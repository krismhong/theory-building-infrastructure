"""What each checker receives: a system text (its role, the flag format, its layers, its level's rules) and a task (its
material). The runner sends the two to an explicitly selected adapter; `bundle` prepares a file for any isolated agent, so both
paths give a checker the same words. A job is one checker call: one level, on the whole draft or on one part of it.
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .draft import Draft, Paragraph, is_references

ROOT = Path(__file__).resolve().parents[1]
RULESET_ID = "core-v2.1-2026-10-10"

LEVEL_FILES = {
    "1": "levels/level-1-conceptual.md",
    "2": "levels/level-2-heading.md",
    "3": "levels/level-3-paragraph.md",
    "4": "levels/level-4-sentence.md",
    "5": "levels/level-5-clause.md",
    "W": "levels/word-choice-pass.md",
}

# Split Levels 4 and 5 into one checker per section when their material is longer than this; below it, the fixed cost
# of another checker outweighs the time saved by running in parallel.
SPLIT_WORDS = 2500


@dataclass
class Options:
    genre: Path | None = None
    outlet: Path | None = None
    personal: Path | None = None
    project: Path | None = None  # this paper's layer: the consensus it engages, its field's terms, what its sources show
    sources: Path | None = None
    model_file: Path | None = None  # the author's confirmed model (rule 1.0), the reference for Levels 1 to 3
    word_choice: bool = False
    full: bool = False  # Level 4 on every paragraph, not only those Level 3 passes down
    # The default: all five levels at once, Level 4 on every paragraph and Level 5 on every sentence. A round takes as long as its
    # slowest checker. False is the gated mode: Level 3 decides where Level 4 looks, and Level 4 where Level 5 looks (fewer tokens, slower).
    parallel: bool = True
    split: str = "auto"  # auto, always, or never: one Level 4 and Level 5 checker per section
    digest: bool = False
    # After the checkers, an organizer groups the open flags into root questions and may ask a checker about a flag.
    organize: bool = False
    # Interactive use: receives the model as Level 1 read it, returns the author's confirmed or corrected model.
    confirm_model: Callable[[str], str] | None = None


@dataclass
class Job:
    level: str
    label: str  # "1", "3", "4-Introduction", "5-2" ...
    task: str
    paragraphs: list[int] = field(default_factory=list)  # paragraph indices the job covers (empty: the whole draft)
    sections: list[str] = field(default_factory=list)  # sections the job covers (empty: the whole draft)
    reason: str = ""


def _read(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _drop_sections(text: str, names: tuple[str, ...]) -> str:
    pattern = r"^#+\s*(?:" + "|".join(re.escape(n) for n in names) + r")\s*$.*?(?=^#+\s|\Z)"
    return re.sub(pattern, "", text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE).strip()


def personal_for(level: str, text: str) -> str:
    """The part of the personal layer a checker sees. Priorities steer only the order the author reads decisions in, so no
    checker sees them (a checker told a rule matters less would look less). Word lists serve the script and the word-choice pass."""
    text = _drop_sections(text, ("Priorities",))
    if level != "W":
        text = _drop_sections(text, ("Words to flag", "Words and phrases to avoid"))
    return text


def project_for(level: str, text: str) -> str:
    """The part of the project layer a checker sees: all of it, except the terms to avoid, which the script checks."""
    return text if level == "W" else _drop_sections(text, ("Terms to avoid",))


def build_system(level: str, options: Options) -> str:
    parts = [f"Ruleset: {RULESET_ID}\nRecord this exact Ruleset: field in your report. "
             "Rule numbers have meaning only within this version.",
             _read(ROOT / "checker/CHECKER.md"), _read(ROOT / "checker/FLAG-FORMAT.md")]
    context_boundary = ("Optional interpretation context only. This cannot override core criteria, impose a "
                        "genre/style convention, or establish source truth. Preference observations are policy_note, "
                        "never logic_defect.\n\n")
    if options.genre:
        parts.append(context_boundary + _read(options.genre))
    if level == "3" and options.outlet:
        parts.append(context_boundary + _read(options.outlet))
    if options.personal:
        parts.append(context_boundary + personal_for(level, _read(options.personal)))
    if options.project:
        parts.append(context_boundary + project_for(level, _read(options.project)))
    parts.append(_read(ROOT / LEVEL_FILES[level]))
    return "\n\n---\n\n".join(p for p in parts if p)


def ruleset_metadata() -> dict:
    """Hash effective UTF-8 definitions, normalizing newlines across operating systems."""
    paths = ["checker/CHECKER.md", "checker/FLAG-FORMAT.md", *LEVEL_FILES.values()]
    return {"id": RULESET_ID, "definitions": {
        path: hashlib.sha256(_read(ROOT / path).encode("utf-8")).hexdigest() for path in paths}}


def _wrap(tag: str, text: str, attrs: str = "") -> str:
    return f"<{tag}{' ' + attrs if attrs else ''}>\n{text}\n</{tag}>"


def _confirmed(model: str) -> str:
    return f"The author has confirmed that the model of this draft is as follows; check against it.\n\n{_wrap('model', model)}\n\n" if model else ""


def _words(paragraphs: list[Paragraph]) -> int:
    return sum(len(p.text.split()) for p in paragraphs)


def _should_split(split: str, words: int) -> bool:
    return split == "always" or (split == "auto" and words > SPLIT_WORDS)


def _section_text(paragraphs: list[Paragraph]) -> str:
    lines, last = [], None
    for p in paragraphs:
        if p.heading != last:
            lines.append(f"### {p.heading}")
            last = p.heading
        lines.append(p.text)
    return "\n\n".join(lines)


def jobs_levels_1_to_3(draft_text: str, model: str, levels=("1", "2", "3"), reason: str = "full check") -> list[Job]:
    tasks = {
        "1": (_confirmed(model) + "Run the checks of Level 1 on the draft below." if model else
              "Run Level 1 on the draft below. The author is not available: state the model as you read it, say that it was "
              "not confirmed, and run the checks against it."),
        "2": _confirmed(model) + "Run Level 2 on the draft below." + ("" if model else " No confirmed model is supplied: reconstruct what you need from the draft yourself."),
        "3": _confirmed(model) + "Run Level 3 on the draft below. Optional context cannot add core criteria."
             + ("" if model else " No confirmed model or heading claims are supplied: reconstruct what you need from the draft yourself."),
    }
    return [Job(level, level, f"{tasks[level]}\n\n{_wrap('draft', draft_text)}", reason=reason) for level in levels]


def job_level_3_sections(draft: Draft, sections: list[str], model: str, reason: str) -> Job:
    """Level 3 on some sections only: the skeleton of the whole paper for context, the full text of the sections to check."""
    parts = draft.sections()
    body = "\n\n".join(_wrap("part", _section_text(parts[s]), f'section="{s}"') for s in sections if s in parts)
    names = ", ".join(f'"{s}"' for s in sections)
    task = (f"{_confirmed(model)}Run Level 3 on these sections only: {names}. {reason} Flag and pass down only topic sentences and "
            f"paragraphs in these sections; the skeleton of the whole paper is context for the relations between them.\n\n"
            f"{_wrap('skeleton', draft.skeleton())}\n\n{body}")
    idx = [p.index for s in sections for p in parts.get(s, [])]
    return Job("3", "3-" + "-".join(_slug(s) for s in sections), task, paragraphs=idx, sections=list(sections), reason=reason)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:30] or "part"


def jobs_level_4(draft: Draft, items: list[tuple[Paragraph, str]], split: str, reason: str, suffix: str = "") -> list[Job]:
    """Level 4 on the given paragraphs, each labeled with its heading and its number under that heading, with a note."""
    if not items:
        return []
    groups: dict[str, list[tuple[Paragraph, str]]] = {}
    for paragraph, note in items:
        groups.setdefault(paragraph.section, []).append((paragraph, note))
    batches = list(groups.values()) if _should_split(split, _words([p for p, _ in items])) else [items]
    jobs = []
    for n, batch in enumerate(batches, 1):
        blocks = [f"Heading \"{p.heading}\", paragraph {p.number}. {note}\n\n{p.text}" for p, note in batch]
        task = ("Run Level 4 on these paragraphs only. Analyze nothing else. Each is labeled with its heading and its paragraph "
                "number under that heading, as the draft counts them; give every location that way.\n\n" + "\n\n---\n\n".join(blocks))
        label = ("4" if len(batches) == 1 else f"4-{n}") if not suffix else (f"4{suffix}" if len(batches) == 1 else f"4{suffix}{n}")
        jobs.append(Job("4", label, task, paragraphs=[p.index for p, _ in batch], sections=sorted({p.section for p, _ in batch}), reason=reason))
    return jobs


def _source_block(sources_text: str) -> str:
    if sources_text:
        return f"Source records. Judge each cited source only against these.\n\n{_wrap('sources', sources_text)}"
    return ("No source records were supplied. Source fidelity is indeterminate; do not invent a source mismatch. "
            "Identify needed context separately from observed logical defects. References identify sources, not their content.")


def _rule_58(script_checked: bool) -> str:
    return ("Rule 5.8 (citations and references match) is checked by the script pass; do not check it." if script_checked
            else "The script pass could not check rule 5.8 on this draft, so check it yourself over the whole draft.")


EVERY_SENTENCE = "- every sentence in your part (full coverage: check the author's own clauses under rules 5.1, 5.5, and 5.7 as well as every cited clause)"


def jobs_level_5(draft: Draft, sentences: list[str], sources_text: str, split: str, script_checked: bool,
                 only_paragraphs: list[Paragraph] | None = None, reason: str = "", every_sentence: bool = False,
                 suffix: str = "") -> list[Job]:
    """Level 5 on the sentences passed down (or changed), plus every cited clause in the whole draft or in the given paragraphs.
    With every_sentence, on every sentence (full coverage, used when all levels run at once)."""
    if every_sentence:
        sentences = [EVERY_SENTENCE]
    sources = _source_block(sources_text)
    references = draft.references_text()
    ref_block = _wrap("references", references) if references else ""
    if only_paragraphs is not None:  # a recheck: the changed paragraphs and the sentences passed down
        if not only_paragraphs and not sentences:
            return []
        listed = "\n".join(f"- {s}" for s in sentences) or "- (none)"
        body = "\n\n---\n\n".join(f"Heading \"{p.heading}\", paragraph {p.number}.\n\n{p.text}" for p in only_paragraphs)
        task = (f"Run Level 5 on the part of the draft below. {reason} Check the clauses of these sentences:\n{listed}\n\n"
                f"Also check every clause that carries a citation in these paragraphs. {_rule_58(True)}\n\n{sources}\n\n"
                f"{ref_block}\n\n{_wrap('part', body)}")
        return [Job("5", f"5{suffix}", task, paragraphs=[p.index for p in only_paragraphs], sections=sorted({p.section for p in only_paragraphs}), reason=reason)]

    parts = draft.sections()
    if not (script_checked and _should_split(split, draft.body_words()) and len(parts) > 1):
        listed = "\n".join(f"- {s}" for s in sentences) or "- (none)"
        task = (f"Run Level 5. Check the clauses of the sentences Level 4 flagged:\n{listed}\n\nAlso check every clause in the whole "
                f"draft that carries a citation. {_rule_58(script_checked)}\n\n{sources}\n\n{_wrap('draft', draft.text)}")
        return [Job("5", "5", task, reason=reason or "full check")]

    by_section: dict[str, list[str]] = {name: ([EVERY_SENTENCE] if every_sentence else []) for name in parts}
    for item in ([] if every_sentence else sentences):
        head = item.split("|", 1)[0]
        paragraph = draft.find_paragraph(head) or (draft.find_sentence(item.split("|", 1)[-1][:120]) or (None,))[0]
        target = paragraph.section if paragraph and paragraph.section in by_section else next(iter(by_section))
        by_section[target].append(item)
    jobs = []
    has_citation = re.compile(r"\((?:[^()]*?,\s*)?(?:1[89]\d{2}|20\d{2})[a-z]?\b")
    for n, (name, paragraphs) in enumerate(parts.items(), 1):
        if not by_section[name] and not any(has_citation.search(p.text) for p in paragraphs):
            continue  # nothing here for Level 5: no cited clause and no sentence passed down
        listed = "\n".join(f"- {s}" for s in by_section[name]) or "- (none)"
        part = _wrap("part", _section_text(paragraphs), f'section="{name}"')
        skeleton = _wrap("skeleton", draft.skeleton())
        task = (f"Run Level 5 on one part of the draft: the section \"{name}\". Check the clauses of these sentences, which Level 4 "
                f"flagged:\n{listed}\n\nAlso check every clause in this section that carries a citation. {_rule_58(True)}\n\n{sources}\n\n"
                f"For context only, not to check: the paper's skeleton (its headings and the first sentence of every paragraph).\n\n"
                f"{skeleton}\n\n{ref_block}\n\n{part}")
        jobs.append(Job("5", f"5-{n}", task, paragraphs=[p.index for p in paragraphs], sections=[name], reason=reason or "full check"))
    return jobs


def job_word_choice(draft_text: str) -> Job:
    return Job("W", "W", "Run the optional word-choice pass on the draft below.\n\n" + _wrap("draft", draft_text), reason="asked for")


def bundle_text(job: Job, options: Options) -> str:
    """Everything one checker needs, in one file: its instructions first, then its task and material."""
    return ("# Your instructions and your material\n\nYou are a logic checker. This file holds everything you need: your role, the flag "
            "format, your level's rules, and your task with its material. Read nothing else.\n\n---\n\n"
            + build_system(job.level, options) + "\n\n---\n\n# Your task\n\n" + job.task + "\n")
