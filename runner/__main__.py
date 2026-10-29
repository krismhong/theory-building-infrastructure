"""Command line for the levels of logic. Run `python -m runner --help` for the commands."""

import argparse
import sys
from pathlib import Path

from .cascade import Options, compatible_ruleset, ensure_new_run, merge_directory, run_cascade, run_recheck, write_bundles, write_routes, write_script
from .providers import AnthropicProvider, OpenAICompatibleProvider, StubProvider
from .report_contract import ReportContractError
from .revise import apply_proposals, learn, read_rulings


def _confirm_interactively(model_text: str) -> str:
    print("\nHere is the model Level 1 read:\n")
    print(model_text)
    print("\nPress Enter if it is correct, or type a corrected model (finish with an empty line):")
    lines = []
    for line in sys.stdin:
        if not line.strip():
            break
        lines.append(line.rstrip("\n"))
    return "\n".join(lines) if lines else model_text


def _layers(p: argparse.ArgumentParser) -> None:
    p.add_argument("--genre", type=Path, help="optional interpretation context; theory, empirical, or none")
    p.add_argument("--outlet", type=Path, help="legacy optional context; prefer --project; never adds core criteria")
    p.add_argument("--personal", type=Path, help="your personal-layer file")
    p.add_argument("--project", type=Path, help="this paper's project layer; default: project.md beside the run folders, if present")
    p.add_argument("--sources", type=Path, help="a file of source records for Level 5")
    p.add_argument("--model-file", type=Path, help="your confirmed model (rule 1.0); default: model.md beside the run folders, if present")
    p.add_argument("--rulings", type=Path, help="your rulings; default: rulings.md beside the run folders, if present")
    p.add_argument("--full", action="store_true", help="Level 4 on every paragraph, not only those Level 3 passes down")
    p.add_argument("--gated", action="store_true", help="first rounds: Level 3 decides where Level 4 looks, and Level 4 where Level 5 looks "
                   "(fewer tokens, slower); the default runs all five levels at once")
    p.add_argument("--split", choices=["auto", "always", "never"], default="auto", help="one Level 4 and Level 5 checker per section")
    p.add_argument("--digest", action="store_true", help="show only CRITICAL points and points raised at two or more levels")
    p.add_argument("--organize", action="store_true", help="after the checkers, the organizer routes each flag to the checkers below it, "
                   "which say whether their flags follow from it (for check and recheck; agents use route)")


def _nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def _positive_int(value: str) -> int:
    number = _nonnegative_int(value)
    if number == 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _provider(p: argparse.ArgumentParser) -> None:
    p.add_argument("--provider", choices=["anthropic", "openai-compatible", "stub"], help="explicit adapter choice; agent workflow uses bundle/merge instead")
    p.add_argument("--model", help="required model name for an explicitly chosen live adapter")
    p.add_argument("--base-url", help="required endpoint for openai-compatible; no hosted endpoint assumed")
    p.add_argument("--api-key-env", default="OPENAI_API_KEY", help="environment variable holding the key, for openai-compatible endpoints")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], help="optional anthropic reasoning effort; requires model support")
    p.add_argument("--no-fallback", action="store_true", help="legacy compatibility option; fallback is always disabled")
    p.add_argument("--max-tokens", type=_positive_int, help="maximum generated tokens per call, including thinking when the provider counts it")
    p.add_argument("--retries", type=_nonnegative_int, help="provider retries per request; use 0 for a bounded pilot")


def _options(args, out: Path) -> Options:
    beside = out.resolve().parent
    model_file = args.model_file or (beside / "model.md" if (beside / "model.md").exists() else None)
    project = args.project or (beside / "project.md" if (beside / "project.md").exists() else None)
    return Options(genre=args.genre, outlet=args.outlet, personal=args.personal, project=project, sources=args.sources, model_file=model_file,
                   word_choice=getattr(args, "word_choice", False), full=args.full, parallel=not args.gated, split=args.split, digest=args.digest,
                   organize=args.organize,
                   confirm_model=_confirm_interactively if getattr(args, "confirm_model", False) else None)


