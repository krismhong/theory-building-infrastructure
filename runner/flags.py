"""Parse level reports into flags and pass-down lists, merge flags into decision points, and render them."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field

from .draft import normalize, parse_draft

SEVERITY_ORDER = {"CRITICAL": 0, "ISSUE": 1, "SUGGEST": 2}
KIND_ORDER = {"fork": 0, "slip": 1, "": 2}

_TAG = re.compile(r"^[\s>*\-]*\**\[(CRITICAL|ISSUE|SUGGEST):?\]\**", re.MULTILINE)


@dataclass
class Flag:
    level: str
    severity: str
    rule: str
    location: str
    quote: str
    what_fails: str
    decision: str
    raw: str
    kind: str = ""  # "fork" (the author must choose the point) or "slip" (one repair restores what the draft already chose)
    origin: str = "new"  # "new" (raised by this run) or "carried" (from an earlier run)
    moved_up: bool = False  # raised by an up-check after a revision, and not present before it
    stale: bool = False  # carried, but the words it quotes changed and its level did not rerun there
    id: str = ""  # "D-xxxxxxxx.n": the decision point it belongs to and its place there, assigned at every merge
    report: str = ""  # the report it came from ("1", "4-2", "S"), so that a question can go back to the checker that raised it
    status: str = ""  # after the author's rulings: new, open, decided, or reappeared ("" before rulings are applied)
    ruling: str = ""  # the author's ruling that applies to it, if any
    note: str = ""  # what its checker answered when the organizer asked about it
    assessment: str = ""  # logic_defect, indeterminate, policy_note, reference_check; blank means legacy/unclassified
    ruleset: str = ""  # explicit report version; never infer a new version for old reports


@dataclass
class DecisionPoint:
    quote: str
    severity: str
    flags: list[Flag] = field(default_factory=list)
    position: int = 10**9
    id: str = ""
    status: str = "new"  # new, open (carried and unanswered), decided, reappeared (ruled fixed, raised again)
    ruling: str = ""

    @property
    def kind(self) -> str:
        kinds = {f.kind for f in self.flags}
        return "fork" if "fork" in kinds else ("slip" if "slip" in kinds else "")

    @property
    def levels(self) -> set[str]:
        return {f.level for f in self.flags if f.level != "S"}

    @property
    def moved_up(self) -> bool:
        return any(f.moved_up for f in self.flags)


def _field(block: str, name: str) -> str:
    match = re.search(rf"\**{name}\**\s*:\s*(.+)", block, re.IGNORECASE)
    if not match:
        return ""
    value = match.group(1).strip()
    return value.strip().strip('"').strip("“”").strip()


def parse_flags(report: str, level: str, source: str = "") -> list[Flag]:
    """Find every tagged flag in a level report, tolerating small format variations. `source` names the report."""
    flags = []
    starts = [m.start() for m in _TAG.finditer(report)]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(report)
        block = report[start:end]
        block = re.split(r"\n#{2,6}\s", block)[0]  # stop at the next heading
        severity = _TAG.match(block).group(1)
        rule_match = re.search(r"Rule\s+([A-Z]?\d+(?:\.\d+)?|[A-Z]\.\d+)", block)
        kind = _field(block, "Kind").lower()
        flags.append(
            Flag(
                level=level,
                severity=severity,
                rule=rule_match.group(1) if rule_match else "",
                location=_field(block, "Location"),
                quote=_field(block, "Quote"),
                what_fails=_field(block, "What fails"),
                decision=_field(block, "Decision"),
                raw=block.strip(),
                kind="fork" if kind.startswith("fork") else ("slip" if kind.startswith("slip") else ""),
                report=source,
                assessment=_field(block, "Assessment").lower(),
                ruleset=_field(report, "Ruleset"),
            )
        )
    return flags


def parse_pass_down(report: str) -> list[str]:
    """Return the items listed under every 'Pass down' heading in a report (a report may join several parts).

    A section that opens with "None" gives no items, even when a reason follows. When the section holds a list,
    only its list items count, each with any indented lines that continue it (such as a reason), so a checker's
    unindented sentences around the list are not passed down.
    """
    items: list[str] = []
    for match in re.finditer(r"^#{2,6}\s*Pass down\s*$(.*?)(?=^#{2,6}\s|\Z)", report, re.MULTILINE | re.DOTALL | re.IGNORECASE):
        raw = [line.rstrip() for line in match.group(1).splitlines() if line.strip()]
        if not raw or re.match(r"^\s*\(?none\b", raw[0], re.IGNORECASE):
            continue
        bullet = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")
        if not any(bullet.match(line) for line in raw):
            items.extend(line.strip() for line in raw)
            continue
        section: list[str] = []
        for line in raw:
            if bullet.match(line):
                section.append(bullet.sub("", line).strip())
            elif section and line[:1].isspace():
                section[-1] += " " + line.strip()
        items.extend(section)
    return items


def quote_segments(quote: str) -> list[str]:
    """The passages a flag's Quote field quotes: usually one, several when the checker quoted more than one place."""
    straight = quote.replace("“", '"').replace("”", '"')
    # The Quote field arrives with its outer quotation marks stripped, so restore them before pairing the rest.
    found = [s.strip() for s in re.findall(r'"([^"]+)"', '"' + straight + '"')] if '"' in straight else []
    found = [s for s in found if len(s) >= 3]
    return found if len(found) > 1 else [quote]


