"""A rejected run must preserve its files and make no model calls."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runner.__main__ import main
from runner.cascade import ROOT, Options, run_cascade, run_recheck
from runner.providers import StubProvider
from runner.prompts import ruleset_metadata


class TestRunDirectory(unittest.TestCase):
    def test_check_and_recheck_keep_existing_reports_without_calls(self):
        sample = ROOT / "examples" / "sample-draft.md"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run-01"
            out.mkdir()
            report = out / "level-4.md"
            report.write_text("An earlier report.\n", encoding="utf-8")
            for command in ("check", "recheck"):
                with self.subTest(command=command):
                    provider = StubProvider()
                    with self.assertRaisesRegex(FileExistsError, "Choose a new --out"):
                        if command == "check":
                            run_cascade(sample, out, provider, Options())
                        else:
                            run_recheck(out, sample, out, provider, Options())
                    self.assertEqual(provider.calls, [])
                    self.assertEqual(report.read_text(encoding="utf-8"), "An earlier report.\n")
                    self.assertEqual([p.name for p in out.iterdir()], ["level-4.md"])

    def test_cli_rejects_reuse_before_initializing_a_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "notes.txt").write_text("Keep this.\n", encoding="utf-8")
            with patch("runner.__main__.AnthropicProvider") as provider:
                with contextlib.redirect_stderr(io.StringIO()) as error:
                    with self.assertRaises(SystemExit) as stopped:
                        main(["check", "unused.md", "--out", str(out)])
            self.assertEqual(stopped.exception.code, 2)
            provider.assert_not_called()
            self.assertIn("existing files were kept", error.getvalue())

    def test_full_recheck_can_start_in_an_empty_existing_folder(self):
        sample = ROOT / "examples" / "sample-draft.md"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous, out = root / "run-01", root / "run-02"
            previous.mkdir()
            out.mkdir()
            (previous / "draft.md").write_text("# Old draft\n\nDifferent argument.\n", encoding="utf-8")
            (previous / "model.md").write_text("Old model.", encoding="utf-8")
            import json
            (previous / "ruleset.json").write_text(json.dumps(ruleset_metadata()), encoding="utf-8")
            model = root / "model.md"
            model.write_text("New model.", encoding="utf-8")
            provider = StubProvider()
            run_recheck(previous, sample, out, provider, Options(model_file=model), log=lambda _: None)
            self.assertEqual(sorted(level for level, _ in provider.calls), ["1", "2", "3", "4", "5"])
            self.assertTrue((out / "run.json").exists())
