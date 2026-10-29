"""Prepare a synthetic development scaffold offline; this is not an approved evaluation.

No executor, provider, credentials, or API is required. Agent/API execution is separate.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.cascade import all_paragraphs, ensure_new_run, passed_down_paragraphs
from runner.flags import parse_pass_down
from runner.mechanical import script_pass
from runner.prompts import (ROOT, Options, build_system, jobs_level_4, jobs_level_5,
                            jobs_levels_1_to_3)
from runner.draft import parse_draft


def prepare(out: Path, level3_report: Path | None = None, level4_report: Path | None = None) -> dict:
    ensure_new_run(out)
    original = ROOT / "examples" / "sample-draft.md"
    revised = ROOT / "examples" / "sample-draft-v2.md"
    sources = ROOT / "examples" / "pilot-sources.md"
    text = original.read_text(encoding="utf-8")
    draft = parse_draft(text)
    records = sources.read_text(encoding="utf-8")
    options = Options(sources=sources, split="never")  # core-only, no automatic or private layers
    script = script_pass(text)
    jobs = {
        "shared-level-3": jobs_levels_1_to_3(text, "", levels=("3",))[0],
        "full-level-4": jobs_level_4(draft, all_paragraphs(draft), "never", "full coverage")[0],
        "coarse-level-1": jobs_levels_1_to_3(text, "", levels=("1",))[0],
        "full-level-5": jobs_level_5(draft, [], records, "never", script.checked_citations, every_sentence=True)[0],
    }
    control = parse_draft(revised.read_text(encoding="utf-8"))
    repaired = [p for p in control.paragraphs if p.first_sentence.startswith(("Slack gives a team", "Teams that protect"))]
    if len(repaired) != 2:
        raise ValueError("The two expected revised paragraphs changed; review the fixture before preparing the pilot.")
    jobs["revised-level-4"] = jobs_level_4(control, [(p, "Check this paragraph only.") for p in repaired], "never",
                                       "local revision control")[0]
    skipped = []
    if level3_report:
        items = passed_down_paragraphs(draft, level3_report.read_text(encoding="utf-8"))
        gated = jobs_level_4(draft, items, "never", "selected by the shared Level 3 report")
        if gated:
            jobs["gated-level-4"] = gated[0]
        else:
            skipped.append("gated-level-4")
    if level4_report:
        jobs["gated-level-5"] = jobs_level_5(draft, parse_pass_down(level4_report.read_text(encoding="utf-8")),
                                            records, "never", script.checked_citations)[0]
    out.mkdir(parents=True, exist_ok=True)
    sizes = []
    for name, job in jobs.items():
        system, user = build_system(job.level, options), job.task
        payload = {"level": job.level, "system": system, "user": user, "paragraphs": job.paragraphs,
                   "sections": job.sections}
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        (out / (name + ".json")).write_bytes(encoded)
        sizes.append({"request": name, "level": job.level, "prompt_utf8_bytes": len((system + user).encode("utf-8")),
                      "sha256": hashlib.sha256(encoded).hexdigest()})
    manifest = {"mode": "offline preparation, not model results", "prepared_requests": sizes,
                "conditional_requests_not_prepared": (["gated-level-4"] if not level3_report else [])
                                                    + (["gated-level-5"] if not level4_report else []),
                "skipped_requests": skipped, "maximum_checker_jobs_in_scaffold": 7,
                "dispatch": "not dispatched; external agent or explicitly authorized adapter",
                "token_budget": None, "dollar_budget": None,
                "layers": {"personal": None, "project": None, "confirmed_model": None, "rulings": None},
                "fixture_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (original, revised, sources)},
                "external_calls": 0}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "script-original.md").write_text(script.report, encoding="utf-8")
    (out / "script-revised.md").write_text(script_pass(control.text).report, encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--level3-report", type=Path, help="the one shared Level 3 report, to prepare the gated Level 4 request")
    parser.add_argument("--level4-report", type=Path, help="the gated Level 4 report, to prepare the gated Level 5 request")
    args = parser.parse_args()
    manifest = prepare(args.out, args.level3_report, args.level4_report)
    print(json.dumps({"prepared_requests": len(manifest["prepared_requests"]),
                      "prompt_utf8_bytes": sum(x["prompt_utf8_bytes"] for x in manifest["prepared_requests"]),
                      "maximum_checker_jobs_in_scaffold": manifest["maximum_checker_jobs_in_scaffold"], "external_calls": 0}))


if __name__ == "__main__":
    main()