def _same_words(a: str, b: str) -> bool:
    shorter, longer = sorted((a, b), key=len)
    return a == b or (len(shorter) >= 25 and shorter in longer)


def _sentence_index(draft_text: str) -> tuple[list[str], list[int]]:
    """Every sentence of the draft, normalized, in order, with its offset in the normalized draft."""
    if not draft_text:
        return [], []
    draft_norm = normalize(draft_text)
    sentences, offsets, cursor = [], [], 0
    for paragraph in parse_draft(draft_text).paragraphs:
        for sentence in paragraph.sentences:
            key = normalize(sentence)
            found = draft_norm.find(key, cursor)
            sentences.append(key)
            offsets.append(found if found >= 0 else cursor)
            cursor = max(cursor, found if found >= 0 else cursor)
    return sentences, offsets


def _locate(key: str, sentences: list[str]) -> int | None:
    """The one sentence a quote falls in (or, for a quote longer than a sentence, the first sentence it covers)."""
    hits = [i for i, sentence in enumerate(sentences) if key in sentence]
    if not hits:
        hits = [i for i, sentence in enumerate(sentences) if sentence and sentence in key][:1]
    return hits[0] if len(hits) == 1 else None


def assign_flag_ids(points: list["DecisionPoint"]) -> None:
    """Name every flag by its decision point and its place there. The same reports always give the same names, so the
    organizer's report, the questions to checkers, and the merge all refer to the same flags."""
    for point in points:
        for n, flag in enumerate(point.flags, 1):
            flag.id = f"{point.id}.{n}"


def flag_key(point_id_: str, flag: Flag) -> str:
    """A name for a flag that holds across rounds: its sentence, its level, and its rule."""
    return f"{point_id_}|{flag.level}|{flag.rule}"


def point_id(anchor: str) -> str:
    """A stable name for a decision point: the same sentence (or the same quoted places) gives the same id."""
    return "D-" + hashlib.sha1(anchor.encode("utf-8")).hexdigest()[:8]


def merge_flags(flags: list[Flag], draft_text: str = "") -> list[DecisionPoint]:
    """Merge flags that point to the same sentence of the draft into one decision point.

    A flag whose quote falls in one sentence joins the other flags on that sentence. A flag whose quote cannot be placed
    in a single sentence merges only with flags quoting the same words. A flag that quotes several places stands alone,
    because it puts one decision about all of them.
    """
    sentences, offsets = _sentence_index(draft_text)
    draft_norm = normalize(draft_text)
    points: list[DecisionPoint] = []
    by_sentence: dict[int, int] = {}
    loose: list[tuple[str, int]] = []  # (quote key, point index) for flags not placed in one sentence
    for flag in flags:
        segments = [key for key in (normalize(s) for s in quote_segments(flag.quote)) if key]
        if not segments:
            segments = [normalize(flag.raw[:200])]
        target = None
        sentence = _locate(segments[0], sentences) if len(segments) == 1 else None
        if sentence is not None:
            target = by_sentence.get(sentence)
        elif len(segments) == 1:
            target = next((i for key, i in loose if _same_words(key, segments[0])), None)
        if target is None:
            if sentence is not None:
                position, anchor = offsets[sentence], sentences[sentence]
            else:
                # place the point where its first quoted passage appears in the draft (a heading, for example), else at the end
                placed = [offsets[i] for i in (_locate(key, sentences) for key in segments) if i is not None]
                found = [f for f in ((draft_norm.find(key) for key in segments) if draft_norm else []) if f >= 0]
                position = min(placed + found) if placed or found else 10**9
                anchor = " | ".join(segments)
            points.append(DecisionPoint(quote=flag.quote, severity=flag.severity, position=position, id=point_id(anchor)))
            target = len(points) - 1
            if sentence is not None:
                by_sentence[sentence] = target
            elif len(segments) == 1:
                loose.append((segments[0], target))
        point = points[target]
        point.flags.append(flag)
        if SEVERITY_ORDER[flag.severity] < SEVERITY_ORDER[point.severity]:
            point.severity = flag.severity
        if len(segments) == 1 and len(flag.quote) > len(point.quote):
            point.quote = flag.quote
    points.sort(key=lambda p: (p.position, SEVERITY_ORDER[p.severity]))
    return points


