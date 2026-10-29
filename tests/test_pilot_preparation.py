"""The public pilot is prepared offline and does not inherit author layers."""

import json
import tempfile
import unittest
from pathlib import Path

from tools.prepare_pilot import prepare


class TestPilotPreparation(unittest.TestCase):
    def test_requests_are_public_separate_without_assumed_execution_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project.md").write_text("PRIVATE SENTINEL", encoding="utf-8")
            manifest = prepare(root / "requests")
            self.assertEqual(len(manifest["prepared_requests"]), 5)
            self.assertEqual(manifest["maximum_checker_jobs_in_scaffold"], 7)
            self.assertIsNone(manifest["token_budget"])
            self.assertIsNone(manifest["dollar_budget"])
            self.assertIn("not dispatched", manifest["dispatch"])
            self.assertTrue(all(x is None for x in manifest["layers"].values()))
            full = json.loads((root / "requests" / "full-level-4.json").read_text(encoding="utf-8"))
            revised = json.loads((root / "requests" / "revised-level-4.json").read_text(encoding="utf-8"))
            self.assertGreater(len(full["paragraphs"]), len(revised["paragraphs"]))
            self.assertEqual(len(revised["paragraphs"]), 2)
            for path in (root / "requests").glob("*.json"):
                self.assertNotIn("PRIVATE SENTINEL", path.read_text(encoding="utf-8"))

    def test_empty_gate_skips_level4_but_keeps_cited_clauses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "none.md"
            report.write_text("### Pass down\nNone\n", encoding="utf-8")
            manifest = prepare(root / "requests", report, report)
            self.assertIn("gated-level-4", manifest["skipped_requests"])
            self.assertIn("gated-level-5", [x["request"] for x in manifest["prepared_requests"]])
            self.assertEqual(manifest["external_calls"], 0)

    def test_preparation_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sentinel = root / "prior.json"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                prepare(root)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
