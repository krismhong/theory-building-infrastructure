"""Prepare tasks or accept adapter receipts; never dispatch model/API calls."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.prompts import ROOT
from runner.cascade import ensure_new_run
from runner.section_trial import TrialStopped, accept_report, preflight_report, private_path, section_trial
from runner.verification import preflight_verification, prepare_verification


def main():
    parser = argparse.ArgumentParser(description="Prepare a private section trial with no model/API calls.")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--input", type=Path, help="a user-selected section file already under local Temp")
    choice.add_argument("--fictional", action="store_true", help="use a section of the existing invented fixture")
    choice.add_argument("--accept", choices=("level-3", "full-level-4", "gated-level-4"))
    choice.add_argument("--preflight", choices=("level-3", "full-level-4", "gated-level-4"))
    choice.add_argument("--verification", action="store_true", help="prepare a horizontal handoff; never execute it")
    parser.add_argument("--out", type=Path, required=True, help="an unused run folder under local Temp")
    parser.add_argument("--receipt", type=Path, help="the external adapter's local completion receipt")
    parser.add_argument("--report", type=Path, help="a separate corrected report in the run folder")
    parser.add_argument("--resume", action="store_true", help="explicitly recover a recorded report-contract failure")
    parser.add_argument("--reuse", action="store_true", help="reuse unchanged input/configuration in this same run")
    parser.add_argument("--verification-response", type=Path, help="preflight an existing verifier response without dispatch")
    args = parser.parse_args()
    if (args.accept or args.preflight) and not args.receipt:
        parser.error("--accept/--preflight requires --receipt")
    if (args.report or args.resume) and not (args.accept or args.preflight):
        parser.error("--report/--resume requires --accept or --preflight")
    if args.reuse and not (args.input or args.fictional):
        parser.error("--reuse requires --input or --fictional")
    if args.verification_response and not args.verification:
        parser.error("--verification-response requires --verification")
    started = time.perf_counter()
    try:
        if args.preflight:
            result = preflight_report(args.out, args.preflight, args.receipt, report_path=args.report, resume=args.resume)
            print(json.dumps(result, ensure_ascii=True))
            return 0 if result["can_accept"] else 2
        if args.verification:
            result = (preflight_verification(args.out, args.verification_response) if args.verification_response
                      else prepare_verification(args.out))
            print(json.dumps(result, ensure_ascii=True))
            return 0
        if args.accept:
            state = accept_report(args.out, args.accept, args.receipt, report_path=args.report, resume=args.resume)
            print("Report accepted. Next task: " + (state["next_task"] or "none; trial complete"))
            print(f"Local coordinator operation: {time.perf_counter() - started:.6f} seconds.")
            return 0
        source = args.input
        if args.fictional:
            target = private_path(args.out)
            if not args.reuse:
                ensure_new_run(target)
            source = target.parent / "fictional-section.md"
            original = (ROOT / "examples" / "sample-draft.md").read_text(encoding="utf-8")
            section = "## Slack Time as the Condition for Reflection\n\n" + original.split("## Slack Time as the Condition for Reflection", 1)[1].split("## References", 1)[0].strip() + "\n"
            target.parent.mkdir(parents=True, exist_ok=True)
            if not source.exists():
                source.write_text(section, encoding="utf-8")
            elif source.read_text(encoding="utf-8") != section:
                raise TrialStopped("Existing input was preserved.")
        state = section_trial(source, args.out, reuse=args.reuse)
    except (TrialStopped, FileExistsError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Trial blocked: {error}")
        return 2
    print("Tasks prepared or reused. Next task: " + (state["next_task"] or "none") + ". No model/API calls or semantic checks were made.")
    print(f"Local coordinator operation: {time.perf_counter() - started:.6f} seconds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
