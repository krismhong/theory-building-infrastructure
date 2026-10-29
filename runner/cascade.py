"""Run a check, or a recheck after a revision, and merge what the checkers find into decisions for the author.

A first round, by default: the script pass, then all five levels at once, with Level 4 checking every paragraph's sentences
against that paragraph's own topic sentence and Level 5 checking every clause, so the round takes as long as its slowest
checker. The gated alternative costs fewer tokens and takes longer: Levels 1 to 3 on the whole draft, Level 4 on the
paragraphs Level 3 passes down, Level 5 on the sentences Level 4 passes down plus every cited clause. Levels 4 and 5 split
into one checker per section, run in parallel, when their material is long.

A recheck (`run_recheck`): only what the revision touched, one level up and down from each change (see revise.py), with
every other decision point carried forward and the author's rulings applied.
"""

import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from .draft import Paragraph, is_references, parse_draft
from .flags import (assign_flag_ids, is_open, merge_flags, parse_flags, parse_pass_down, points_from_json, points_to_json,
                    render_decisions)
from .mechanical import script_pass
from .organize import (dispute_list, dispute_text, disputes_by_report, flag_index, parse_answers, parse_reply, render_organized, resolve,
                       route_text, routes)
from .prompts import (ROOT, Job, Options, _read, build_system, bundle_text, job_level_3_sections, job_word_choice,
                      jobs_level_4, jobs_level_5, jobs_levels_1_to_3, ruleset_metadata)
from .providers import Completion, checked_completion
from .report_contract import (ReportContractError, digest, prepare_input, read_jobs, receipt_for,
                              register_jobs, validate_report, validate_run, write_json)
from .revise import apply_rulings, carry_forward, mark_moved_up, plan_recheck, read_priorities, read_rulings

__all__ = ["ROOT", "Options", "build_system", "run_cascade", "run_recheck", "merge_directory", "write_bundles",
           "write_routes", "ensure_new_run"]


def ensure_new_run(out_dir: Path) -> None:
    """Reject a nonempty run folder before writing reports or calling a model.

    The merge reads every level report in the folder, so reusing it could silently mix
    an earlier round's reports with the new ones. Bundle, merge, and route commands
    deliberately work within an existing round and do not use this check.
    """
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"Run folder is not empty: {out_dir}. Choose a new --out folder; existing files were kept.")


def _text(path: Path | None) -> str:
    return _read(path) if path and Path(path).exists() else ""


def compatible_ruleset(run_dir: Path) -> bool:
    path = run_dir / "ruleset.json"
    return path.exists() and json.loads(_read(path)) == ruleset_metadata()


def _record_ruleset(run_dir: Path, *, allow_legacy_processing: bool = False) -> None:
    path = run_dir / "ruleset.json"
    if path.exists() and not compatible_ruleset(run_dir):
        raise ValueError("Ruleset changed; preserve this run and start a fresh output folder.")
    if not path.exists() and not allow_legacy_processing:
        if list(run_dir.glob("level-[1-5]*.md")) or list(run_dir.glob("bundle-*")):
            raise ValueError("Unversioned tasks or reports already exist; preserve them and use a fresh folder.")
    path.write_text(json.dumps(ruleset_metadata(), indent=2) + "\n", encoding="utf-8")


def level_of(label: str) -> str:
    return label.split("-", 1)[0]


def passed_down_paragraphs(draft, report: str, exclude: set[int] = frozenset()) -> list[tuple[Paragraph, str]]:
    items = []
    for item in parse_pass_down(report):
        paragraph = draft.find_paragraph(item)
        if paragraph and paragraph.index not in exclude and not is_references(paragraph.section):
            items.append((paragraph, f"Level 3's note: {item}"))
            exclude = set(exclude) | {paragraph.index}
    return items


def all_paragraphs(draft) -> list[tuple[Paragraph, str]]:
    return [(p, "Every paragraph is checked (full coverage).") for p in draft.paragraphs
            if not is_references(p.section) and p.section != "(front matter)"]


