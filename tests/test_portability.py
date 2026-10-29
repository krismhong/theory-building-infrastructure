"""Core/agent contracts and uncertainty handling; no semantic model judgments."""
import contextlib
import io
import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from runner.__main__ import main
from runner.cascade import ROOT, compatible_ruleset, run_cascade, run_recheck, write_bundles
from runner.flags import merge_flags, parse_flags, points_from_json, points_to_json, render_decisions
from runner.mechanical import script_pass
from runner.prompts import Options, RULESET_ID, build_system
from runner.providers import AnthropicProvider, OpenAICompatibleProvider, StubProvider
from runner.section_trial import validated_flags
from runner.draft import parse_draft


class TestPortability(unittest.TestCase):
    def test_no_implicit_live_provider_or_endpoint(self):
        cases = [[], ["--provider", "anthropic"],
                 ["--provider", "openai-compatible", "--model", "explicit-model"]]
        for options in cases:
            with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()):
                with patch("runner.__main__.AnthropicProvider") as sdk, patch("runner.__main__.OpenAICompatibleProvider") as http:
                    with self.assertRaises(SystemExit) as stopped:
                        main(["check", "unused.md", "--out", str(Path(tmp)/"run"), *options])
                    self.assertEqual(stopped.exception.code, 2)
                    sdk.assert_not_called()
                    http.assert_not_called()
                    self.assertFalse((Path(tmp)/"run").exists())

    def test_core_needs_no_sdk_genre_or_credentials(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("sys.modules", {"anthropic": None}), patch.dict("os.environ", {}, clear=True):
            out = Path(tmp)/"run"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["check", str(ROOT/"examples/sample-draft.md"), "--out", str(out), "--provider", "stub"]), 0)
            self.assertTrue(compatible_ruleset(out))
            self.assertEqual(len(list(out.glob("level-[1-5].md"))), 5)
            self.assertEqual(json.loads((out/"run.json").read_text())["ruleset"]["id"], RULESET_ID)

    def test_optional_genres_cannot_replace_core_or_require_outlet(self):
        for level in ("1", "2", "3", "4", "5"):
            bare = build_system(level, Options())
            for genre in ("theory-paper.md", "empirical-paper.md"):
                contextual = build_system(level, Options(genre=ROOT/"genres"/genre))
                self.assertIn("cannot override core criteria", contextual)
                self.assertTrue(contextual.endswith(bare.split("\n\n---\n\n")[-1]))
                self.assertIn("Ruleset: " + RULESET_ID, contextual)

    def test_indeterminate_survives_parse_merge_json_and_bounded_contract(self):
        draft = "# Argument\n\n## Findings\n\nThe estimate is interpreted as causal.\n"
        report = (f"Ruleset: {RULESET_ID}\n\n## Level 4\n\n"
                  '[ISSUE:] Rule 4.4. Location: Findings, paragraph 1, sentence 1\n'
                  'Quote: "The estimate is interpreted as causal."\n'
                  'What fails: Identification assumptions are absent from the assigned context.\n'
                  'Decision: Supply the assumptions or narrow the interpretation?\n'
                  'Kind: fork\nAssessment: indeterminate\n\n### Pass down\nNone\n')
        points = points_from_json(points_to_json(merge_flags(parse_flags(report, "4"), draft)))
        flag = points[0].flags[0]
        self.assertEqual((flag.assessment, flag.ruleset), ("indeterminate", RULESET_ID))
        self.assertIn("[indeterminate; " + RULESET_ID + "]", render_decisions(points))
        rows = validated_flags(parse_draft(draft), report, "4")
        self.assertEqual((rows[0]["assessment"], rows[0]["ruleset"]), ("indeterminate", RULESET_ID))

    def test_legacy_reports_are_not_reassigned_new_meanings(self):
        report = '[ISSUE:] Rule 3.1. Location: X\nQuote: "Old words"\nWhat fails: Old criterion\nDecision: Author choice\nKind: fork\n'
        flag = parse_flags(report, "3")[0]
        self.assertEqual((flag.ruleset, flag.assessment), ("", ""))
        self.assertIn("legacy unclassified; unversioned", render_decisions(merge_flags([flag])))

    def test_changed_or_missing_ruleset_blocks_carryover_without_calls(self):
        sample = ROOT/"examples/sample-draft.md"
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path(tmp)/"old"
            previous.mkdir()
            for metadata in (None, {"id": "core-v1", "definitions": {}}):
                if metadata:
                    (previous/"ruleset.json").write_text(json.dumps(metadata))
                provider = StubProvider()
                with self.assertRaisesRegex(ValueError, "ruleset"):
                    run_recheck(previous, sample, Path(tmp)/"new", provider, Options(), log=lambda _: None)
                self.assertEqual(provider.calls, [])
                with self.assertRaisesRegex(ValueError, "ruleset"):
                    write_bundles(sample, Path(tmp)/"bundles", "all", Options(), previous)

    def test_normative_word_is_not_a_mechanical_logic_failure(self):
        report = script_pass("# Argument\n\n## Recommendation\n\nPeople should honor their promises.\n").report
        self.assertEqual(parse_flags(report, "S"), [])
        flags = parse_flags(script_pass("# Argument\n\n## Claim\n\nThis always happens.\n", "## Words to flag\n- happens -> occurs\n").report, "S")
        self.assertEqual({f.assessment for f in flags}, {"indeterminate", "policy_note"})

    def test_new_preparation_does_not_overwrite_unversioned_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            original = out/"bundle-3.md"
            original.write_text("Original task with earlier criteria.")
            with self.assertRaisesRegex(ValueError, "Unversioned"):
                write_bundles(ROOT/"examples/sample-draft.md", out, "all", Options())
            self.assertEqual(original.read_text(), "Original task with earlier criteria.")
            self.assertFalse((out/"ruleset.json").exists())

    def test_optional_sdk_has_no_implicit_reasoning_or_model_substitution(self):
        sdk = MagicMock()
        sdk.Anthropic.return_value.messages.stream.return_value.__enter__.return_value.get_final_message.return_value = SimpleNamespace(
            stop_reason="end_turn", model="chosen-model", content=[SimpleNamespace(type="text", text="Completed.")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1))
        with patch.dict("sys.modules", {"anthropic": sdk}):
            AnthropicProvider("chosen-model").complete("system", "user")
        params = sdk.Anthropic.return_value.messages.stream.call_args.kwargs
        self.assertEqual(params["model"], "chosen-model")
        self.assertNotIn("thinking", params)
        self.assertNotIn("output_config", params)
        sdk.Anthropic.return_value.beta.messages.stream.assert_not_called()
        with self.assertRaisesRegex(ValueError, "substitution"):
            AnthropicProvider("chosen-model", fallback=True)

    def test_optional_local_http_needs_no_key(self):
        body = {"choices": [{"message": {"content": "scripted"}, "finish_reason": "stop"}]}
        with patch.dict("os.environ", {}, clear=True), patch("runner.providers.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as request:
            provider = OpenAICompatibleProvider("chosen-model", "http://local.invalid/v1", retries=0)
            provider.complete("system", "user")
        self.assertEqual(request.call_args.args[0].full_url, "http://local.invalid/v1/chat/completions")
        self.assertNotIn("Authorization", request.call_args.args[0].headers)
