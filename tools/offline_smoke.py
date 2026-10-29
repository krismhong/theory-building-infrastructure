"""Reproduce engineering checks on synthetic inputs with network access guarded.

Run from the candidate root: python -B tools/offline_smoke.py
No provider is instantiated except StubProvider and mocked constructors in tests.
All generated tasks, reports and receipts stay in a fresh local Temp directory.
Reports below are scripted contract fixtures, not model or scientific judgments.
"""
import contextlib
import hashlib
import io
import json
import platform
import socket
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runner.__main__ import main as cli
from runner.cascade import write_bundles
from runner.prompts import Options
from runner.section_trial import COMPLETE, accept_report, preflight_report, section_trial
from runner.verification import preflight_verification, prepare_verification
from tools.prepare_pilot import prepare


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_skip_reason(reason):
    """OS diagnostics can include usernames and absolute source/target paths."""
    if "WinError 1314" in reason:
        return "Windows symlink creation unavailable: WinError 1314 (required privilege missing)."
    return "Test skipped; diagnostic text omitted from the shareable summary."


def run():
    result = {"kind": "offline engineering checks, not semantic validation",
              "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "platform": platform.system(),
              "provider_api_calls": 0, "network_attempts_blocked": 0,
              "semantic_validation_executed": False}
    def blocked(*args, **kwargs):
        result["network_attempts_blocked"] += 1
        raise AssertionError("Network is forbidden in this offline check.")

    with contextlib.ExitStack() as stack:
        for name in ("socket.socket.connect", "socket.socket.connect_ex",
                     "socket.create_connection", "socket.getaddrinfo"):
            stack.enter_context(patch(name, side_effect=blocked))
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        stream = io.StringIO()
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            tests = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
        result["unit_tests"] = {"run": tests.testsRun, "passed": tests.testsRun-len(tests.skipped)-len(tests.failures)-len(tests.errors),
                                "failures": len(tests.failures), "errors": len(tests.errors),
                                "skipped": [{"test": str(test), "reason": public_skip_reason(reason)} for test, reason in tests.skipped],
                                "seconds": round(time.perf_counter()-started, 6)}
        if not tests.wasSuccessful():
            # Failure details stay local; terminal summary does not expose user paths.
            result["status"] = "failed_unit_tests"
            result["failed_tests"] = [str(test) for test, _ in tests.failures+tests.errors]
            return result

        with tempfile.TemporaryDirectory(prefix="logic-public-smoke-") as temp:
            root = Path(temp)
            draft = ROOT / "examples" / "sample-draft.md"
            with contextlib.redirect_stdout(io.StringIO()):
                assert cli(["check", str(draft), "--out", str(root/"stub"), "--provider", "stub", "--split", "never"]) == 0
                assert cli(["script", str(draft), "--out", str(root/"script")]) == 0
            run_log = json.loads((root/"stub"/"run.json").read_text(encoding="utf-8"))
            result["stub_cli"] = {"status": "passed", "provider": run_log["provider"],
                                  "level_reports": len(list((root/"stub").glob("level-[1-5].md"))),
                                  "decisions_written": (root/"stub"/"decisions.json").is_file()}
            result["regex_cli"] = {"status": "passed", "report_written": (root/"script"/"level-S.md").is_file()}
            assert result["stub_cli"]["provider"] == "stub"
            assert result["stub_cli"]["level_reports"] == 5 and result["stub_cli"]["decisions_written"]
            assert result["regex_cli"]["report_written"]
            bundles = write_bundles(draft, root/"bundles", "all", Options(split="never"))
            result["independent_bundles"] = {"status": "passed", "jobs": len(bundles)}
            assert len(bundles) == 5
            pilot = prepare(root/"pilot")
            result["synthetic_pilot_preparation"] = {"status": "passed", "prepared_requests": len(pilot["prepared_requests"]),
                "prompt_utf8_bytes": sum(row["prompt_utf8_bytes"] for row in pilot["prepared_requests"]),
                "requests": pilot["prepared_requests"], "dispatch": pilot["dispatch"],
                "plan_usage": None, "external_calls": pilot["external_calls"]}
            assert len(pilot["prepared_requests"]) == 5 and pilot["external_calls"] == 0

            source = root/"synthetic-section.md"
            quote = "Invented lanterns illuminate the empty model village."
            source.write_text("## Synthetic lanterns\n\n"+quote+"\nPainted windows remain closed.\n", encoding="utf-8")
            trial = root/"trial"
            section_trial(source, trial)
            preserved = {}
            for label, level, rule in (("level-3", "3", "3.2"), ("full-level-4", "4", "4.4")):
                report = trial/(label+".md")
                report.write_text(f'## Level {level}\n\n[ISSUE:] Rule {rule}. Location: Synthetic lanterns, paragraph 1, sentence 1\n'
                    f'Quote: "{quote}"\nWhat fails: Scripted contract fixture; no semantic judgment was made.\n'
                    'Decision: Confirm the invented fixture choice?\nKind: slip\n\n### Pass down\nNone\n\n'
                    '### Summary\nSynthetic contract fixture finished.\n\n'+COMPLETE+'\n', encoding="utf-8")
                preserved[label] = digest(report)
                receipt = root/(label+"-receipt.json")
                receipt.write_text(json.dumps({"status": "completed", "completion_confirmed": True,
                    "backend": "scripted-offline-fixture", "executor_id": label, "model": "not-a-model",
                    "task": label, "report_sha256": digest(report)}), encoding="utf-8")
                assert preflight_report(trial, label, receipt)["can_accept"]
                state = accept_report(trial, label, receipt)
            assert state["status"] == "complete"
            prepared = prepare_verification(trial)
            bundle = json.loads((trial/"verification-bundle.json").read_text(encoding="utf-8"))
            response = trial/"verification-response.json"
            response.write_text(json.dumps([{"id": row["id"], "disposition": "unresolved", "related_ids": [],
                "rationale": "Scripted structural smoke only; no semantic judgment or model execution."}
                for row in bundle["findings"]]), encoding="utf-8")
            verdict = preflight_verification(trial, response)
            assert verdict["status"] == "contract_valid" and verdict["finding_count"] == 2
            assert all(digest(trial/(label+".md")) == value for label, value in preserved.items())
            assert all(row["elapsed_seconds"] is None and row["input_tokens"] is None
                       and row["output_tokens"] is None for row in state["completed_tasks"])
            result["bounded_section_and_horizontal_contract"] = {"status": "passed", "accepted_scripted_reports": 2,
                "gated_task": "skipped: explicit None gate", "scripted_findings": prepared["findings"],
                "reconciliation": verdict, "raw_reports_preserved": True, "executor_usage": None}
    assert result["network_attempts_blocked"] == 0
    result["status"] = "passed"
    result["generated_outputs"] = "fresh local Temp directory, removed after check"
    return result


if __name__ == "__main__":
    try:
        outcome = run()
    except Exception as error:
        outcome = {"status": "failed_smoke", "error_type": type(error).__name__, "provider_api_calls": 0,
                   "detail": "Inspect the local failure before proceeding; paths omitted from terminal summary."}
    print(json.dumps(outcome, indent=2, ensure_ascii=True))
    raise SystemExit(0 if outcome["status"] == "passed" else 1)