class _Runner:
    """Calls the checkers for a list of jobs in parallel and keeps their reports, timings, and served models."""

    def __init__(self, provider, options: Options, log: Callable[[str], None], out_dir: Path):
        self.provider, self.options, self.log = provider, options, log
        self.out_dir = out_dir
        self.lock = threading.Lock()
        self.reports: dict[str, str] = {}
        self.meta: dict[str, dict] = {}
        self.jobs: list[Job] = []

    def persist(self, status="running") -> None:
        write_json(self.out_dir / "execution.json", {"status": status, "levels": self.meta})

    def run(self, jobs: list[Job]) -> None:
        register_jobs(self.out_dir, jobs, self.options)
        if not jobs:
            return
        self.jobs.extend(jobs)
        for job in jobs:
            self.meta[job.label] = {"status": "pending", "reason": job.reason, "usage": None}
        self.persist()

        def call(job: Job) -> tuple[Job, Completion, float]:
            start = time.time()
            result = self.provider.complete(build_system(job.level, self.options), job.task)
            return job, result, round(time.time() - start, 1)

        failures = []
        with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
            futures = {pool.submit(call, job): job for job in jobs}
            for future in as_completed(futures):
                job, result = futures[future], None
                try:
                    _, result, seconds = future.result()
                    checked_completion(result)  # custom providers must meet the same completion contract
                    validate_report(result.text, job.level, _read(self.out_dir / "draft.md"))
                    report = self.out_dir / f"level-{job.label}.md"
                    report.write_text(result.text, encoding="utf-8")
                    write_json(self.out_dir / f"executor-{job.label}.json",
                               receipt_for(self.out_dir, job.label, result.served_model, result.stop_reason,
                                           result.usage, getattr(self.provider, "name", type(self.provider).__name__)))
                    self.reports[job.label] = result.text
                    self.meta[job.label] = {"status": "completed", "served_model": result.served_model,
                                            "stop_reason": result.stop_reason, "usage": result.usage,
                                            "seconds": seconds, "reason": job.reason}
                    self.log(f"Level {job.label} done ({seconds} s, served by {result.served_model})")
                except Exception as error:
                    result = getattr(error, "completion", result)
                    failed = {"status": "failed", "error_type": type(error).__name__, "usage": None,
                              "reason": job.reason}
                    if isinstance(result, Completion):
                        failed.update(served_model=result.served_model, stop_reason=result.stop_reason, usage=result.usage)
                        if isinstance(result.text, str):
                            partial = self.out_dir / f"incomplete-{job.label}.md"
                            partial.write_text(result.text, encoding="utf-8")
                            failed.update(partial_report=partial.name, partial_sha256=digest(partial))
                    if isinstance(error, ReportContractError):
                        failed["detail"] = str(error)
                    self.meta[job.label] = failed
                    failures.append(job.label)
                self.persist()  # main thread; every result, including later futures after a failure, is saved
        if failures:
            self.persist("failed")
            raise ReportContractError(f"Checker tasks failed: {', '.join(sorted(failures))}. See execution.json; no completed decisions were produced.")

    def level_reports(self, level: str) -> str:
        return "\n\n".join(self.reports[label] for label in sorted(self.reports) if level_of(label) == level)


def _write_reports(out_dir: Path, runner: _Runner) -> None:
    # Reports and expected-job metadata have already been durably written per result.
    runner.persist("ready_for_merge")


class _Round:
    """What a round's reports add up to, before the author's rulings: every flag, merged and named."""

    def __init__(self, draft_text: str, points: list, resolved: list[dict], new_flags: list, carried: list):
        self.draft_text, self.points, self.resolved, self.new_flags, self.carried = draft_text, points, resolved, new_flags, carried


def _collect(out_dir: Path, draft_path: Path, options: Options, prev_dir: Path | None) -> _Round:
    """Read the reports in out_dir (with carry-over from prev_dir, when rechecking), merge them into decision points, and
    name every flag. The same reports always give the same points and names."""
    if prev_dir and not compatible_ruleset(prev_dir):
        raise ValueError("Previous ruleset is missing or changed; start a fresh check without --from.")
    draft_text = _read(draft_path)
    if Path(draft_path).resolve() != (out_dir / "draft.md").resolve():
        shutil.copyfile(draft_path, out_dir / "draft.md")
    if options.model_file and Path(options.model_file).exists() and Path(options.model_file).resolve() != (out_dir / "model.md").resolve():
        shutil.copyfile(options.model_file, out_dir / "model.md")

    new_flags = []
    for path in sorted(out_dir.glob("level-*.md")):
        label = path.stem.split("-", 1)[1]
        new_flags.extend(parse_flags(_read(path), level_of(label), source=label))

    carried, resolved = [], []
    if prev_dir:
        old_points = points_from_json(_read(prev_dir / "decisions.json")) if (prev_dir / "decisions.json").exists() else []
        plan = plan_recheck(_text(prev_dir / "draft.md"), draft_text, _text(prev_dir / "model.md"), _text(options.model_file))
        jobs = json.loads(_read(out_dir / "jobs.json")) if (out_dir / "jobs.json").exists() else []
        rerun: dict[str, object] = {}
        for job in jobs:
            if not job["paragraphs"]:
                rerun[job["level"]] = "all"
            elif rerun.get(job["level"]) != "all":
                rerun.setdefault(job["level"], set()).update(job["paragraphs"])
        carried, resolved = carry_forward(old_points, draft_text, rerun, _text(prev_dir / "draft.md"))
        mark_moved_up(new_flags, old_points, plan, draft_text, _text(prev_dir / "draft.md"))
        (out_dir / "plan.md").write_text(plan.summary() + "\n", encoding="utf-8")

    points = merge_flags(new_flags + carried, draft_text)
    assign_flag_ids(points)
    return _Round(draft_text, points, resolved, new_flags, carried)


