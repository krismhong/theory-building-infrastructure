"""Offline contract checks using fictional sections and receipts in local Temp."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from runner.section_trial import COMPLETE, TrialStopped, accept_report, preflight_report, private_path, section_trial
from runner.verification import preflight_verification, prepare_verification, validate_reconciliation
from tools.section_trial import main


FIRST = "Invented teams reserve a quiet interval to compare their fictional plans."
SECOND = "Imaginary workers record the remaining choices before the next scheduled meeting."
SECTION = f"## Fictional section\n\n{FIRST}\nThey review a made-up schedule.\n\n{SECOND}\n"
TRACE_FIRST = "Invented lanterns illuminate the empty model village."
TRACE_SECOND = "Fictional boats remain beside the painted paper harbor."
TRACE_SECTION = f"## Lantern topic\n\n{TRACE_FIRST}\n\n## Harbor topic\n\n{TRACE_SECOND}\n"


class TestSectionTrial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="section-trial-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.number = 0

    def prepare(self, text=SECTION):
        self.number += 1
        source = self.root / f"input-{self.number}.md"
        target = self.root / f"run-{self.number}"
        source.write_text(text, encoding="utf-8")
        return target, section_trial(source, target)

    def read_state(self, target):
        return json.loads((target / "trial.json").read_text(encoding="utf-8"))

    def report(self, label="level-3", gate="None"):
        level = "3" if label == "level-3" else "4"
        return f"## Level {level}\n\n### Pass down\n{gate}\n\n### Summary\nFictional check finished.\n\n{COMPLETE}\n"

    def handoff(self, target, label="level-3", report=None, receipt=None):
        (target / f"{label}.md").write_text(report or self.report(label), encoding="utf-8")
        data = {"status": "completed", "completion_confirmed": True,
                "backend": "offline-test-adapter", "executor_id": f"test-{label}", "model": "fictional-checker",
                "task": label, "report_sha256": hashlib.sha256((target / f"{label}.md").read_bytes()).hexdigest()}
        if receipt is not None:
            data.update(receipt)
        path = self.root / f"receipt-{target.name}-{label}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def assert_stops(self, target, label, receipt, exception=TrialStopped):
        report = target / f"{label}.md"
        before = report.read_bytes() if report.exists() else None
        with self.assertRaises(exception):
            accept_report(target, label, receipt)
        state = self.read_state(target)
        self.assertEqual(state["status"], "stopped")
        self.assertIsNone(state["next_task"])
        if before is not None:
            self.assertEqual(report.read_bytes(), before)
        with self.assertRaises(TrialStopped):
            accept_report(target, label, receipt)

    def test_private_paths_require_dedicated_temp_outside_repo_sync_public(self):
        self.assertEqual(private_path(self.root / "new"), (self.root / "new").resolve())
        for path in (Path(tempfile.gettempdir()), Path(__file__), self.root / ".." / "..",
                     *(self.root / name / "run" for name in ("Dropbox", "OneDrive-Test", "Public", "prototype", "os-proposal"))):
            with self.subTest(path=path), self.assertRaises(TrialStopped):
                private_path(path)
        for marker in (".git", ".openai/hosting.json"):
            ancestor = self.root / marker.replace("/", "-")
            marker_path = ancestor / marker
            if marker.endswith("json"):
                marker_path.parent.mkdir(parents=True)
                marker_path.write_text("{}", encoding="utf-8")
            else:
                ancestor.mkdir()
                marker_path.write_text("gitdir: fictional", encoding="utf-8")
            with self.subTest(marker=marker), self.assertRaises(TrialStopped):
                private_path(ancestor / "run")

    def test_nonempty_output_and_input_are_preserved(self):
        source = self.root / "input.md"
        source.write_text(SECTION, encoding="utf-8")
        target = self.root / "used"
        target.mkdir()
        sentinel = target / "prior.md"
        sentinel.write_text("Keep earlier output.", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            section_trial(source, target)
        self.assertEqual(source.read_text(encoding="utf-8"), SECTION)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "Keep earlier output.")
        self.assertEqual(list(target.iterdir()), [sentinel])

    def test_word_boundary_and_empty_or_reference_only_sections(self):
        target, _ = self.prepare(" ".join(["fictional"] * 1500))
        self.assertTrue((target / "task-level-3.md").exists())
        for text in (" ".join(["fictional"] * 1501), "", "## Empty\n", "## References\n\nInvented reference only."):
            with self.subTest(words=len(text.split())), self.assertRaises(TrialStopped):
                self.prepare(text)
            self.assertFalse((self.root / f"run-{self.number}").exists())

    def test_preparation_only_makes_l3_ready_and_full_l4_bundle(self):
        target, state = self.prepare(SECTION + "\n## References\n\nInvented bibliography entry.\n")
        self.assertEqual(state["next_task"], "level-3")
        self.assertEqual(state["status"], "prepared")
        self.assertEqual(state["maximum_tasks"], 3)
        self.assertEqual(state["completed_tasks"], [])
        self.assertEqual(state["api_calls_by_this_helper"], 0)
        self.assertEqual(state["dispatch"], "external adapter required")
        self.assertEqual(sorted(p.name for p in target.iterdir()),
                         ["bundle-full-level-4.json", "bundle-level-3.json", "section.md", "task-level-3.md", "trial.json"])
        full = json.loads((target / "bundle-full-level-4.json").read_text(encoding="utf-8"))
        self.assertEqual(full["paragraphs"], [1, 2])
        self.assertNotIn("Invented bibliography entry", full["user"])
        task = (target / "task-level-3.md").read_text(encoding="utf-8")
        self.assertIn(COMPLETE, task)
        self.assertIn("Do not edit the manuscript", task)
        self.assertIn("call a model/API", task)

    def test_sequential_l3_full_l4_gated_l4_and_three_task_ceiling(self):
        target, _ = self.prepare()
        gate = f'- Fictional section, paragraph 1: "{FIRST}" Needs a sentence check.\n- "{FIRST}" Duplicate location.'
        receipt = self.handoff(target, report=self.report(gate=gate))
        state = accept_report(target, "level-3", receipt)
        self.assertEqual(state["next_task"], "full-level-4")
        self.assertEqual(state["gated_level4"], "prepared")
        gated = json.loads((target / "bundle-gated-level-4.json").read_text(encoding="utf-8"))
        self.assertEqual(gated["paragraphs"], [1])
        self.assertNotIn(SECOND, gated["user"])
        self.assertFalse((target / "task-gated-level-4.md").exists())
        state = accept_report(target, "full-level-4", self.handoff(target, "full-level-4"))
        self.assertEqual(state["next_task"], "gated-level-4")
        self.assertTrue((target / "task-gated-level-4.md").exists())
        state = accept_report(target, "gated-level-4", self.handoff(target, "gated-level-4"))
        self.assertEqual(state["status"], "complete")
        self.assertIsNone(state["next_task"])
        self.assertEqual([x["task"] for x in state["completed_tasks"]], ["level-3", "full-level-4", "gated-level-4"])
        before = (target / "trial.json").read_bytes()
        with self.assertRaises(TrialStopped):
            accept_report(target, "gated-level-4", receipt)
        self.assertEqual((target / "trial.json").read_bytes(), before)

    def test_explicit_empty_gate_skips_gated_but_runs_full_l4(self):
        target, _ = self.prepare()
        state = accept_report(target, "level-3", self.handoff(target))
        self.assertEqual(state["gated_level4"], "skipped: explicit empty gate")
        self.assertEqual(state["next_task"], "full-level-4")
        self.assertFalse((target / "bundle-gated-level-4.json").exists())
        state = accept_report(target, "full-level-4", self.handoff(target, "full-level-4"))
        self.assertEqual(state["status"], "complete")
        self.assertEqual(len(state["completed_tasks"]), 2)

    def test_missing_duplicate_unlocated_or_implicit_empty_gate_stops(self):
        reports = [self.report().replace("### Pass down\nNone\n", ""),
                   self.report(gate="None\n\n### Pass down\nNone"),
                   self.report(gate=""), self.report(gate="None because it looks fine."),
                   self.report(gate="- A location not present in the fictional section.")]
        for report in reports:
            with self.subTest(report=report):
                target, _ = self.prepare()
                self.assert_stops(target, "level-3", self.handoff(target, report=report))

    def test_ambiguous_and_reference_gate_locations_stop(self):
        for text, quote in ((SECTION + f"\n{FIRST}\n", FIRST),
                            (SECTION + f"\n## References\n\n{FIRST}\n", FIRST),
                            (SECTION + "\n## References\n\nInvented reference includes a sufficiently long unique first sentence.\n",
                             "Invented reference includes a sufficiently long unique first sentence.")):
            with self.subTest(quote=quote):
                target, _ = self.prepare(text)
                self.assert_stops(target, "level-3", self.handoff(target, report=self.report(gate=f'- "{quote}"')))

    def test_short_opening_accepts_exact_structured_heading_and_sentence(self):
        target, _ = self.prepare("## Invented topic\n\nSmall topic. A fictional detail follows.\n")
        receipt = self.handoff(target, report=self.report(gate="- Invented topic | Small topic. | Check its invented detail."))
        state = accept_report(target, "level-3", receipt)
        self.assertEqual(state["next_task"], "full-level-4")
        self.assertEqual(state["gated_level4"], "prepared")
        gated = json.loads((target / "bundle-gated-level-4.json").read_text(encoding="utf-8"))
        self.assertEqual(gated["paragraphs"], [1])
        self.assertIn("A fictional detail follows.", gated["user"])

    def test_repeated_short_openings_in_same_heading_stop(self):
        target, _ = self.prepare("## Invented topic\n\nSmall topic. First invented detail.\n\nSmall topic. Second invented detail.\n")
        receipt = self.handoff(target, report=self.report(gate="- Invented topic | Small topic. | Check the detail."))
        self.assert_stops(target, "level-3", receipt)

    def test_identical_short_openings_resolve_only_exact_named_heading(self):
        text = "## Invented topic\n\nSmall topic. First invented detail.\n\n## Other invented topic\n\nSmall topic. Second invented detail.\n"
        for heading, paragraph, selected, excluded in (("Invented topic", 1, "First invented detail.", "Second invented detail."),
                                                       ("Other invented topic", 2, "Second invented detail.", "First invented detail.")):
            with self.subTest(heading=heading):
                target, _ = self.prepare(text)
                receipt = self.handoff(target, report=self.report(gate=f"- {heading} | Small topic. | Check the detail."))
                state = accept_report(target, "level-3", receipt)
                self.assertEqual(state["gated_level4"], "prepared")
                gated = json.loads((target / "bundle-gated-level-4.json").read_text(encoding="utf-8"))
                self.assertEqual(gated["paragraphs"], [paragraph])
                self.assertIn(selected, gated["user"])
                self.assertNotIn(excluded, gated["user"])

    def test_short_opening_wrong_heading_partial_sentence_or_unstructured_quote_stops(self):
        for gate in ("- Wrong heading | Small topic. | Check the detail.",
                     "- Invented | Small topic. | Check the detail.",
                     "- Invented topic | Small | Check the detail.",
                     '- "Small topic." Check the detail.'):
            with self.subTest(gate=gate):
                target, _ = self.prepare("## Invented topic\n\nSmall topic. A fictional detail follows.\n")
                self.assert_stops(target, "level-3", self.handoff(target, report=self.report(gate=gate)))

    def test_completion_marker_and_report_level_and_summary_are_required(self):
        base = self.report()
        for report in (base.replace(COMPLETE, ""), base.replace("\n" + COMPLETE, " " + COMPLETE),
                       base + "Extra output.\n", base.replace("Level 3", "Level 4"),
                       base.replace("### Summary", "### Conclusion"),
                       base.replace("Fictional check finished.", "")):
            with self.subTest(report=report):
                target, _ = self.prepare()
                self.assert_stops(target, "level-3", self.handoff(target, report=report))

    def test_missing_report_or_receipt_stops_and_preserves_artifacts(self):
        for missing in ("report", "receipt"):
            with self.subTest(missing=missing):
                target, _ = self.prepare()
                receipt = self.handoff(target)
                (receipt if missing == "receipt" else target / "level-3.md").unlink()
                self.assert_stops(target, "level-3", receipt, FileNotFoundError)

    def test_adapter_must_independently_confirm_completed_task(self):
        for values in ({"completion_confirmed": False}, {"completion_confirmed": 1},
                       {"status": "error"}, {"status": "incomplete"},
                       {"backend": ""}, {"executor_id": " "}, {"model": None},
                       {"task": None}, {"task": "full-level-4"}, {"report_sha256": None},
                       {"report_sha256": "wrong-hash"}):
            with self.subTest(receipt=values):
                target, _ = self.prepare()
                self.assert_stops(target, "level-3", self.handoff(target, receipt=values))

    def test_outside_temp_receipt_stops_without_reading_it(self):
        target, _ = self.prepare()
        self.handoff(target)
        self.assert_stops(target, "level-3", Path(__file__))

    def test_receipt_reuse_for_different_task_stops(self):
        target, _ = self.prepare()
        receipt = self.handoff(target)
        accept_report(target, "level-3", receipt)
        self.handoff(target, "full-level-4")
        self.assert_stops(target, "full-level-4", receipt)

    def test_report_changed_after_receipt_stops(self):
        target, _ = self.prepare()
        receipt = self.handoff(target)
        (target / "level-3.md").write_text(self.report().replace("finished", "altered"), encoding="utf-8")
        self.assert_stops(target, "level-3", receipt)

    def test_l4_missing_duplicate_or_empty_pass_down_and_summary_stop(self):
        base = self.report("full-level-4")
        for report in (base.replace("### Pass down\nNone\n", ""),
                       base.replace("None\n", "\n"),
                       base.replace("None\n", "None\n\n### Pass down\nNone\n"),
                       base.replace("Fictional check finished.", "")):
            with self.subTest(report=report):
                target, _ = self.prepare()
                accept_report(target, "level-3", self.handoff(target))
                self.assert_stops(target, "full-level-4", self.handoff(target, "full-level-4", report=report))

    def test_incomplete_adapter_stop_reasons_stop(self):
        for reason in ("max_tokens", "length", "model_context_window_exceeded", "interrupted", "error", "refusal"):
            with self.subTest(reason=reason):
                target, _ = self.prepare()
                self.assert_stops(target, "level-3", self.handoff(target, receipt={"stop_reason": reason}))

    def test_unexpected_unknown_tasks_stop_and_accepted_task_reuse_preserves_state(self):
        for label in ("full-level-4", "gated-level-4", "unknown-task"):
            with self.subTest(label=label):
                target, _ = self.prepare()
                self.assert_stops(target, label, self.handoff(target, label))
        target, _ = self.prepare()
        receipt = self.handoff(target)
        accept_report(target, "level-3", receipt)
        before = (target / "trial.json").read_bytes()
        accept_report(target, "level-3", receipt)
        self.assertEqual((target / "trial.json").read_bytes(), before)

    def test_mutated_section_or_current_bundle_stops(self):
        for name in ("section.md", "bundle-level-3.json"):
            with self.subTest(name=name):
                target, _ = self.prepare()
                receipt = self.handoff(target)
                with (target / name).open("a", encoding="utf-8") as changed:
                    changed.write("\nFictional mutation.\n")
                self.assert_stops(target, "level-3", receipt)

    def test_mutated_full_or_gated_bundle_stops_when_scheduled(self):
        for label in ("full-level-4", "gated-level-4"):
            with self.subTest(label=label):
                target, _ = self.prepare()
                receipt = self.handoff(target, report=self.report(gate=f'- "{FIRST}"'))
                accept_report(target, "level-3", receipt)
                if label == "gated-level-4":
                    accept_report(target, "full-level-4", self.handoff(target, "full-level-4"))
                with (target / f"bundle-{label}.json").open("a", encoding="utf-8") as changed:
                    changed.write("\n ")
                self.assert_stops(target, label, self.handoff(target, label))

    def test_unknown_observations_are_null_and_real_observations_are_retained(self):
        for observations in ({}, {"elapsed_seconds": 1.25, "input_tokens": 11,
                                  "output_tokens": 7, "total_tokens": 18}):
            with self.subTest(observations=observations):
                target, _ = self.prepare()
                state = accept_report(target, "level-3", self.handoff(target, receipt=observations))
                for key in ("elapsed_seconds", "input_tokens", "output_tokens", "total_tokens"):
                    self.assertEqual(state["completed_tasks"][0][key], observations.get(key))

    def test_invalid_observed_usage_and_time_stop(self):
        for key in ("elapsed_seconds", "input_tokens", "output_tokens", "total_tokens"):
            values = [True, "12", -1, float("nan"), float("inf")]
            if key != "elapsed_seconds":
                values.append(1.5)
            for value in values:
                with self.subTest(key=key, value=value):
                    target, _ = self.prepare()
                    self.assert_stops(target, "level-3", self.handoff(target, receipt={key: value}))

    def test_malformed_and_nonobject_receipts_stop(self):
        for text in ("{bad-json", "[]", "null"):
            with self.subTest(text=text):
                target, _ = self.prepare()
                receipt = self.handoff(target)
                receipt.write_text(text, encoding="utf-8")
                self.assert_stops(target, "level-3", receipt, ValueError)

    def test_cli_prepares_and_accepts_using_only_local_temp(self):
        source = self.root / "cli-section.md"
        source.write_text(SECTION, encoding="utf-8")
        target = self.root / "cli-run"
        with patch("sys.argv", ["section_trial", "--input", str(source), "--out", str(target)]), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 0)
        self.assertIn("No model/API calls", output.getvalue())
        receipt = self.handoff(target)
        with patch("sys.argv", ["section_trial", "--accept", "level-3", "--out", str(target), "--receipt", str(receipt)]), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 0)
        self.assertIn("Next task: full-level-4", output.getvalue())

    def test_cli_fictional_mode_preserves_existing_different_input(self):
        source = self.root / "fictional-section.md"
        source.write_text("Keep the user's fictional input.", encoding="utf-8")
        target = self.root / "fictional-run"
        with patch("sys.argv", ["section_trial", "--fictional", "--out", str(target)]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 2)
        self.assertEqual(source.read_text(encoding="utf-8"), "Keep the user's fictional input.")
        self.assertFalse(target.exists())

    def flag_report(self, *, location="Harbor topic, paragraph 1", quote=TRACE_SECOND,
                    rule="3.1", kind="slip", tag="ISSUE", label="level-3"):
        flag = (f"[{tag}] Rule {rule}\nKind: {kind}\nLocation: {location}\nQuote: {quote}\n"
                "What fails: The invented conclusion lacks an invented premise.\n"
                "Decision: Supply the fictional premise.\n\n")
        return self.report(label).replace("\n\n### Pass down", "\n\n" + flag + "### Pass down")

    def test_unicode_bundles_are_ascii_bytes_and_decode_original_characters(self):
        sentence = "Invented café visitors say “hello”—then inspect 雪 and a toy 🛶."
        text = f"## Imaginary café\n\n{sentence}\n"
        target, _ = self.prepare(text)
        for label in ("level-3", "full-level-4"):
            with self.subTest(label=label):
                bundle_bytes = (target / f"bundle-{label}.json").read_bytes()
                bundle = json.loads(bundle_bytes.decode("ascii"))
                self.assertIn(sentence, bundle["user"])
                self.assertIn("Imaginary café", bundle["user"])
        gate = f'- Imaginary café | "{sentence}" | Check its fictional details.'
        accept_report(target, "level-3", self.handoff(target, report=self.report(gate=gate)))
        gated_bytes = (target / "bundle-gated-level-4.json").read_bytes()
        self.assertIn(sentence, json.loads(gated_bytes.decode("ascii"))["user"])
        self.assertEqual((target / "section.md").read_text(encoding="utf-8"), text)

    def test_preparation_acceptance_timestamps_and_local_validation_observations(self):
        target, state = self.prepare()
        started = datetime.fromisoformat(state["started_at_utc"])
        prepared = datetime.fromisoformat(state["prepared_at_utc"])
        self.assertEqual(started.utcoffset(), timedelta(0))
        self.assertEqual(prepared.utcoffset(), timedelta(0))
        self.assertLessEqual(started, prepared)
        state = accept_report(target, "level-3", self.handoff(target))
        accepted = state["completed_tasks"][0]
        timestamp = datetime.fromisoformat(accepted["accepted_at_utc"])
        self.assertEqual(timestamp.utcoffset(), timedelta(0))
        self.assertGreaterEqual(timestamp, prepared)
        self.assertIsInstance(accepted["local_validation_seconds"], (int, float))
        self.assertGreaterEqual(accepted["local_validation_seconds"], 0)
        for key in ("elapsed_seconds", "input_tokens", "output_tokens", "total_tokens"):
            self.assertIsNone(accepted[key])
        parsed_path = target / "flags-level-3.json"
        self.assertEqual(json.loads(parsed_path.read_text(encoding="utf-8")), {"level": "3", "flags": []})
        self.assertEqual(accepted["parsed_flags_sha256"], hashlib.sha256(parsed_path.read_bytes()).hexdigest())

    def test_atomic_flags_trace_heading_local_paragraphs_at_l3_and_l4(self):
        target, _ = self.prepare(TRACE_SECTION)
        for label, rule, level in (("level-3", "3.1", "3"), ("full-level-4", "4.1", "4")):
            with self.subTest(label=label):
                report = self.flag_report(label=label, rule=rule)
                receipt = self.handoff(target, label, report=report)
                raw = (target / f"{label}.md").read_bytes()
                accept_report(target, label, receipt)
                flags = json.loads((target / f"flags-{label}.json").read_text(encoding="utf-8"))
                self.assertEqual(flags["level"], level)
                self.assertEqual(len(flags["flags"]), 1)
                row = flags["flags"][0]
                self.assertEqual(row["rule"], rule)
                self.assertEqual(row["severity"], "ISSUE")
                self.assertEqual(row["kind"], "slip")
                self.assertEqual(row["quoted_locations"], [{"quote": TRACE_SECOND,
                    "heading": "Harbor topic", "paragraph": 1, "paragraph_index": 2}])
                self.assertEqual((target / f"{label}.md").read_bytes(), raw)

    def test_compound_flag_serializes_each_canonical_source_trace(self):
        target, _ = self.prepare(TRACE_SECTION)
        report = self.flag_report(location="Lantern topic, paragraph 1; Harbor topic, paragraph 1",
                                  quote=f'"{TRACE_FIRST}"; "{TRACE_SECOND}"', kind="fork")
        accept_report(target, "level-3", self.handoff(target, report=report))
        flags = json.loads((target / "flags-level-3.json").read_text(encoding="utf-8"))["flags"]
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["kind"], "fork")
        self.assertEqual(flags[0]["quoted_locations"], [
            {"quote": TRACE_FIRST, "heading": "Lantern topic", "paragraph": 1, "paragraph_index": 1},
            {"quote": TRACE_SECOND, "heading": "Harbor topic", "paragraph": 1, "paragraph_index": 2}])

    def test_compound_locations_validate_each_heading_paragraph_pair(self):
        text = ("## H1\n\nFirst invented lantern detail.\n\nSecond invented lantern detail.\n\n"
                "## H2\n\nFirst fictional harbor detail.\n\nSecond fictional harbor detail.\n")
        quote = '"Second invented lantern detail."; "First fictional harbor detail."'
        target, _ = self.prepare(text)
        swapped = self.flag_report(location="H1, paragraph 1; H2, paragraph 2", quote=quote)
        self.assert_stops(target, "level-3", self.handoff(target, report=swapped))
        self.assertFalse((target / "task-full-level-4.md").exists())
        target, _ = self.prepare(text)
        correct = self.flag_report(location="H1, paragraph 2; H2, paragraph 1", quote=quote)
        state = accept_report(target, "level-3", self.handoff(target, report=correct))
        self.assertEqual(state["next_task"], "full-level-4")
        flags = json.loads((target / "flags-level-3.json").read_text(encoding="utf-8"))["flags"]
        self.assertEqual([(q["heading"], q["paragraph"], q["paragraph_index"])
                          for q in flags[0]["quoted_locations"]], [("H1", 2, 2), ("H2", 1, 3)])

    def test_malformed_missing_fields_and_wrong_level_flags_stop_without_release(self):
        valid = self.flag_report()
        reports = [self.flag_report(rule="4.1"), self.flag_report(kind="unknown"),
                   self.flag_report(tag="WARNING")]
        for prefix in ("Kind:", "Location:", "Quote:", "What fails:", "Decision:"):
            reports.append("\n".join(line for line in valid.splitlines() if not line.startswith(prefix)))
        reports.append(valid.replace("Rule 3.1", "Rule missing"))
        for report in reports:
            with self.subTest(report=report):
                target, _ = self.prepare(TRACE_SECTION)
                receipt = self.handoff(target, report=report)
                self.assert_stops(target, "level-3", receipt)
                self.assertFalse((target / "task-full-level-4.md").exists())
                self.assertFalse((target / "flags-level-3.json").exists())
                self.assertEqual(self.read_state(target)["completed_tasks"], [])

    def test_corrupted_quotes_and_global_paragraph_number_stop_without_release(self):
        for report in (self.flag_report(quote=TRACE_SECOND.replace("boats", "ships")),
                       self.flag_report(location="Harbor topic, paragraph 2"),
                       self.flag_report(location="Lantern topic, paragraph 1")):
            with self.subTest(report=report):
                target, _ = self.prepare(TRACE_SECTION)
                receipt = self.handoff(target, report=report)
                self.assert_stops(target, "level-3", receipt)
                self.assertFalse((target / "task-full-level-4.md").exists())
                self.assertFalse((target / "flags-level-3.json").exists())
                stopped = datetime.fromisoformat(self.read_state(target)["stopped_at_utc"])
                self.assertEqual(stopped.utcoffset(), timedelta(0))


    def test_labeled_quote_field_stops_and_preserves_the_raw_report(self):
        target, _ = self.prepare(TRACE_SECTION)
        report = self.flag_report().replace("Quote:", "Quote (sentence 1):")
        receipt = self.handoff(target, report=report)
        self.assert_stops(target, "level-3", receipt)
        self.assertFalse((target / "task-full-level-4.md").exists())
        self.assertFalse((target / "flags-level-3.json").exists())

    def snapshot(self, target):
        return {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}

    def correction(self, target, original_receipt, report=None):
        data = json.loads(original_receipt.read_text(encoding="utf-8"))
        data.update(original_report_sha256=data["report_sha256"], correction_confirmed=True)
        corrected = target / "level-3-corrected.md"
        corrected.write_text(report or self.flag_report(), encoding="utf-8")
        data["report_sha256"] = hashlib.sha256(corrected.read_bytes()).hexdigest()
        receipt = target / "receipt-corrected.json"
        receipt.write_text(json.dumps(data), encoding="utf-8")
        return corrected, receipt

    def test_preflight_is_read_only_and_explains_quote_variations(self):
        reports = [self.flag_report().replace("Quote:", "Quote (sentence 1):"),
                   self.flag_report().replace("Quote:", "Quote (paragraph 1, sentence 1):"),
                   self.flag_report().replace(f"Quote: {TRACE_SECOND}", f"Quote: {TRACE_SECOND}\nQuote: {TRACE_SECOND}"),
                   self.flag_report()]
        for index, report in enumerate(reports):
            with self.subTest(index=index):
                target, _ = self.prepare(TRACE_SECTION)
                receipt = self.handoff(target, report=report)
                before = self.snapshot(target)
                result = preflight_report(target, "level-3", receipt)
                self.assertEqual(result["can_accept"], index == 3)
                if index != 3:
                    self.assertIn("one literal Quote:", result["correction"])
                    self.assertTrue(result["recoverable_report"])
                self.assertEqual(self.snapshot(target), before)

    def test_format_recovery_preserves_originals_and_needs_no_new_checker(self):
        target, _ = self.prepare(TRACE_SECTION)
        receipt = self.handoff(target, report=self.flag_report().replace("Quote:", "Quote (sentence 1):"))
        original, original_receipt = (target / "level-3.md").read_bytes(), receipt.read_bytes()
        self.assert_stops(target, "level-3", receipt)
        corrected, correction_receipt = self.correction(target, receipt)
        before = self.snapshot(target)
        self.assertTrue(preflight_report(target, "level-3", correction_receipt, report_path=corrected, resume=True)["can_accept"])
        self.assertEqual(self.snapshot(target), before)
        state = accept_report(target, "level-3", correction_receipt, report_path=corrected, resume=True)
        self.assertEqual(state["next_task"], "full-level-4")
        self.assertEqual(len(state["completed_tasks"]), 1)
        self.assertEqual(state["completed_tasks"][0]["report_file"], corrected.name)
        self.assertNotIn("error_type", state)
        self.assertEqual(state["completed_tasks"][0]["original_report_file"], "level-3.md")
        self.assertEqual(state["completed_tasks"][0]["correction_of_report_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual((target / "level-3.md").read_bytes(), original)
        self.assertEqual(receipt.read_bytes(), original_receipt)
        before = self.snapshot(target)
        accept_report(target, "level-3", correction_receipt)
        self.assertEqual(self.snapshot(target), before)

    def test_recovery_rejects_unconfirmed_new_executor_or_corrupt_correction(self):
        for change in ({"correction_confirmed": False}, {"original_report_sha256": "wrong"},
                       {"executor_id": "a-new-checker"}, {"total_tokens": 999}, {"bad_quote": True}):
            with self.subTest(change=change):
                target, _ = self.prepare(TRACE_SECTION)
                receipt = self.handoff(target, report=self.flag_report().replace("Quote:", "Quote (sentence 1):"))
                self.assert_stops(target, "level-3", receipt)
                corrected, correction_receipt = self.correction(target, receipt,
                    self.flag_report(quote="Words absent from the fictional section.") if change.get("bad_quote") else None)
                data = json.loads(correction_receipt.read_text(encoding="utf-8"))
                data.update({k: v for k, v in change.items() if k != "bad_quote"})
                correction_receipt.write_text(json.dumps(data), encoding="utf-8")
                before = self.snapshot(target)
                with self.assertRaises(TrialStopped):
                    accept_report(target, "level-3", correction_receipt, report_path=corrected, resume=True)
                self.assertEqual(self.snapshot(target), before)

    def test_recovery_never_bypasses_changed_original_input_or_incomplete_receipt(self):
        for mutation in ("level-3.md", "section.md", "bundle-level-3.json", "incomplete_receipt"):
            with self.subTest(mutation=mutation):
                target, _ = self.prepare(TRACE_SECTION)
                receipt = self.handoff(target, report=self.flag_report().replace("Quote:", "Quote (sentence 1):"),
                                       receipt={"completion_confirmed": False} if mutation == "incomplete_receipt" else None)
                self.assert_stops(target, "level-3", receipt)
                corrected, correction_receipt = self.correction(target, receipt)
                if mutation != "incomplete_receipt":
                    with (target / mutation).open("a", encoding="utf-8") as changed:
                        changed.write("Changed fictional artifact.")
                before = self.snapshot(target)
                self.assertFalse(preflight_report(target, "level-3", correction_receipt, report_path=corrected, resume=True)["can_accept"])
                with self.assertRaises(TrialStopped):
                    accept_report(target, "level-3", correction_receipt, report_path=corrected, resume=True)
                self.assertEqual(self.snapshot(target), before)

    def test_mechanical_recovery_cannot_drop_or_rewrite_original_judgments(self):
        for corrected_report in (self.report(), self.flag_report().replace("Supply the fictional premise.", "Change the invented conclusion.")):
            with self.subTest(corrected_report=corrected_report):
                target, _ = self.prepare(TRACE_SECTION)
                receipt = self.handoff(target, report=self.flag_report().replace("Quote:", "Quote (sentence 1):"))
                self.assert_stops(target, "level-3", receipt)
                corrected, correction_receipt = self.correction(target, receipt, corrected_report)
                before = self.snapshot(target)
                with self.assertRaisesRegex(TrialStopped, "preserve every original finding"):
                    accept_report(target, "level-3", correction_receipt, report_path=corrected, resume=True)
                self.assertEqual(self.snapshot(target), before)

    def test_accepted_handoff_reuse_is_read_only_even_after_completion(self):
        target, _ = self.prepare()
        first = self.handoff(target)
        accept_report(target, "level-3", first)
        second = self.handoff(target, "full-level-4")
        accept_report(target, "full-level-4", second)
        before = self.snapshot(target)
        for label, receipt in (("level-3", first), ("full-level-4", second)):
            self.assertEqual(preflight_report(target, label, receipt)["status"], "already_accepted")
            accept_report(target, label, receipt)
        self.assertEqual(self.snapshot(target), before)
        data = json.loads(first.read_text(encoding="utf-8"))
        data["elapsed_seconds"] = 123
        first.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(TrialStopped):
            accept_report(target, "level-3", first)
        self.assertEqual(self.snapshot(target), before)

    def test_reuse_requires_same_input_configuration_and_untouched_artifacts(self):
        for mutation in (None, "source", "configuration", "bundle-level-3.json", "task-level-3.md"):
            with self.subTest(mutation=mutation):
                target, state = self.prepare()
                source = self.root / f"input-{self.number}.md"
                if mutation == "source":
                    source.write_text(SECTION + "Changed fictional text.", encoding="utf-8")
                elif mutation not in (None, "configuration"):
                    with (target / mutation).open("a", encoding="utf-8") as changed:
                        changed.write("Changed fictional artifact.")
                before = self.snapshot(target)
                if mutation is None:
                    with patch("runner.section_trial.parse_draft", side_effect=AssertionError("Preparation reran")):
                        self.assertEqual(section_trial(source, target, reuse=True), state)
                elif mutation == "configuration":
                    with patch("runner.section_trial._preparation_fingerprint", return_value="new-configuration"):
                        with self.assertRaises(TrialStopped):
                            section_trial(source, target, reuse=True)
                else:
                    with self.assertRaises(TrialStopped):
                        section_trial(source, target, reuse=True)
                self.assertEqual(self.snapshot(target), before)

    def test_cli_preflight_prints_actionable_failure_without_stopping(self):
        target, _ = self.prepare(TRACE_SECTION)
        receipt = self.handoff(target, report=self.flag_report().replace("Quote:", "Quote (sentence 1):"))
        before = self.snapshot(target)
        with patch("sys.argv", ["section_trial", "--preflight", "level-3", "--out", str(target), "--receipt", str(receipt)]), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 2)
        self.assertIn("one literal Quote:", output.getvalue())
        self.assertEqual(self.snapshot(target), before)

    def test_horizontal_handoff_preserves_independent_findings_and_reuses_exact_snapshot(self):
        target, _ = self.prepare(TRACE_SECTION)
        accept_report(target, "level-3", self.handoff(target, report=self.flag_report()))
        before = self.snapshot(target)
        with self.assertRaises(TrialStopped):
            prepare_verification(target)
        self.assertEqual(self.snapshot(target), before)
        accept_report(target, "full-level-4", self.handoff(target, "full-level-4", report=self.flag_report(label="full-level-4", rule="4.1")))
        original = self.snapshot(target)
        result = prepare_verification(target)
        self.assertEqual(result["findings"], 2)
        self.assertFalse(result["semantic_verification_executed"])
        bundle = json.loads((target / "verification-bundle.json").read_text(encoding="utf-8"))
        self.assertEqual([row["id"] for row in bundle["findings"]], ["level-3:1", "full-level-4:1"])
        self.assertEqual({name: (target / name).read_bytes() for name in original}, original)
        before = self.snapshot(target)
        self.assertEqual(prepare_verification(target)["status"], "reused")
        self.assertEqual(self.snapshot(target), before)
        response = [{"id": "level-3:1", "disposition": "context_needed", "related_ids": [], "rationale": "Needs fictional context."},
                    {"id": "full-level-4:1", "disposition": "duplicate", "related_ids": ["level-3:1"], "rationale": "Same fictional question."}]
        response_path = self.root / "verification-response.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")
        self.assertFalse(preflight_verification(target, response_path)["semantic_correctness_validated"])
        self.assertEqual(self.snapshot(target), before)
        (target / "flags-level-3.json").write_text("{}", encoding="utf-8")
        before = self.snapshot(target)
        with self.assertRaises(TrialStopped):
            prepare_verification(target)
        self.assertEqual(self.snapshot(target), before)

    def test_horizontal_response_rejects_omissions_invented_ids_cycles_and_one_sided_conflicts(self):
        bundle = {"findings": [{"id": "a"}, {"id": "b"}]}
        retained = {"id": "a", "disposition": "retain", "related_ids": [], "rationale": "Fictional reason."}
        other = {**retained, "id": "b"}
        invalid = [[], [retained], [retained, retained], [retained, {**other, "id": "invented"}],
                   [retained, {**other, "disposition": "duplicate", "related_ids": ["invented"]}],
                   [{**retained, "disposition": "duplicate", "related_ids": ["b"]}, {**other, "disposition": "duplicate", "related_ids": ["a"]}],
                   [{**retained, "disposition": "conflict", "related_ids": ["b"]}, other],
                   [retained, {**other, "rationale": ""}], [retained, {**other, "disposition": "discard"}]]
        for response in invalid:
            with self.subTest(response=response), self.assertRaises(TrialStopped):
                validate_reconciliation(bundle, response)
        response = [{**retained, "disposition": "conflict", "related_ids": ["b"]},
                    {**other, "disposition": "conflict", "related_ids": ["a"]}]
        self.assertEqual(validate_reconciliation(bundle, response)["finding_count"], 2)
        self.assertEqual(validate_reconciliation({"findings": []}, [])["finding_count"], 0)

    def test_replaced_artifact_symlink_is_rejected_before_reading_outside_temp(self):
        target, _ = self.prepare()
        receipt = self.handoff(target)
        section = target / "section.md"
        section.unlink()
        try:
            section.symlink_to(Path(__file__).resolve())
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        # Receipt/report hashes are safe; the replaced section must fail before hashing.
        from runner.section_trial import _sha as real_sha
        def guarded_sha(path):
            self.assertNotEqual(Path(path).resolve(), Path(__file__).resolve())
            return real_sha(path)
        before = (target / "trial.json").read_bytes()
        with patch("runner.section_trial._sha", side_effect=guarded_sha):
            result = preflight_report(target, "level-3", receipt)
        self.assertFalse(result["can_accept"])
        self.assertEqual((target / "trial.json").read_bytes(), before)

    def test_combined_levels_and_findings_outside_gated_scope_are_rejected(self):
        target, _ = self.prepare(TRACE_SECTION)
        receipt = self.handoff(target, report=self.report().replace("### Pass down", "## Level 4\n\n### Pass down"))
        self.assertFalse(preflight_report(target, "level-3", receipt)["can_accept"])
        gate = f'- Lantern topic | "{TRACE_FIRST}" | Check its fictional detail.'
        accept_report(target, "level-3", self.handoff(target, report=self.report(gate=gate)))
        accept_report(target, "full-level-4", self.handoff(target, "full-level-4"))
        receipt = self.handoff(target, "gated-level-4", report=self.flag_report(label="gated-level-4", rule="4.1"))
        before = self.snapshot(target)
        result = preflight_report(target, "gated-level-4", receipt)
        self.assertFalse(result["can_accept"])
        self.assertIn("outside this task", result["correction"])
        self.assertEqual(self.snapshot(target), before)