def _rulings(args, out: Path) -> Path | None:
    beside = out.resolve().parent / "rulings.md"
    return args.rulings or (beside if beside.exists() else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runner", description="Check the logic of a draft, level by level.")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="run the five levels on a Markdown draft")
    check.add_argument("draft", type=Path)
    check.add_argument("--out", type=Path, required=True, help="the run folder (for example logic-check/my-paper/run-01)")
    check.add_argument("--word-choice", action="store_true", help="also run the optional word-choice pass")
    check.add_argument("--confirm-model", action="store_true", help="show Level 1's reading of the model and confirm it before the checks")
    _layers(check); _provider(check)

    recheck = sub.add_parser("recheck", help="after a revision, recheck only what changed, one level up and down")
    recheck.add_argument("draft", type=Path)
    recheck.add_argument("--from", dest="prev", type=Path, required=True, help="the previous run folder")
    recheck.add_argument("--out", type=Path, required=True, help="the new run folder")
    _layers(recheck); _provider(recheck)

    script = sub.add_parser("script", help="run only the script checks (instant, no model)")
    script.add_argument("draft", type=Path)
    script.add_argument("--out", type=Path, required=True)
    script.add_argument("--personal", type=Path)
    script.add_argument("--project", type=Path)

    bundle = sub.add_parser("bundle", help="for any agent: prepare one file per checker; no API call")
    bundle.add_argument("draft", type=Path)
    bundle.add_argument("--out", type=Path, required=True)
    bundle.add_argument("--level", required=True, help="1,2,3 (together), 4, 5, or W, in that order; or all (every level at once, full coverage)")
    bundle.add_argument("--from", dest="prev", type=Path, help="the previous run folder, for a recheck")
    _layers(bundle)

    merge = sub.add_parser("merge", help="merge the reports in a run folder into decisions.md")
    merge.add_argument("report_dir", type=Path)
    merge.add_argument("--draft", type=Path, help="the draft (default: draft.md in the run folder)")
    merge.add_argument("--from", dest="prev", type=Path, help="the previous run folder, for a recheck")
    _layers(merge)

    route = sub.add_parser("route", help="the coordinator's next messages, once the checkers of a round have reported "
                           "(first each checker's flags above its own, then any disputes)")
    route.add_argument("report_dir", type=Path)
    route.add_argument("--draft", type=Path, help="the draft (default: draft.md in the run folder)")
    route.add_argument("--from", dest="prev", type=Path, help="the previous run folder, for a recheck")
    _layers(route)

    learn_cmd = sub.add_parser("learn", help="propose changes to your personal layer from your rulings")
    learn_cmd.add_argument("runs", type=Path, nargs="+", help="run folders whose decisions you ruled on")
    learn_cmd.add_argument("--rulings", type=Path, required=True)
    learn_cmd.add_argument("--personal", type=Path, help="your personal-layer file, for --apply")
    learn_cmd.add_argument("--apply", action="store_true", help="write the proposals into the personal layer")

    args = parser.parse_args(argv)
    if args.command == "script":
        print(write_script(args.draft, args.out, Options(personal=args.personal, project=args.project)))
        return 0
    if args.command == "bundle":
        for bundle_path, report in write_bundles(args.draft, args.out, args.level.replace(" ", ""), _options(args, args.out), args.prev):
            print(f"{bundle_path} -> {report}")
        return 0
    if args.command == "route":
        written = write_routes(args.report_dir, args.draft, _options(args, args.report_dir), _rulings(args, args.report_dir), args.prev)
        for report, message, reply, bundle in written:
            print(f"{report} : {message} -> {reply}" + (f" (bundle {bundle})" if bundle.exists() else ""))
        if not written:
            print("Nothing to route: every message has its reply. Merge next.")
        return 0
    if args.command == "merge":
        try:
            print(merge_directory(args.report_dir, args.draft, _options(args, args.report_dir), _rulings(args, args.report_dir), args.prev))
        except ReportContractError as error:
            parser.error(str(error))
        return 0
    if args.command == "learn":
        proposals = learn(read_rulings(args.rulings), [r / "decisions.json" for r in args.runs if (r / "decisions.json").exists()])
        if not proposals:
            print("No proposals: no rule has been ruled a matter of taste often enough.")
            return 0
        for p in proposals:
            print(p.line)
            for example in p.examples[:3]:
                print(f"    e.g. \"{example}\"")
        if args.apply:
            if not args.personal:
                parser.error("--apply needs --personal")
            apply_proposals(args.personal, proposals)
            print(f"Written to {args.personal}")
        return 0

    try:
        ensure_new_run(args.out)
    except FileExistsError as error:
        parser.error(str(error))

    if not args.provider:
        parser.error("No API is assumed. For your agent follow AGENTS.md using bundle/merge. "
                     "Choose --provider stub for an offline dry-run, or explicitly select a live adapter.")
    if args.command == "recheck" and not compatible_ruleset(args.prev):
        parser.error("Previous ruleset is missing or changed. Prepare a fresh check; no automatic scope expansion or carryover.")
    if args.provider != "stub" and not args.model:
        parser.error("--model is required for a live adapter")
    if args.provider == "openai-compatible" and not args.base_url:
        parser.error("--base-url is required; no hosted endpoint is assumed")
    limits = {name: getattr(args, name) for name in ("max_tokens", "retries") if getattr(args, name) is not None}
    if args.provider == "anthropic":
        provider = AnthropicProvider(model=args.model, effort=args.effort, fallback=False, **limits)
    elif args.provider == "openai-compatible":
        if not args.model:
            parser.error("--model is required for openai-compatible endpoints")
        provider = OpenAICompatibleProvider(model=args.model, base_url=args.base_url, api_key_env=args.api_key_env, **limits)
    else:
        provider = StubProvider()
    options = _options(args, args.out)
    if args.command == "recheck":
        run_recheck(args.prev, args.draft, args.out, provider, options, _rulings(args, args.out))
    else:
        run_cascade(args.draft, args.out, provider, options, _rulings(args, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