def earlier_roots(out_dir: Path, prev_dir: Path | None = None) -> dict[str, set[str]]:
    """The root questions of earlier rounds, by id, each with the flags it settled, so that a ruling on a root keeps
    settling those flags in later rounds. Earlier rounds are the other run folders beside this one, and prev_dir."""
    folders = {d.resolve() for d in out_dir.resolve().parent.iterdir() if d.is_dir()} if out_dir.resolve().parent.exists() else set()
    if prev_dir:
        folders.add(Path(prev_dir).resolve())
    folders.discard(out_dir.resolve())
    roots: dict[str, set[str]] = {}
    for folder in sorted(folders):
        path = folder / "decisions.json"
        if path.exists():
            try:
                data = json.loads(_read(path))
            except json.JSONDecodeError:
                continue
            for root in data.get("roots", []):
                roots.setdefault(root["id"], set()).update(root.get("keys", []))
    return roots


def _routed(out_dir: Path, rnd: _Round) -> dict:
    """What the organizer routed to each checker, as recorded when it routed (routes.json), in this round's flags."""
    index = flag_index(rnd.points)
    data = json.loads(_read(out_dir / "routes.json"))
    return {label: ([index[f][1] for f in item["own"] if f in index], [index[f][1] for f in item["higher"] if f in index])
            for label, item in data.items()}


def _organized(out_dir: Path, rnd: _Round):
    """What the checkers said after the organizer routed their flags, carried out, if the round was organized."""
    if not (out_dir / "routes.json").exists():
        return None
    routed = _routed(out_dir, rnd)
    replies = {p.stem.split("-", 1)[1]: parse_reply(_read(p)) for p in sorted(out_dir.glob("reply-*.md"))}
    answers = {p.stem.split("-", 2)[2]: parse_answers(_read(p)) for p in sorted(out_dir.glob("dispute-reply-*.md"))}
    rnd.points, organized = resolve(rnd.points, replies, answers, routed)
    return organized


def _require_complete(out_dir: Path, draft_path: Path, prev_dir: Path | None):
    try:
        jobs = validate_run(out_dir, draft_path, prev_dir)
    except (ReportContractError, OSError, ValueError) as error:
        write_json(out_dir / "merge-status.json", {"status": "incomplete", "error_type": type(error).__name__,
                   "detail": str(error), "decisions_current": False})
        # An earlier merged result is evidence, not a valid result for the changed run.
        execution_path = out_dir / "execution.json"
        try:
            previous_execution = json.loads(_read(execution_path)) if execution_path.exists() else None
        except (OSError, ValueError):
            previous_execution = {"levels": {}}
        for name in ("decisions.md", "decisions.json", "decisions-flat.md", "run.json", "execution.json"):
            path = out_dir / name
            if path.exists():
                archive = out_dir / (name + ".previous")
                number = 1
                while archive.exists():
                    archive = out_dir / (name + f".previous-{number}"); number += 1
                path.rename(archive)
        if previous_execution is not None:
            if not isinstance(previous_execution, dict):
                previous_execution = {"levels": {}}
            previous_execution.update(status="failed", reason="Merge preflight failed; prior status is archived.")
            write_json(execution_path, previous_execution)
        write_json(out_dir / "run.json", {"status": "incomplete", "decisions_current": False, "reason": "Merge preflight failed; prior status is archived."})
        raise
    return jobs


