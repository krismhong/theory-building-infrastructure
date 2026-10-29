"""The dynamic loop: after the author revises, recheck only what the revision touched, one level up and down from each
change; carry forward what did not change; remember the author's rulings; and learn from them.

The nest of units and the level that checks each unit against its parent:
    the model (Level 1)  >  sections (Level 2)  >  paragraphs, through their topic sentences (Level 3)
    >  sentences (Level 4)  >  clauses (Level 5)
A change to a unit is checked at its own level and one level up (does the unit still serve its parent?) and one level down
(do its parts still make it good?). If the check one level up finds a new problem, the revision has moved up a level: the
system reports it first and stops there. Whether the point itself changes is the author's decision, never the system's.
"""

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .draft import Draft, Paragraph, is_references, normalize, parse_draft
from .flags import DecisionPoint, Flag, _same_words, flag_key, quote_segments

_FRAMING = re.compile(r"^(introduction|discussion|conclusions?|general discussion|implications)$", re.IGNORECASE)
FULL_RECHECK_SHARE = 0.3  # a revision that changes more than this share of the body's paragraphs is checked in full


@dataclass
class Change:
    kind: str  # sentence, topic, added, removed, proposition, heading, references
    section: str
    paragraph: Paragraph | None  # the paragraph in the new draft (None when removed)
    sentences: list[str] = field(default_factory=list)  # new or changed sentences in the new draft
    detail: str = ""


@dataclass
class Plan:
    changes: list[Change]
    full: bool = False
    full_reason: str = ""
    level1: bool = False
    level2: bool = False
    level3_sections: list[str] = field(default_factory=list)
    level4: list[tuple[Paragraph, str]] = field(default_factory=list)  # (paragraph, note)
    level5_paragraphs: list[Paragraph] = field(default_factory=list)
    level5_sentences: list[str] = field(default_factory=list)
    # where a new flag means the revision moved up a level: level -> paragraph indices (4), section names (3), or "all" (1, 2)
    up: dict[str, set] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        if not self.changes and not self.full:
            return "No change since the last check; nothing was rechecked. Every decision point carries over."
        lines = ["# What changed, and what was rechecked", ""]
        if self.full:
            lines.append(f"Checked in full: {self.full_reason}.")
        for c in self.changes:
            where = c.paragraph.location() if c.paragraph else f"section \"{c.section}\""
            lines.append(f"- {c.kind}: {where}{' (' + c.detail + ')' if c.detail else ''}")
        if not self.full:
            lines.append("")
            lines.append(f"- Level 1: {'rechecked (' + self.reasons.get('1', '') + ')' if self.level1 else 'carried over'}")
            lines.append(f"- Level 2: {'rechecked (' + self.reasons.get('2', '') + ')' if self.level2 else 'carried over'}")
            lines.append(f"- Level 3: {'sections ' + ', '.join(self.level3_sections) if self.level3_sections else 'carried over'}")
            lines.append(f"- Level 4: {len(self.level4)} paragraph(s), plus any the new Level 3 passes down")
            lines.append(f"- Level 5: {len(self.level5_paragraphs)} paragraph(s), plus any sentence the new Level 4 passes down")
            lines.append("- Script checks: rerun on the whole draft (they cost nothing)")
        return "\n".join(lines)


def diff_drafts(old_text: str, new_text: str) -> list[Change]:
    old, new = parse_draft(old_text), parse_draft(new_text)
    changes: list[Change] = []
    if [h for h in old.headings] != [h for h in new.headings]:
        before, after = {t for _, t in old.headings}, {t for _, t in new.headings}
        detail = "; ".join([f"added \"{t}\"" for t in after - before] + [f"removed \"{t}\"" for t in before - after]) or "headings reordered or moved"
        changes.append(Change("heading", "", None, detail=detail))
    a = [normalize(p.text) for p in old.paragraphs]
    b = [normalize(p.text) for p in new.paragraphs]
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        olds, news = old.paragraphs[i1:i2], new.paragraphs[j1:j2]
        for k in range(max(len(olds), len(news))):
            before = olds[k] if k < len(olds) else None
            after = news[k] if k < len(news) else None
            if (after is not None and is_references(after.section)) or (after is None and is_references(before.section)):
                changes.append(Change("references", "References", after))
                continue
            if after is None:
                changes.append(Change("proposition" if before.is_proposition else "removed", before.section, None,
                                      detail=f"removed: \"{before.first_sentence[:80]}\""))
                continue
            if before is None:
                changes.append(Change("proposition" if after.is_proposition else "added", after.section, after, after.sentences))
                continue
            old_sentences = {normalize(s) for s in before.sentences}
            changed = [s for s in after.sentences if normalize(s) not in old_sentences]
            if before.is_proposition or after.is_proposition:
                changes.append(Change("proposition", after.section, after, changed))
            elif normalize(before.first_sentence) != normalize(after.first_sentence):
                changes.append(Change("topic", after.section, after, changed))
            else:
                changes.append(Change("sentence", after.section, after, changed))
    return changes


