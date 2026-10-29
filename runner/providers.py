"""Model providers. The cascade calls `provider.complete(system, user)` and never depends on a vendor. `history` holds
earlier turns of the same conversation, as (user, assistant) pairs, so that a checker can be asked about its own report.

- AnthropicProvider: Claude, through the official `anthropic` SDK (install with `pip install anthropic`).
- OpenAICompatibleProvider: any endpoint that speaks the OpenAI chat-completions protocol, including
  open-weight models served locally (for example by vLLM or Ollama). Standard library only.
- StubProvider: returns scripted reports; used by the tests and for dry runs.
"""

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass
class Completion:
    text: str
    served_model: str
    stop_reason: str = ""
    usage: dict = field(default_factory=dict)


class RefusalError(RuntimeError):
    """The model declined the request; the level's report is not usable."""

    def __init__(self, completion: Completion):
        self.completion = completion
        super().__init__("The provider declined or filtered the request; the response is not a completed report.")


class IncompleteCompletionError(RuntimeError):
    """A token/context limit interrupted a report; never merge it as a finished check."""

    def __init__(self, completion: Completion):
        self.completion = completion
        super().__init__(f"{completion.served_model} stopped on {completion.stop_reason}; the report is incomplete. "
                         "Keep this call's usage, review its budget, and do not score it as a completed check.")


def checked_completion(completion: Completion) -> Completion:
    if not isinstance(completion, Completion):
        raise TypeError("Provider must return a Completion record.")
    if (not isinstance(completion.stop_reason, str) or not isinstance(completion.served_model, str)
            or not completion.served_model.strip()):
        raise IncompleteCompletionError(completion)
    if completion.stop_reason in {"max_tokens", "length", "model_context_window_exceeded"}:
        raise IncompleteCompletionError(completion)
    if completion.stop_reason in {"refusal", "content_filter"}:
        raise RefusalError(completion)
    if (completion.stop_reason not in {"stop", "end_turn", "stop_sequence"}
            or not isinstance(completion.text, str) or not completion.text.strip()):
        raise IncompleteCompletionError(completion)
    return completion


class AnthropicProvider:
    """Optional SDK adapter with explicit model selection and no automatic model substitution.

    Reasoning configuration is opt-in; live endpoint/model compatibility is unverified.
    """

    name = "anthropic"
    def __init__(self, model: str, effort: str | None = None, max_tokens: int = 8192, fallback: bool = False,
                 retries: int = 2):
        if not model:
            raise ValueError("Explicit model selection is required.")
        if fallback:
            raise ValueError("Automatic model substitution is unsupported; select a model explicitly.")
        import anthropic  # optional dependency, needed only for this provider

        self.client = anthropic.Anthropic(max_retries=retries)  # reads the configured credential
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.fallback = fallback
        self.retries = retries

    def complete(self, system: str, user: str, history: list[tuple[str, str]] | None = None) -> Completion:
        params = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=_messages(user, history),
        )
        if self.effort is not None:
            params.update(thinking={"type": "adaptive"}, output_config={"effort": self.effort})
        with self.client.messages.stream(**params) as stream:
            message = stream.get_final_message()
        blocks = [block.text for block in message.content if block.type == "text"]
        text = "".join(blocks) if all(isinstance(block, str) for block in blocks) else None
        usage = {"input_tokens": message.usage.input_tokens, "output_tokens": message.usage.output_tokens,
                 "cache_creation_input_tokens": getattr(message.usage, "cache_creation_input_tokens", 0) or 0,
                 "cache_read_input_tokens": getattr(message.usage, "cache_read_input_tokens", 0) or 0}
        return checked_completion(Completion(text=text, served_model=message.model,
                                             stop_reason=message.stop_reason or "", usage=usage))


class OpenAICompatibleProvider:
    """Any OpenAI-compatible chat-completions endpoint (hosted, or an open-weight model served locally)."""

    name = "openai-compatible"

    def __init__(self, model: str, base_url: str, api_key_env: str = "OPENAI_API_KEY",
                 max_tokens: int | None = None, timeout: float = 900.0, retries: int = 3):
        if not model or not base_url:
            raise ValueError("Explicit model and endpoint selection are required.")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = os.environ.get(api_key_env, "")
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.retries = retries

    def complete(self, system: str, user: str, history: list[tuple[str, str]] | None = None) -> Completion:
        body = {"model": self.model, "messages": [{"role": "system", "content": system}] + _messages(user, history)}
        if self.max_tokens:
            body["max_tokens"] = self.max_tokens
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers)
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.load(response)
                break
            except urllib.error.HTTPError as error:
                if error.code in (408, 409, 429) or error.code >= 500:
                    if attempt < self.retries:
                        time.sleep(2 ** (attempt + 1))
                        continue
                raise
        # Preserve available usage/model information even for malformed responses.
        data = data if isinstance(data, dict) else {}
        choices = data.get("choices")
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict) else {}
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        completion = Completion(text=message.get("content"), served_model=data.get("model") or self.model,
                                stop_reason=choice.get("finish_reason") or "",
                                usage=data.get("usage") if isinstance(data.get("usage"), dict) else {})
        if message.get("refusal"):
            completion.stop_reason = "refusal"
        elif message.get("tool_calls") or message.get("function_call"):
            completion.stop_reason = "tool_calls"
        return checked_completion(completion)


class StubProvider:
    """Returns a scripted report for each level (keyed "1" to "5" and "W"), the organizer's report (keyed "O"), and a
    checker's answers to the organizer (keyed "A" plus the level, or "A"); no model is called."""

    name = "stub"

    def __init__(self, script: dict[str, str] | None = None):
        self.script = script or {}
        self.model = "stub"
        self.calls: list[tuple[str, str]] = []
        self.histories: list[list[tuple[str, str]]] = []

    def complete(self, system: str, user: str, history: list[tuple[str, str]] | None = None) -> Completion:
        level = _level_of(system)
        if history:
            level = "A" + level
        self.calls.append((level, user))
        self.histories.append(list(history or []))
        from .prompts import RULESET_ID
        default = ("## Organizer\n\n### Questions for checkers\nNone\n" if level == "O" else "## Your flags\nNone\n\n## Disputes\nNone\n" if level.startswith("A") else
                   f"Ruleset: {RULESET_ID}\n\n## Level {level}\n\nNo issues found at Level {level}.\n\n### Pass down\nNone\n")
        text = self.script.get(level, self.script.get("A", default) if level.startswith("A") else default)
        return Completion(text=text, served_model="stub", stop_reason="end_turn")


def _messages(user: str, history: list[tuple[str, str]] | None) -> list[dict]:
    turns = []
    for asked, answered in history or []:
        turns += [{"role": "user", "content": asked}, {"role": "assistant", "content": answered}]
    return turns + [{"role": "user", "content": user}]


def _level_of(system: str) -> str:
    """Identify which level a system prompt is for, from the level file it ends with (a genre file may name other levels)."""
    markers = (("W", "# Optional pass: word choice"), ("1", "# Level 1:"), ("2", "# Level 2:"),
               ("3", "# Level 3:"), ("4", "# Level 4:"), ("5", "# Level 5:"), ("O", "# The organizer"))
    found = [(system.rfind(marker), level) for level, marker in markers if marker in system]
    return max(found)[1] if found else "?"