def _finish(out_dir: Path, draft_path: Path, options: Options, rulings_path: Path | None, prev_dir: Path | None,
            log: Callable[[str], None]) -> dict:
    """Merge the reports in out_dir (with carry-over from prev_dir, when rechecking) and write the decisions. When the round
    was organized, decisions.md opens with the root questions and decisions-flat.md keeps every flag as the checkers raised it."""
    jobs = _require_complete(out_dir, draft_path, prev_dir)
    rnd = _collect(out_dir, draft_path, options, prev_dir)
    organized = _organized(out_dir, rnd)
    roots = earlier_roots(out_dir, prev_dir)
    if organized:
        roots.update({r.id: set(r.keys) for r in organized.roots})
    points = rnd.points
    apply_rulings(points, read_rulings(rulings_path), roots)
    low = read_priorities(options.personal)
    if organized:
        (out_dir / "decisions.md").write_text(render_organized(points, organized, rnd.resolved, low, options.digest, rnd.draft_text), encoding="utf-8")
        (out_dir / "decisions-flat.md").write_text(render_decisions(points, rnd.resolved, low, title="Every flag, before organizing"), encoding="utf-8")
    else:
        (out_dir / "decisions.md").write_text(render_decisions(points, rnd.resolved, low, digest=options.digest), encoding="utf-8")
    (out_dir / "decisions.json").write_text(points_to_json(points, rnd.resolved, organized.to_json() if organized else None), encoding="utf-8")
    to_decide = sum(1 for p in points if any(is_open(f) for f in p.flags))
    summary = {
        "flags_new": len(rnd.new_flags), "flags_carried": len(rnd.carried), "decision_points": len(points), "to_decide": to_decide,
        "moved_up": sum(1 for p in points if p.moved_up), "resolved": len(rnd.resolved),
    }
    if organized:
        rooted = {f for r in organized.roots for f in [r.flag_id] + r.followers}
        singles = sum(1 for p in points if any(is_open(f) and f.id not in rooted for f in p.flags))
        summary.update({"roots": len(organized.roots), "flags_in_roots": len(rooted), "single_points": singles,
                        "follows": sum(1 for r in organized.replies if r.verdict == "follows"), "disputes": len(organized.disputes),
                        "withdrawn": len(organized.withdrawn)})
        log(f"{summary['flags_new']} new flags and {summary['flags_carried']} carried over: {summary['roots']} root questions settle "
            f"{summary['flags_in_roots']} flags, and {singles} single points stand alone; the checkers withdrew {summary['withdrawn']} "
            f"flags and disputed {summary['disputes']}: {out_dir / 'decisions.md'}")
    else:
        log(f"{summary['flags_new']} new flags and {summary['flags_carried']} carried over make {summary['decision_points']} decision points "
            f"({summary['to_decide']} to decide): {out_dir / 'decisions.md'}")
    write_json(out_dir / "merge-status.json", {"status": "completed", "decisions_current": True,
               "decisions_sha256": digest(out_dir / "decisions.json"), "draft_sha256": digest(out_dir / "draft.md"),
               "completed_tasks": [j["label"] for j in jobs], "horizontal_verification": "separate; not established by merge",
               **summary})
    run_log = json.loads(_read(out_dir / "run.json")) if (out_dir / "run.json").exists() else {}
    run_log.update(status="completed", decisions_current=True, completed_tasks=[j["label"] for j in jobs], **summary)
    run_log.setdefault("mode", "merge")
    write_json(out_dir / "run.json", run_log)
    return summary


def _open_round(out_dir: Path, draft_path: Path, options: Options, rulings_path: Path | None, prev_dir: Path | None) -> _Round:
    """The round with the author's rulings applied, so that only open flags reach the organizer."""
    rnd = _collect(out_dir, draft_path, options, prev_dir)
    apply_rulings(rnd.points, read_rulings(rulings_path), earlier_roots(out_dir, prev_dir))
    return rnd


def _route_step(out_dir: Path, rnd: _Round) -> dict[str, tuple[list, list]]:
    """Step one of the organizer: route each open flag down the nest, and record what went to whom."""
    routed = routes(rnd.points, parse_draft(rnd.draft_text))
    (out_dir / "routes.json").write_text(json.dumps({label: {"own": [f.id for f in own], "higher": [h.id for h in higher]}
                                                     for label, (own, higher) in routed.items()}, indent=1), encoding="utf-8")
    return routed