def plan_recheck(old_text: str, new_text: str, old_model: str = "", new_model: str = "", sources_changed: bool = False) -> Plan:
    changes = diff_drafts(old_text, new_text)
    new = parse_draft(new_text)
    plan = Plan(changes=changes)
    body = [p for p in new.paragraphs if not is_references(p.section) and p.section != "(front matter)"]
    touched = {c.paragraph.index for c in changes if c.paragraph is not None and c.kind != "references" and c.paragraph.section != "(front matter)"}
    touched_share = (len(touched) + sum(1 for c in changes if c.kind == "removed")) / max(1, len(body))
    if normalize(old_model) != normalize(new_model):
        plan.full, plan.full_reason = True, "the confirmed model changed, so every level checks against the new one"
        return plan
    if touched_share > FULL_RECHECK_SHARE:
        plan.full, plan.full_reason = True, f"the revision touched {touched_share:.0%} of the body's paragraphs"
        return plan

    kinds = {c.kind for c in changes}
    if "proposition" in kinds:
        plan.level1, plan.reasons["1"] = True, "a proposition changed, so the model is checked one level up"
        plan.up["1"] = {"all"}
    framing = any(_FRAMING.match(c.section.strip()) for c in changes if c.kind in ("topic", "added", "removed"))
    if kinds & {"heading", "proposition"} or framing:
        plan.level2 = True
        plan.reasons["2"] = "the headings changed" if "heading" in kinds else ("a proposition changed" if "proposition" in kinds else
                                                                              "a paragraph of the introduction or discussion changed")
        if "heading" in kinds:
            plan.up["2"] = {"all"}
    sections = []
    for c in changes:
        if c.kind in ("topic", "added", "removed", "proposition") and c.section and not is_references(c.section):
            if c.section not in sections:
                sections.append(c.section)
    if "heading" in kinds:  # a new or renamed section is checked one level down
        for name in new.sections():
            if name not in {p.section for p in parse_draft(old_text).paragraphs} and name not in sections:
                sections.append(name)
    plan.level3_sections = sections
    plan.up["3"] = {c.section for c in changes if c.kind in ("topic", "added", "removed")}

    seen = set()
    for c in changes:
        if c.paragraph is None or c.kind == "references" or c.paragraph.index in seen:
            continue
        seen.add(c.paragraph.index)
        note = {"sentence": "Changed since the last check: sentences in its body.",
                "topic": "Changed since the last check: its topic sentence.",
                "added": "New since the last check.",
                "proposition": "Changed since the last check: a proposition."}[c.kind]
        plan.level4.append((c.paragraph, note))
        plan.level5_paragraphs.append(c.paragraph)
        first = c.paragraph.first_sentence
        plan.level5_sentences.extend(f"{first} | {s} (changed)" for s in c.sentences)
    plan.up["4"] = {c.paragraph.index for c in changes if c.kind == "sentence" and c.paragraph is not None}
    if sources_changed:
        plan.level5_paragraphs = [p for p in body]
    return plan


# ---------- carrying decisions forward ----------

def _present(quote: str, draft_norm: str) -> bool:
    segments = [normalize(s) for s in quote_segments(quote)]
    return all(seg and seg in draft_norm for seg in segments)


def _paragraph_in(new: Draft, old: Draft | None, quote: str) -> Paragraph | None:
    """The paragraph of the new draft a flag belongs to: where its quote now stands, or, if the words changed, the paragraph
    that took the place of the one it quoted (the same first sentence, else the same position under the same heading)."""
    for segment in quote_segments(quote):
        where = new.find_sentence(segment)
        if where:
            return where[0]
    if old is None:
        return None
    for segment in quote_segments(quote):
        where = old.find_sentence(segment)
        if not where:
            continue
        before = where[0]
        same = [p for p in new.paragraphs if normalize(p.first_sentence) == normalize(before.first_sentence)]
        if same:
            return same[0]
        slot = [p for p in new.paragraphs if p.heading == before.heading and p.number == before.number]
        if slot:
            return slot[0]
    return None


