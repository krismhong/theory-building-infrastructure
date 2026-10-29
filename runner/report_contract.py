"""Structural completion checks. These do not judge an argument's correctness.

Legacy flag parsing remains permissive; new completed rounds must pass this gate.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

from .flags import parse_flags, quote_segments
from .prompts import RULESET_ID, LEVEL_FILES, ROOT, bundle_text, ruleset_metadata


class ReportContractError(ValueError):
    """A prepared run/report cannot be represented as a completed check."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data) -> None:
    """Replace a complete JSON record atomically on the same filesystem."""
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Windows sync/indexing processes can briefly hold the destination open.
    # Never fall back to deleting or truncating the last complete record.
    for attempt in range(5):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * 2 ** attempt)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ReportContractError(f"Missing or invalid {path.name}; preserve this run and inspect its preparation.") from error


def previous_hashes(previous: Path) -> dict:
    status = read_json(previous / "merge-status.json")
    decisions = read_json(previous / "decisions.json")
    if (not isinstance(status, dict) or status.get("status") != "completed"
            or status.get("decisions_current") is not True
            or status.get("decisions_sha256") != digest(previous / "decisions.json")
            or status.get("draft_sha256") != digest(previous / "draft.md")
            or not isinstance(decisions, dict) or not isinstance(decisions.get("points"), list)):
        raise ReportContractError("Previous round is incomplete, changed, or lacks current completion evidence; start a fresh check.")
    for name in ("run.json", "execution.json"):
        if (previous / name).exists():
            state = read_json(previous / name)
            if not isinstance(state, dict) or state.get("status") != "completed":
                raise ReportContractError("Previous executor round is incomplete; start a fresh check.")
    return {name: digest(previous / name) for name in ("draft.md", "decisions.json", "ruleset.json", "merge-status.json")}


def input_record(draft: Path, previous: Path | None) -> dict:
    record = {"draft_sha256": digest(draft), "previous": str(previous.resolve()) if previous else None}
    if previous:
        record["previous_hashes"] = previous_hashes(previous)
    return record


def prepare_input(out: Path, draft: Path, previous: Path | None = None) -> None:
    record = input_record(draft, previous)
    if (out / "input.json").exists() and read_json(out / "input.json") != record:
        raise ReportContractError("Prepared input changed; preserve this run and choose a fresh output folder.")
    if (out / "draft.md").exists() and digest(out / "draft.md") != record["draft_sha256"]:
        raise ReportContractError("Prepared draft snapshot changed; use a fresh output folder.")
    if draft.resolve() != (out / "draft.md").resolve():
        (out / "draft.md").write_bytes(draft.read_bytes())
    write_json(out / "input.json", record)