def _organize_with_provider(out_dir: Path, draft_path: Path, options: Options, rulings_path: Path | None, prev_dir: Path | None,
                            provider, runner: "_Runner", log: Callable[[str], None]) -> None:
    """The organizer as a traffic controller: each checker gets the flags above its own and replies, all at once, resumed
    with its own report in its context; then the checker of any disputed flag answers the dispute."""
    rnd = _open_round(out_dir, draft_path, options, rulings_path, prev_dir)
    jobs = {job.label: job for job in runner.jobs}
    routed = {label: item for label, item in _route_step(out_dir, rnd).items() if label in jobs and label in runner.reports}

    def ask(label: str, text: str, name: str):
        job, begun = jobs[label], time.time()
        try:
            reply = checked_completion(provider.complete(build_system(job.level, options), text,
                                       history=[(job.task, runner.reports[label])]))
        except Exception as error:
            with runner.lock:
                completion = getattr(error, "completion", None)
                runner.meta[f"{name}-{label}"] = {"status": "failed", "error_type": type(error).__name__,
                    "usage": completion.usage if isinstance(completion, Completion) else None}
                if isinstance(completion, Completion) and isinstance(completion.text, str):
                    (out_dir / f"incomplete-{name}-{label}.md").write_text(completion.text, encoding="utf-8")
                runner.persist("running")
            raise
        seconds = round(time.time() - begun, 1)
        (out_dir / f"{name}-{label}.md").write_text(reply.text, encoding="utf-8")
        with runner.lock:
            runner.meta[f"{name}-{label}"] = {"status": "completed", "served_model": reply.served_model,
                "stop_reason": reply.stop_reason, "usage": reply.usage,
                "seconds": seconds, "reason": "the organizer's routing"}
            runner.persist("running")
        log(f"Level {label}: {name} ({seconds} s)")
        return reply.text

    if routed:
        with ThreadPoolExecutor(max_workers=min(8, len(routed))) as pool:
            list(pool.map(lambda item: ask(item[0], route_text(*item[1]), "reply"), routed.items()))
    replies = {p.stem.split("-", 1)[1]: parse_reply(_read(p)) for p in sorted(out_dir.glob("reply-*.md"))}
    disputes = {label: items for label, items in disputes_by_report(dispute_list(replies, rnd.points)).items()
                if label in jobs and label in runner.reports}
    if disputes:
        with ThreadPoolExecutor(max_workers=min(8, len(disputes))) as pool:
            list(pool.map(lambda item: ask(item[0], dispute_text(item[1], rnd.points), "dispute-reply"), disputes.items()))
    runner.persist("ready_for_merge")


def _run_cascade(draft_path: Path, out_dir: Path, provider, options: Options | None = None, rulings_path: Path | None = None,
                log: Callable[[str], None] = print) -> dict:
    ensure_new_run(out_dir)
    options = options or Options()
    out_dir.mkdir(parents=True, exist_ok=True)
    _record_ruleset(out_dir)
    prepare_input(out_dir, draft_path)
    draft_text = _read(draft_path)
    draft = parse_draft(draft_text)
    started = time.time()

    script = script_pass(draft_text, _text(options.personal), _text(options.project))
    (out_dir / "level-S.md").write_text(script.report, encoding="utf-8")

    runner = _Runner(provider, options, log, out_dir)
    model = _text(options.model_file)
    if options.confirm_model and not model:
        stated = checked_completion(provider.complete(build_system("1", options), "Apply only rule 1.0 of Level 1: state the model as you read it, then stop.\n\n"
                                   f"<draft>\n{draft_text}\n</draft>"))
        model = options.confirm_model(stated.text)
        (out_dir / "model.md").write_text(model, encoding="utf-8")
        options.model_file = out_dir / "model.md"

    if options.parallel:  # independent full-coverage jobs; actual time/token effects are unmeasured
        items = all_paragraphs(draft)
        runner.run(jobs_levels_1_to_3(draft_text, model) + jobs_level_4(draft, items, options.split, "full coverage, all levels at once")
                   + jobs_level_5(draft, [], _text(options.sources), options.split, script.checked_citations, every_sentence=True))
    else:
        runner.run(jobs_levels_1_to_3(draft_text, model))
        items = all_paragraphs(draft) if options.full else passed_down_paragraphs(draft, runner.level_reports("3"))
        runner.run(jobs_level_4(draft, items, options.split, "full coverage" if options.full else "paragraphs Level 3 passed down"))
        sentences = parse_pass_down(runner.level_reports("4"))
        runner.run(jobs_level_5(draft, sentences, _text(options.sources), options.split, script.checked_citations))
    if options.word_choice:
        runner.run([job_word_choice(draft_text)])
    if not items:
        runner.meta["4"] = {"status": "skipped", "reason": "No paragraphs routed to Level 4.", "usage": None}

    _write_reports(out_dir, runner)
    if options.organize:
        _organize_with_provider(out_dir, draft_path, options, rulings_path, None, provider, runner, log)
    summary = _finish(out_dir, draft_path, options, rulings_path, None, log)
    run_log = {"draft": str(draft_path), "mode": "full" if options.full else "check",
               "ruleset": ruleset_metadata(),
               "provider": getattr(provider, "name", type(provider).__name__), "model_requested": getattr(provider, "model", ""),
               "model_confirmed_by_author": bool(model), "seconds": round(time.time() - started, 1),
               "levels": runner.meta, "script_flags": script.flags, **summary}
    (out_dir / "run.json").write_text(json.dumps(run_log, indent=2), encoding="utf-8")
    return run_log