def carry_forward(old_points: list[DecisionPoint], new_text: str, rerun: dict[str, object], old_text: str = "") -> tuple[list[Flag], list[dict]]:
    """Old flags that still stand. `rerun` says what was checked again: level -> "all", or a set of paragraph indices.

    A flag that a recheck covered is dropped, since the recheck decides afresh. Every other flag carries forward; if the words
    it quotes changed and its level did not rerun there, it is marked stale: still open, because nothing has checked it again.
    A decision point whose every flag a recheck covered is gone, unless the recheck raised it again.
    """
    new = parse_draft(new_text)
    old = parse_draft(old_text) if old_text else None
    draft_norm = normalize(new_text)
    carried: list[Flag] = []
    gone: list[dict] = []
    for point in old_points:
        kept = False
        for flag in point.flags:
            if flag.level == "S":
                continue  # the script pass always reruns
            quote = flag.quote or point.quote
            scope = rerun.get(flag.level)
            paragraph = _paragraph_in(new, old, quote)
            if scope == "all" or (isinstance(scope, set) and paragraph is not None and paragraph.index in scope):
                continue
            flag.origin = "carried"
            flag.moved_up = False
            flag.stale = not _present(quote, draft_norm)
            carried.append(flag)
            kept = True
        if not kept:
            gone.append({"id": point.id, "quote": point.quote})
    return carried, gone


def mark_moved_up(new_flags: list[Flag], old_points: list[DecisionPoint], plan: Plan, new_text: str, old_text: str = "") -> None:
    """A flag counts as moved up when an up-check raised it after a revision and the same rule had not been raised on the same
    unit before (the same paragraph for Level 4, the same section for Level 3, anywhere for Levels 1 and 2)."""
    if plan.full:
        return
    new, old = parse_draft(new_text), parse_draft(old_text) if old_text else None

    def unit(draft, flag: Flag):
        where = draft.find_sentence(quote_segments(flag.quote)[0]) if draft else None
        if not where:
            return None
        paragraph = where[0]
        return (paragraph.heading, paragraph.number) if flag.level == "4" else paragraph.section

    before = {(f.level, f.rule, unit(old, f) if f.level in ("3", "4") else "all") for p in old_points for f in p.flags}
    for flag in new_flags:
        if flag.severity == "SUGGEST" or flag.level not in plan.up:
            continue
        scope = plan.up[flag.level]
        if "all" not in scope:
            where = new.find_sentence(quote_segments(flag.quote)[0])
            if not where or (where[0].index if flag.level == "4" else where[0].section) not in scope:
                continue
        here = unit(new, flag) if flag.level in ("3", "4") else "all"
        flag.moved_up = (flag.level, flag.rule, here) not in before


# ---------- rulings ----------

RULING_STATUSES = ("fixed", "taste", "answer", "later")


def read_rulings(path: Path | None) -> dict[str, tuple[str, str]]:
    """rulings.md: one line per question, `D-xxxxxxxx | fixed, taste, answer, or later | note` for a decision point, or the
    same with `R-xxxxxxxx` for a root question. Kept in the order written, so that a later line overrides an earlier one."""
    rulings: dict[str, tuple[str, str]] = {}
    if not path or not Path(path).exists():
        return rulings
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*[-*]?\s*([DR]-[0-9a-f]{8})\s*\|\s*(\w+)\s*(?:\|\s*(.*))?$", line)
        if match and match.group(2).lower() in RULING_STATUSES:
            rulings.pop(match.group(1), None)  # a repeated id moves to where it was last written
            rulings[match.group(1)] = (match.group(2).lower(), (match.group(3) or "").strip())
    return rulings


def _flag_status(flag: Flag, ruling: tuple[str, str] | None) -> str:
    if ruling is None:
        return "new" if flag.origin == "new" else "open"
    status = ruling[0]
    if status == "later":
        return "open"
    if status == "fixed":
        # Raised again only if a fresh check raised it, or its words are unchanged; a flag left stale by the revision is not.
        return "reappeared" if flag.origin == "new" or not flag.stale else "decided"
    if flag.severity == "CRITICAL" and flag.origin == "new":
        return "new"  # a decided question comes back only when a fresh check finds it critical
    return "decided"