def _who(flag: Flag) -> str:
    if flag.level == "S":
        return f"Script, rule {flag.rule}"
    if flag.level == "W":
        return f"Word choice, rule {flag.rule}"
    return f"Level {flag.level}, rule {flag.rule}"


OPEN_STATUSES = ("", "new", "open", "reappeared")


def is_open(flag: Flag) -> bool:
    """Still for the author to decide: not decided by an earlier ruling."""
    return flag.status in OPEN_STATUSES


def severity_of(flags: list[Flag]) -> str:
    return min((f.severity for f in flags), key=lambda s: SEVERITY_ORDER[s]) if flags else "SUGGEST"


def kind_of(flags: list[Flag]) -> str:
    kinds = {f.kind for f in flags}
    return "fork" if "fork" in kinds else ("slip" if "slip" in kinds else "")


def _order(point: DecisionPoint, shown: list[Flag], low: set[str]) -> tuple:
    severity = severity_of(shown)
    all_low = severity != "CRITICAL" and all(f.rule in low for f in shown)
    return (not any(f.moved_up for f in shown), all_low, SEVERITY_ORDER[severity], KIND_ORDER[kind_of(shown)], point.position)


def point_block(n: int, point: DecisionPoint, shown: list[Flag], note: str = "") -> list[str]:
    """One decision point as the author reads it: its tags, the levels and rules that raised it, the passage it quotes,
    and each open flag with the decision it asks for."""
    tags = ", ".join(t for t in (severity_of(shown), kind_of(shown),
                                  "raised again" if any(f.status == "reappeared" for f in shown) else "",
                                  "carried over" if all(f.origin == "carried" for f in shown) else "",
                                  "words changed, not rechecked" if any(f.stale for f in shown) else "") if t)
    lines = [f"### {n}. {point.id} [{tags}] " + "; ".join(_who(f) for f in shown)]
    segments = quote_segments(point.quote) if point.quote else []
    if len(segments) > 1:
        lines.append("Quotes: " + "; ".join(f'"{segment}"' for segment in segments))
    elif point.quote:
        lines.append(f'Quote: "{point.quote}"')
    earlier = next((f.ruling for f in shown if f.status == "reappeared" and f.ruling), "")
    if earlier:
        lines.append(f"Your earlier ruling: {earlier}")
    if note:
        lines.append(note)
    for flag in shown:
        where = " (after your revision)" if flag.moved_up else (" (the words it quotes changed since it was raised; this level did not rerun there)" if flag.stale else "")
        classification = flag.assessment or "legacy unclassified"
        version = flag.ruleset or "unversioned"
        lines.append(f"- {_who(flag)} [{classification}; {version}]{where}: {flag.what_fails or flag.raw.splitlines()[0]}")
        if flag.decision:
            lines.append(f"  Decision: {flag.decision}")
        if flag.note:
            lines.append(f"  {flag.note}")
    lines.append("")
    return lines


def decided_lines(points: list[DecisionPoint]) -> list[str]:
    """What earlier rulings settled: a whole point in one line, or the settled flags of a point that is still partly open."""
    lines = []
    for point in sorted(points, key=lambda p: p.position):
        settled = [f for f in point.flags if not is_open(f)]
        if not settled:
            continue
        if len(settled) == len(point.flags):
            lines.append(f"- {point.id}: {settled[0].ruling or point.ruling} | \"{point.quote[:100]}\"")
        else:
            for flag in settled:
                lines.append(f"- {point.id}, {_who(flag)}: {flag.ruling} | \"{(flag.quote or point.quote)[:100]}\"")
    return lines