def recheck_wave_one(draft, draft_text: str, plan, options: Options, script_checked: bool) -> list[Job]:
    """Everything a recheck can start at once: Levels 1 and 2 if the plan needs them, Level 3 on the changed sections, and
    Levels 4 and 5 on the changed paragraphs (Level 5 on every sentence in them), none of which waits for another."""
    model = _text(options.model_file)
    jobs = jobs_levels_1_to_3(draft_text, model, levels=tuple(l for l, on in (("1", plan.level1), ("2", plan.level2)) if on))
    for job in jobs:
        job.reason = plan.reasons.get(job.level, "")
    if plan.level3_sections:
        jobs.append(job_level_3_sections(draft, plan.level3_sections, model, "Their topic sentences changed since the last check."))
    jobs += jobs_level_4(draft, list(plan.level4), options.split, "changed since the last check")
    if plan.level5_paragraphs:
        jobs += jobs_level_5(draft, [], _text(options.sources), options.split, script_checked, only_paragraphs=list(plan.level5_paragraphs),
                             reason="These paragraphs changed since the last check.", every_sentence=True)
    return jobs


def recheck_wave_two(draft, plan, options: Options, script_checked: bool, level3: str, level4: str, done: list[Job]) -> list[Job]:
    """What wave one's checkers passed down beyond the changed paragraphs: Level 4 on further paragraphs Level 3 flagged,
    Level 5 on sentences Level 4 flagged outside the paragraphs Level 5 already read. Usually nothing."""
    had4 = {i for j in done if j.level == "4" for i in j.paragraphs}
    had5 = {i for j in done if j.level == "5" for i in j.paragraphs}
    extra4 = passed_down_paragraphs(draft, level3, exclude=had4)
    jobs = jobs_level_4(draft, extra4, options.split, "passed down by Level 3", suffix="-b")
    sentences, paragraphs = [], {}
    for item in parse_pass_down(level4):
        found = draft.find_paragraph(item.split("|", 1)[0])
        if found and found.index not in had5:
            sentences.append(item)
            paragraphs.setdefault(found.index, found)
    if sentences:
        jobs += jobs_level_5(draft, sentences, _text(options.sources), options.split, script_checked, only_paragraphs=list(paragraphs.values()),
                             reason="Level 4 passed these sentences down.", suffix="-b")
    return jobs


def _run_recheck(prev_dir: Path, draft_path: Path, out_dir: Path, provider, options: Options | None = None,
                rulings_path: Path | None = None, log: Callable[[str], None] = print) -> dict:
    """Recheck a revised draft against the run in prev_dir: only what changed, one level up and one level down."""
    ensure_new_run(out_dir)
    options = options or Options()
    if not compatible_ruleset(prev_dir):
        raise ValueError("Previous ruleset is missing or changed; explicitly prepare a fresh check without carryover.")
    out_dir.mkdir(parents=True, exist_ok=True)
    draft_text = _read(draft_path)
    draft = parse_draft(draft_text)
    plan = plan_recheck(_text(prev_dir / "draft.md"), draft_text, _text(prev_dir / "model.md"), _text(options.model_file))
    if plan.full:
        log(f"Checking in full: {plan.full_reason}.")
        return run_cascade(draft_path, out_dir, provider, options, rulings_path, log)
    _record_ruleset(out_dir)
    prepare_input(out_dir, draft_path, prev_dir)
    started = time.time()
    log(plan.summary())

    script = script_pass(draft_text, _text(options.personal), _text(options.project))
    (out_dir / "level-S.md").write_text(script.report, encoding="utf-8")
    runner = _Runner(provider, options, log, out_dir)
    runner.run(recheck_wave_one(draft, draft_text, plan, options, script.checked_citations))
    runner.run(recheck_wave_two(draft, plan, options, script.checked_citations, runner.level_reports("3"), runner.level_reports("4"), runner.jobs))

    _write_reports(out_dir, runner)
    if options.organize:
        _organize_with_provider(out_dir, draft_path, options, rulings_path, prev_dir, provider, runner, log)
    summary = _finish(out_dir, draft_path, options, rulings_path, prev_dir, log)
    run_log = {"draft": str(draft_path), "mode": "recheck", "previous": str(prev_dir),
               "ruleset": ruleset_metadata(),
               "provider": getattr(provider, "name", type(provider).__name__), "model_requested": getattr(provider, "model", ""),
               "seconds": round(time.time() - started, 1), "levels": runner.meta, "script_flags": script.flags, **summary}
    (out_dir / "run.json").write_text(json.dumps(run_log, indent=2), encoding="utf-8")
    return run_log