def apply_rulings(points: list[DecisionPoint], rulings: dict[str, tuple[str, str]], roots: dict[str, set[str]] | None = None) -> None:
    """Set each flag's status from the rulings that name its decision point or a root question that settles it (the last one
    written counts), then each point's status from its flags: reappeared, new, open, or decided when no flag is left open."""
    roots = roots or {}
    for point in points:
        for flag in point.flags:
            ruling = None
            for rid, value in rulings.items():
                if rid == point.id or (rid in roots and flag_key(point.id, flag) in roots[rid]):
                    ruling = value
            flag.ruling = f"{ruling[0]}{': ' + ruling[1] if ruling[1] else ''}" if ruling else ""
            flag.status = _flag_status(flag, ruling)
        statuses = {f.status for f in point.flags}
        point.status = ("reappeared" if "reappeared" in statuses else "new" if "new" in statuses else
                        "open" if "open" in statuses else "decided")
        point.ruling = next((f.ruling for f in point.flags if f.ruling), "")


def read_priorities(personal: Path | None) -> set[str]:
    """Rules the author marked low priority in the personal layer's Priorities section (`- 4.4: low ...`)."""
    if not personal or not Path(personal).exists():
        return set()
    text = Path(personal).read_text(encoding="utf-8")
    section = re.search(r"^#+\s*Priorities\s*$(.*?)(?=^#+\s|\Z)", text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if not section:
        return set()
    return {m.group(1) for m in re.finditer(r"^\s*[-*]\s*(?:rule\s+)?([A-Z]?\d+(?:\.\d+)?|[A-Z]\.\d+)\s*:\s*low\b", section.group(1), re.MULTILINE | re.IGNORECASE)}


# ---------- learning from rulings ----------

@dataclass
class Proposal:
    rule: str
    taste: int
    decided: int
    examples: list[str]

    @property
    def line(self) -> str:
        return f"- {self.rule}: low (you ruled it a matter of taste {self.taste} of {self.decided} times)"


def learn(rulings: dict[str, tuple[str, str]], decision_files: list[Path], min_taste: int = 3, min_share: float = 0.6) -> list[Proposal]:
    """Propose lowering the priority of rules the author keeps ruling a matter of taste. Nothing changes without the author's yes."""
    rules_of: dict[str, set[str]] = {}
    quotes: dict[str, str] = {}
    for path in decision_files:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for p in data.get("points", []):
            rules_of.setdefault(p["id"], set()).update(f["rule"] for f in p["flags"] if f.get("rule"))
            quotes[p["id"]] = p.get("quote", "")
        for r in data.get("roots", []):  # a ruling on a root question counts for the rule of every flag it settled
            rules_of.setdefault(r["id"], set()).update(k.split("|")[2] for k in r.get("keys", []) if k.split("|")[2])
            quotes[r["id"]] = r.get("question", "")
    tally: dict[str, list] = {}
    for pid, (status, _) in rulings.items():
        if status == "later":
            continue
        for rule in rules_of.get(pid, ()):
            entry = tally.setdefault(rule, [0, 0, []])
            entry[1] += 1
            if status == "taste":
                entry[0] += 1
                entry[2].append(quotes.get(pid, "")[:100])
    return [Proposal(rule, t, n, ex) for rule, (t, n, ex) in sorted(tally.items()) if t >= min_taste and t / n >= min_share]


def apply_proposals(personal: Path, proposals: list[Proposal]) -> None:
    text = Path(personal).read_text(encoding="utf-8") if Path(personal).exists() else "# Personal layer\n"
    lines = "\n".join(p.line for p in proposals)
    if re.search(r"^#+\s*Priorities\s*$", text, re.MULTILINE | re.IGNORECASE):
        text = re.sub(r"(^#+\s*Priorities\s*$\n?)", r"\1" + lines.replace("\\", r"\\") + "\n", text, count=1, flags=re.MULTILINE | re.IGNORECASE)
    else:
        text = text.rstrip() + "\n\n## Priorities\n\nRules you rule a matter of taste again and again go last in your decisions. Checkers never see this section.\n\n" + lines + "\n"
    Path(personal).write_text(text, encoding="utf-8")