def digest_filter(shown: list[Flag]) -> bool:
    """Kept in a digest: CRITICAL, raised at two or more levels, or moved up by a revision."""
    return severity_of(shown) == "CRITICAL" or len({f.level for f in shown if f.level != "S"}) >= 2 or any(f.moved_up for f in shown)


def render_decisions(points: list[DecisionPoint], resolved: list[dict] | None = None, low_priority: set[str] | None = None,
                     digest: bool = False, title: str = "Decisions for the author") -> str:
    """Write the decision points for the author: what to decide first, then what was decided before and what was resolved.

    The order: points where a revision moved a problem up a level; then by severity; forks before slips; then the draft's order.
    Rules the author has marked low priority go last (never a CRITICAL). The digest keeps only CRITICAL points and points
    raised by two or more levels, the failures seen from more than one depth. A point shows only its open flags.
    """
    low = low_priority or set()
    shown = {id(p): [f for f in p.flags if is_open(f)] for p in points}
    to_decide = [p for p in points if shown[id(p)]]
    decided = [p for p in points if not shown[id(p)]]
    if digest:
        to_decide = [p for p in to_decide if digest_filter(shown[id(p)])]
    to_decide.sort(key=lambda p: _order(p, shown[id(p)], low))
    forks = sum(1 for p in to_decide if kind_of(shown[id(p)]) == "fork")
    slips = sum(1 for p in to_decide if kind_of(shown[id(p)]) == "slip")
    flags = sum(len(p.flags) for p in points)
    lines = [f"# {title}", ""]
    lines.append(f"{len(to_decide)} to decide ({forks} forks, {slips} slips), merged from {flags} flags"
                 + (f"; {len(decided)} decided before" if decided else "")
                 + (f"; {len(resolved)} resolved since the last check" if resolved else "")
                 + (". Digest: only CRITICAL points and points raised at two or more levels." if digest else "."))
    lines.append("")
    lines.append("A **fork** asks which version of the point you mean; only you can choose. A **slip** departs from a choice the draft "
                 "already made; one repair restores it. Answer in `rulings.md`, one line per point: "
                 "`D-xxxxxxxx | fixed, taste, answer, or later | your note`.")
    lines.append("")
    moved = [p for p in to_decide if any(f.moved_up for f in shown[id(p)])]
    recheck = any(f.origin == "carried" for p in points for f in p.flags)
    fresh = [p for p in to_decide if p not in moved and any(f.origin == "new" for f in shown[id(p)])]
    still = [p for p in to_decide if p not in moved and p not in fresh]
    if recheck:
        lines.insert(3, f"This round raised {len(moved) + len(fresh)} of them; {len(still)} are still open from earlier rounds.")
        lines.insert(4, "")
    groups: list[tuple[list[str], list[DecisionPoint]]] = []
    if moved:
        groups.append((["## Your revision moved up a level: decide these first", "",
                        "A change you made put the unit above it out of step. The check went one level up on its own and stopped: "
                        "whether the point itself changes is your call.", ""], moved))
    if recheck:
        groups += [(["## New this round", ""], fresh), (["## Still open from earlier rounds", ""], still)]
    else:
        groups.append((["## To decide", ""] if moved else [], fresh + still))
    n = 0
    for heading, group in groups:
        if not group:
            continue
        lines.extend(heading)
        for point in group:
            n += 1
            lines.extend(point_block(n, point, shown[id(point)]))
    settled = decided_lines(points)
    if settled:
        lines += ["## Decided before (not asked again)", ""] + settled + [""]
    if resolved:
        lines.append("## Gone since the last check (rechecked where the words changed, and not raised again)")
        lines.append("")
        for item in resolved:
            lines.append(f"- {item['id']}: \"{item['quote'][:100]}\"")
        lines.append("")
    return "\n".join(lines)


def points_to_json(points: list[DecisionPoint], resolved: list[dict] | None = None, extra: dict | None = None) -> str:
    return json.dumps({"points": [dict(asdict(p), kind=p.kind) for p in points], "resolved": resolved or [], **(extra or {})}, indent=1)


def points_from_json(text: str) -> list[DecisionPoint]:
    data = json.loads(text)
    points = []
    for p in data.get("points", []):
        flags = [Flag(**f) for f in p.pop("flags")]
        p.pop("kind", None)
        points.append(DecisionPoint(flags=flags, **p))
    return points