# ---------- bundles for any agent, then shared report processing ----------


def _execute(out_dir: Path, action) -> dict:
    # Reject reuse before entering the error recorder: never rewrite an older run.
    ensure_new_run(out_dir)
    try:
        result = action()
    except BaseException as error:
        if out_dir.exists():
            path = out_dir / "execution.json"
            execution = json.loads(_read(path)) if path.exists() else {"levels": {}}
            execution.update(status="failed", error_type=type(error).__name__)
            write_json(path, execution)
            write_json(out_dir / "run.json", {"status": "incomplete", "error_type": type(error).__name__,
                       "levels": execution["levels"], "decisions_current": False})
        raise
    result["status"] = "completed"
    write_json(out_dir / "run.json", result)
    path = out_dir / "execution.json"
    execution = json.loads(_read(path)) if path.exists() else {"levels": {}}
    execution["status"] = "completed"
    write_json(path, execution)
    return result


def run_cascade(draft_path: Path, out_dir: Path, provider, options: Options | None = None,
                rulings_path: Path | None = None, log: Callable[[str], None] = print) -> dict:
    return _execute(out_dir, lambda: _run_cascade(draft_path, out_dir, provider, options, rulings_path, log))


def run_recheck(prev_dir: Path, draft_path: Path, out_dir: Path, provider, options: Options | None = None,
                rulings_path: Path | None = None, log: Callable[[str], None] = print) -> dict:
    return _execute(out_dir, lambda: _run_recheck(prev_dir, draft_path, out_dir, provider, options, rulings_path, log))

def write_bundles(draft_path: Path, out_dir: Path, level: str, options: Options, prev_dir: Path | None = None) -> list[tuple[Path, Path]]:
    """Write one bundle per checker for a level (or for Levels 1 to 3 together), and return (bundle, report) paths.

    Level 4 reads Level 3's reports in out_dir, and Level 5 reads Level 4's, so run the levels in order.
    With prev_dir, write only what a recheck needs.
    """
    if prev_dir and not compatible_ruleset(prev_dir):
        raise ValueError("Previous ruleset is missing or changed; prepare a fresh check without --from.")
    out_dir.mkdir(parents=True, exist_ok=True)
    _record_ruleset(out_dir)
    prepare_input(out_dir, draft_path, prev_dir)
    draft_text = _read(draft_path)
    draft = parse_draft(draft_text)
    model = _text(options.model_file)
    plan = plan_recheck(_text(prev_dir / "draft.md"), draft_text, _text(prev_dir / "model.md"), model) if prev_dir else None
    if plan is not None and plan.full:
        plan = None  # checked in full
    reports = lambda lv: "\n\n".join(_read(p) for p in sorted(out_dir.glob(f"level-{lv}*.md")))
    jobs: list[Job] = []
    log_path = out_dir / "jobs.json"
    done = [Job(j["level"], j["label"], "", j["paragraphs"], j["sections"]) for j in (read_jobs(out_dir) if log_path.exists() else [])]
    if level == "all" and plan is not None:  # a recheck's first wave: everything that can start at once
        jobs = recheck_wave_one(draft, draft_text, plan, options, script_pass(draft_text, _text(options.personal), _text(options.project)).checked_citations)
    elif level in ("4", "5") and plan is not None and any(j.level == level for j in done):  # a recheck's second wave
        wave = recheck_wave_two(draft, plan, options, script_pass(draft_text, _text(options.personal), _text(options.project)).checked_citations,
                                reports("3"), reports("4"), done)
        jobs = [j for j in wave if j.level == level]
    elif level == "all":  # every level at once, with full coverage
        checked = script_pass(draft_text, _text(options.personal), _text(options.project)).checked_citations
        jobs = (jobs_levels_1_to_3(draft_text, model) + jobs_level_4(draft, all_paragraphs(draft), options.split, "full coverage, all levels at once")
                + jobs_level_5(draft, [], _text(options.sources), options.split, checked, every_sentence=True))
    elif level in ("1", "2", "3", "1,2,3", "123"):
        wanted = ("1", "2", "3") if level in ("1,2,3", "123") else (level,)
        if plan is None:
            jobs = jobs_levels_1_to_3(draft_text, model, levels=wanted)
        else:
            jobs = jobs_levels_1_to_3(draft_text, model, levels=tuple(l for l in wanted if (l == "1" and plan.level1) or (l == "2" and plan.level2)))
            if "3" in wanted and plan.level3_sections:
                jobs.append(job_level_3_sections(draft, plan.level3_sections, model, "Their topic sentences changed since the last check."))
    elif level == "4":
        items = list(plan.level4) if plan else []
        items += all_paragraphs(draft) if options.full and plan is None else passed_down_paragraphs(draft, reports("3"), {p.index for p, _ in items})
        jobs = jobs_level_4(draft, items, options.split, "changed since the last check, or passed down by Level 3" if plan else "paragraphs Level 3 passed down")
    elif level == "5":
        checked = script_pass(draft_text, _text(options.personal), _text(options.project)).checked_citations
        sentences = (list(plan.level5_sentences) if plan else []) + parse_pass_down(reports("4"))
        if plan is None:
            jobs = jobs_level_5(draft, sentences, _text(options.sources), options.split, checked)
        else:
            paragraphs = {p.index: p for p in plan.level5_paragraphs}
            for item in sentences:
                found = draft.find_paragraph(item.split("|", 1)[0])
                if found:
                    paragraphs.setdefault(found.index, found)
            jobs = jobs_level_5(draft, sentences, _text(options.sources), options.split, checked, only_paragraphs=list(paragraphs.values()),
                                reason="These paragraphs changed since the last check, or Level 4 passed their sentences down.")
    elif level == "W":
        jobs = [job_word_choice(draft_text)]
    written = []
    register_jobs(out_dir, jobs, options)
    for job in jobs:
        bundle = out_dir / f"bundle-{job.label}.md"
        written.append((bundle, out_dir / f"level-{job.label}.md"))
    if plan is not None:
        (out_dir / "plan.md").write_text(plan.summary() + "\n", encoding="utf-8")
    return written