def read_jobs(out: Path) -> list[dict]:
    jobs = read_json(out / "jobs.json")
    if not isinstance(jobs, list):
        raise ReportContractError("jobs.json must be a list of prepared tasks.")
    labels = set()
    for job in jobs:
        if not isinstance(job, dict):
            raise ReportContractError("Invalid prepared task record.")
        label, level = job.get("label"), job.get("level")
        if (not isinstance(label, str) or not re.fullmatch(r"[1-5W](?:-[A-Za-z0-9_-]+)?", label)
                or label in labels or not isinstance(level, str) or level not in LEVEL_FILES or label.split("-", 1)[0] != level
                or not isinstance(job.get("paragraphs"), list) or not isinstance(job.get("sections"), list)
                or any(type(i) is not int or i < 0 for i in job["paragraphs"])
                or any(not isinstance(s, str) for s in job["sections"])
                or not isinstance(job.get("bundle_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", job["bundle_sha256"])):
            raise ReportContractError("Invalid, duplicate, or unbound prepared task record.")
        labels.add(label)
    return jobs


def register_jobs(out: Path, jobs, options) -> list[dict]:
    logged = read_jobs(out) if (out / "jobs.json").exists() else []
    by_label = {j["label"]: j for j in logged}
    for job in jobs:
        # Match the existing text-writer's platform newlines before binding exact bytes.
        data = bundle_text(job, options).replace("\n", os.linesep).encode("utf-8")
        row = {"label": job.label, "level": job.level, "paragraphs": job.paragraphs,
               "sections": job.sections, "reason": job.reason,
               "bundle_sha256": hashlib.sha256(data).hexdigest()}
        if job.label in by_label and by_label[job.label] != row:
            raise ReportContractError("Prepared task changed; use a fresh run rather than replacing its bundle.")
        path = out / f"bundle-{job.label}.md"
        if path.exists() and path.read_bytes() != data:
            raise ReportContractError("Prepared bundle changed; preserve it and use a fresh run.")
        path.write_bytes(data)
        by_label[job.label] = row
    logged = list(by_label.values())
    write_json(out / "jobs.json", logged)
    return logged


def validate_report(text: str, level: str, draft_text: str | None = None) -> None:
    if not isinstance(text, str) or not text.strip():
        raise ReportContractError("Checker report is empty or is not text.")
    if re.findall(r"^Ruleset:\s*(\S+)\s*$", text, re.MULTILINE) != [RULESET_ID]:
        raise ReportContractError("Report needs exactly one current Ruleset marker.")
    if re.findall(r"^##\s+Level\s+([1-5W])\b", text, re.MULTILINE) != [level]:
        raise ReportContractError("Report needs exactly one heading for its assigned Level.")
    passes = list(re.finditer(r"^### Pass down\s*$(.*?)(?=^#{2,6}\s|\Z)", text, re.MULTILINE | re.DOTALL))
    if len(passes) != 1 or not passes[0].group(1).strip():
        raise ReportContractError("Report needs exactly one nonempty Pass down section (or explicit None).")
    pass_text = passes[0].group(1).strip()
    if re.match(r"(?i)^none\b", pass_text) and (re.search(r"(?m)^\s*[-*]\s+", pass_text) or "|" in pass_text):
        raise ReportContractError("Pass down cannot combine None with routed items.")
    body = text[:passes[0].start()]
    after_heading = re.split(r"^##\s+Level[^\n]*\n", body, maxsplit=1, flags=re.MULTILINE)
    if len(after_heading) != 2 or not after_heading[1].strip():
        raise ReportContractError("Report has no findings or account of the completed check.")
    if re.search(r"^\s*\[(?:CRITICAL|ISSUE|SUGGEST):?\]", text[passes[0].start():], re.MULTILINE):
        raise ReportContractError("Findings must precede Pass down.")
    flags = parse_flags(body, level)
    if not flags and not re.search(r"No issues found at Level " + re.escape(level) + r"\b", body):
        raise ReportContractError("A zero-finding report must explicitly state No issues found at its Level.")
    starts = re.findall(r"^\s*\[[^\]\n]+\].*\bRule\b", body, re.MULTILINE)
    if len(starts) != len(flags):
        raise ReportContractError("A finding has an unrecognized tag or malformed header.")
    fields = ("Quote", "What fails", "Decision", "Kind", "Assessment")
    # Orphan fields cannot silently become a zero-finding report.
    for field in fields:
        if (len(re.findall(r"^" + field + r":", body, re.MULTILINE)) != len(flags)
                or len(re.findall(r"^" + field + r":[ \t]*[^\s\r\n][^\r\n]*$", body, re.MULTILINE)) != len(flags)):
            raise ReportContractError(f"Each finding needs exactly one {field}: field.")
    valid_rules = set(re.findall(r"\*\*([1-5W]\.\d+)\b", (ROOT / LEVEL_FILES[level]).read_text(encoding="utf-8")))
    for flag in flags:
        if re.findall(r"^Kind:\s*(fork|slip)\s*$", flag.raw, re.MULTILINE) != [flag.kind]:
            raise ReportContractError("Kind must be exactly fork or slip.")
        if (flag.rule not in valid_rules or not all((flag.location, flag.quote, flag.what_fails, flag.decision))
                or flag.kind not in {"fork", "slip"}
                or flag.assessment not in {"logic_defect", "indeterminate", "policy_note", "reference_check"}):
            raise ReportContractError("A finding has incomplete or invalid rule, location, kind, or assessment fields.")
        if len(re.findall(r"\bLocation:[ \t]*[^\s\r\n][^\r\n]*", flag.raw)) != 1:
            raise ReportContractError("Each finding needs one Location field.")
        if draft_text is not None and any(q not in draft_text for q in quote_segments(flag.quote)):
            raise ReportContractError("A finding's verbatim quotation is absent from the prepared draft.")


def receipt_for(out: Path, label: str, model: str, stop_reason: str, usage, backend: str) -> dict:
    return {"task": label, "status": "completed", "completion_confirmed": True,
            "report_sha256": digest(out / f"level-{label}.md"),
            "bundle_sha256": digest(out / f"bundle-{label}.md"),
            "model": model, "backend": backend, "executor_id": backend + ":" + label,
            "stop_reason": stop_reason, "usage": usage}


def validate_run(out: Path, draft: Path, previous: Path | None = None) -> list[dict]:
    if read_json(out / "ruleset.json") != ruleset_metadata():
        raise ReportContractError("Prepared ruleset changed or is missing; start a fresh check.")
    snapshot = read_json(out / "input.json")
    if snapshot != input_record(draft, previous):
        raise ReportContractError("Draft or previous-round context differs from the prepared input.")
    if digest(out / "draft.md") != snapshot["draft_sha256"]:
        raise ReportContractError("Prepared draft snapshot changed.")
    execution = read_json(out / "execution.json") if (out / "execution.json").exists() else None
    if execution is not None and (not isinstance(execution, dict) or execution.get("status") not in {"ready_for_merge", "completed"}):
        raise ReportContractError("Executor run is incomplete; preserve its outputs and start a fresh run.")
    jobs = read_jobs(out)
    if not jobs and not previous:
        raise ReportContractError("No checker jobs were prepared; this is not a completed check.")
    expected = {j["label"] for j in jobs}
    found = {p.stem[6:] for p in out.glob("level-*.md")} - {"S"}
    if found != expected:
        raise ReportContractError(f"Checker report coverage differs from prepared jobs; missing={sorted(expected-found)}, extra={sorted(found-expected)}.")
    draft_text = draft.read_text(encoding="utf-8")
    for job in jobs:
        label = job["label"]
        if digest(out / f"bundle-{label}.md") != job["bundle_sha256"]:
            raise ReportContractError("A prepared bundle no longer matches its job record.")
        report = out / f"level-{label}.md"
        validate_report(report.read_text(encoding="utf-8-sig"), job["level"], draft_text)
        receipt = read_json(out / f"executor-{label}.json")
        if (not isinstance(receipt, dict) or receipt.get("task") != label
                or receipt.get("status") != "completed" or receipt.get("completion_confirmed") is not True
                or any(not isinstance(receipt.get(key), str) or not receipt[key].strip() for key in ("model", "backend", "executor_id"))
                or (receipt.get("usage") is not None and not isinstance(receipt["usage"], dict))
                or receipt.get("report_sha256") != digest(report)
                or receipt.get("bundle_sha256") != job["bundle_sha256"]
                or not (receipt.get("stop_reason") is None or
                        isinstance(receipt.get("stop_reason"), str) and
                        receipt["stop_reason"] in {"", "stop", "end_turn", "stop_sequence"})):
            raise ReportContractError("Missing, incomplete, or mismatched executor receipt.")
    return jobs
