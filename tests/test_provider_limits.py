"""Budget controls and truncated results are tested without API calls."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from runner.__main__ import main
from runner.providers import (AnthropicProvider, Completion, IncompleteCompletionError,
                              OpenAICompatibleProvider, checked_completion)


class TestProviderLimits(unittest.TestCase):
    def test_anthropic_limit_stop_keeps_usage_and_disables_retries(self):
        sdk = MagicMock()
        message = SimpleNamespace(stop_reason="max_tokens", model="test-model",
                                  content=[SimpleNamespace(type="text", text="Partial")],
                                  usage=SimpleNamespace(input_tokens=100, output_tokens=8192,
                                                        cache_read_input_tokens=50, cache_creation_input_tokens=0))
        sdk.Anthropic.return_value.messages.stream.return_value.__enter__.return_value.get_final_message.return_value = message
        with patch.dict("sys.modules", {"anthropic": sdk}):
            provider = AnthropicProvider(model="test-model", max_tokens=8192, fallback=False, retries=0)
            with self.assertRaises(IncompleteCompletionError) as error:
                provider.complete("system", "task")
        sdk.Anthropic.assert_called_once_with(max_retries=0)
        self.assertEqual(sdk.Anthropic.return_value.messages.stream.call_args.kwargs["max_tokens"], 8192)
        self.assertEqual(error.exception.completion.usage["cache_read_input_tokens"], 50)

    def test_compatible_limit_stop_is_rejected_without_network(self):
        body = {"model": "test-model", "choices": [{"message": {"content": "Partial"}, "finish_reason": "length"}],
                "usage": {"output_tokens": 8192}}
        provider = OpenAICompatibleProvider("test-model", "http://local.invalid/v1", max_tokens=8192, retries=0)
        with patch("runner.providers.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as request:
            with self.assertRaises(IncompleteCompletionError):
                provider.complete("system", "task")
        request.assert_called_once()

    def test_token_and_context_stops_cannot_be_completed_reports(self):
        for reason in ("max_tokens", "length", "model_context_window_exceeded"):
            with self.subTest(reason=reason):
                completion = Completion("Partial report.", "test-model", reason, {"output_tokens": 8192})
                with self.assertRaises(IncompleteCompletionError) as error:
                    checked_completion(completion)
                self.assertIs(error.exception.completion, completion)
                self.assertEqual(error.exception.completion.usage["output_tokens"], 8192)
        done = Completion("Completed report.", "test-model", "end_turn")
        self.assertIs(checked_completion(done), done)

    def test_cli_passes_limits_and_zero_retries_to_both_providers(self):
        for provider_name, constructor in (("anthropic", "AnthropicProvider"),
                                           ("openai-compatible", "OpenAICompatibleProvider")):
            with self.subTest(provider=provider_name), tempfile.TemporaryDirectory() as tmp:
                with patch("runner.__main__." + constructor) as provider, patch("runner.__main__.run_cascade"):
                    self.assertEqual(main(["check", "unused.md", "--out", str(Path(tmp) / "run"),
                                           "--provider", provider_name, "--model", "test-model", "--max-tokens", "8192",
                                           "--retries", "0", "--no-fallback", "--base-url", "http://local.invalid/v1"]), 0)
                self.assertEqual(provider.call_args.kwargs["max_tokens"], 8192)
                self.assertEqual(provider.call_args.kwargs["retries"], 0)

    def test_invalid_limits_fail_before_provider_initialization(self):
        for option, value in (("--max-tokens", "0"), ("--max-tokens", "-1"), ("--retries", "-1")):
            with self.subTest(option=option, value=value), contextlib.redirect_stderr(io.StringIO()):
                with patch("runner.__main__.AnthropicProvider") as provider:
                    with self.assertRaises(SystemExit) as stopped:
                        main(["check", "unused.md", "--out", "unused", option, value])
                self.assertEqual(stopped.exception.code, 2)
                provider.assert_not_called()