def write_script(draft_path: Path, out_dir: Path, options: Options) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = script_pass(_read(draft_path), _text(options.personal), _text(options.project))
    target = out_dir / "level-S.md"
    target.write_text(result.report, encoding="utf-8")
    return target


def write_routes(report_dir: Path, draft_path: Path | None = None, options: Options | None = None, rulings_path: Path | None = None,
                 prev_dir: Path | None = None) -> list[tuple[Path, Path, Path, Path]]:
    """The coordinator's next step for any agent interface. Step one routes each checker the flags above its
    own; once every checker has replied, step two sends each disputed flag's checker the disputes. Returns (report, message,
    reply, bundle) for each checker to resume, or nothing when every message has its reply."""
    options = options or Options()
    draft_path = draft_path or report_dir / "draft.md"
    _require_complete(report_dir, draft_path, prev_dir)
    if not (report_dir / "routes.json").exists():
        routed = _route_step(report_dir, _open_round(report_dir, draft_path, options, rulings_path, prev_dir))
        written = []
        for label, (own, higher) in routed.items():
            message, reply = report_dir / f"route-{label}.md", report_dir / f"reply-{label}.md"
            message.write_text(route_text(own, higher, reply.resolve()), encoding="utf-8")
            written.append((report_dir / f"level-{label}.md", message, reply, report_dir / f"bundle-{label}.md"))
        return written
    rnd = _collect(report_dir, draft_path, options, prev_dir)
    labels = json.loads(_read(report_dir / "routes.json")).keys()
    waiting = [label for label in labels if not (report_dir / f"reply-{label}.md").exists()]
    if waiting:
        return [(report_dir / f"level-{label}.md", report_dir / f"route-{label}.md", report_dir / f"reply-{label}.md",
                 report_dir / f"bundle-{label}.md") for label in waiting]
    replies = {p.stem.split("-", 1)[1]: parse_reply(_read(p)) for p in sorted(report_dir.glob("reply-*.md"))}
    written = []
    for label, disputes in disputes_by_report(dispute_list(replies, rnd.points)).items():
        message, reply = report_dir / f"dispute-{label}.md", report_dir / f"dispute-reply-{label}.md"
        if reply.exists():
            continue
        message.write_text(dispute_text(disputes, rnd.points, reply.resolve()), encoding="utf-8")
        written.append((report_dir / f"level-{label}.md", message, reply, report_dir / f"bundle-{label}.md"))
    return written


def merge_directory(report_dir: Path, draft_path: Path | None = None, options: Options | None = None,
                    rulings_path: Path | None = None, prev_dir: Path | None = None, log: Callable[[str], None] = print) -> Path:
    """Process reports from any executor through the same merge implementation."""
    options = options or Options()
    draft_path = draft_path or report_dir / "draft.md"
    _finish(report_dir, draft_path, options, rulings_path, prev_dir, log)
    return report_dir / "decisions.md"
