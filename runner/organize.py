"""The organizer: a traffic controller for the level checkers.

After every checker has reported on its own, the organizer routes each flag down the nest to the checkers whose parts of
the draft it covers: the model's and the headings' flags to every checker below them, a paragraph-level flag to the checkers
of its section, a sentence-level flag to the checker of that paragraph's clauses. It reads where a flag sits, not what it
says. The judging is the checkers' own. Each checker says of each of its flags whether it stands, follows from a flag above
it (the author's answer there would settle it), or rests on a misreading; and it may dispute a flag above it, which that
flag's own checker then keeps, revises, or withdraws. A flag that others follow becomes a root question: its question is its
own checker's decision, not a new text, and the flags that follow it go under it. Nothing leaves the list except by the
checker that raised it.
"""

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .draft import Draft, parse_draft
from .flags import (SEVERITY_ORDER, DecisionPoint, Flag, _field, _order, _who, decided_lines, digest_filter, flag_key, is_open,
                    point_block, quote_segments, severity_of)
from .prompts import ROOT, _read

CONFERRING_FILE = "checker/CONFERRING.md"
ANSWERING_FILE = "checker/ANSWERING.md"
VERDICTS = ("keep", "revise", "withdraw")


@dataclass
class Reply:
    flag_id: str
    verdict: str  # stands, follows, or withdraw
    target: str = ""  # for follows: the flag whose answer settles this one
    reason: str = ""


@dataclass
class Dispute:
    number: int
    by_flag: str  # the disputing checker's report label
    by_level: str
    target: str  # the flag above that the checker disputes
    reason: str
    report: str = ""  # the target flag's report label
    verdict: str = ""  # keep, revise, or withdraw, once its checker answers
    answer: str = ""


@dataclass
class Root:
    id: str
    flag_id: str  # the flag whose decision the author answers
    followers: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)  # follower -> its checker's account of how the answer settles it
    keys: list[str] = field(default_factory=list)  # the root and its followers, named so that the name holds across rounds


@dataclass
class Organized:
    roots: list[Root] = field(default_factory=list)
    replies: list[Reply] = field(default_factory=list)
    disputes: list[Dispute] = field(default_factory=list)
    withdrawn: list[dict] = field(default_factory=list)  # {"flag": Flag as a dict, "reason": ..., "after": ...}
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"roots": [asdict(r) for r in self.roots], "replies": [asdict(r) for r in self.replies],
                "disputes": [asdict(d) for d in self.disputes], "withdrawn": self.withdrawn, "organizer_notes": self.notes}


def flag_index(points: list[DecisionPoint]) -> dict[str, tuple[DecisionPoint, Flag]]:
    return {f.id: (p, f) for p in points for f in p.flags}


def askable(flag: Flag) -> bool:
    """A flag's checker can be asked only if it ran in this round: not a carried flag, not the script, not word choice."""
    return flag.origin == "new" and flag.level not in ("S", "W") and bool(flag.report)


def _rank(flag: Flag) -> int:
    return int(flag.level) if flag.level.isdigit() else 9


# ---------- where a flag sits, and what lies under it ----------

def flag_units(flag: Flag, draft: Draft) -> set[int] | None:
    """The paragraphs a flag's quoted passages fall in; None when a passage cannot be placed (it then counts as everywhere)."""
    units = set()
    for segment in quote_segments(flag.quote) if flag.quote else []:
        found = draft.find_sentence(segment)
        if not found:
            key = re.sub(r"\s+", " ", segment).strip().lower()
            hits = [p.index for p in draft.paragraphs if key and key in re.sub(r"\s+", " ", p.text).lower()]
            if len(hits) != 1:
                return None
            units.add(hits[0])
        else:
            units.add(found[0].index)
    return units or None


def covers(flag: Flag, draft: Draft) -> set[int] | None:
    """The paragraphs a flag stands above in the nest: everything for the model and the headings (None), the whole section
    for a flag on a topic sentence, the paragraph itself for a flag on a sentence."""
    if flag.level in ("1", "2"):
        return None
    units = flag_units(flag, draft)
    if units is None:
        return None
    if flag.level == "3":
        sections = {p.section for p in draft.paragraphs if p.index in units}
        return {p.index for p in draft.paragraphs if p.section in sections}
    return units


def routes(points: list[DecisionPoint], draft: Draft) -> dict[str, tuple[list[Flag], list[Flag]]]:
    """For each checker of this round: its open flags that some flag above it covers, and those flags above, once each."""
    flags = [f for p in points for f in p.flags if is_open(f)]
    cover = {f.id: covers(f, draft) for f in flags if f.level in ("1", "2", "3", "4")}
    out: dict[str, tuple[list[Flag], list[Flag]]] = {}
    for flag in flags:
        if not askable(flag) or flag.level == "1":
            continue
        units = flag_units(flag, draft)
        above = [h for h in flags if h.id in cover and _rank(h) < _rank(flag)
                 and (cover[h.id] is None or units is None or cover[h.id] & units)]
        if not above:
            continue
        own, higher = out.setdefault(flag.report, ([], []))
        own.append(flag)
        higher.extend(h for h in above if h not in higher)
    for own, higher in out.values():
        higher.sort(key=lambda h: (_rank(h), h.id))
    return out


def _flag_lines(flag: Flag) -> list[str]:
    quote = "; ".join(f'"{q}"' for q in quote_segments(flag.quote)) if flag.quote else ""
    lines = [f"{flag.id} | {_who(flag)} | {flag.severity}{', ' + flag.kind if flag.kind else ''}"]
    for name, value in (("Location", flag.location), ("Quote", quote), ("What fails", flag.what_fails), ("Decision", flag.decision)):
        if value:
            lines.append(f"{name}: {value}")
    return lines


def route_text(own: list[Flag], higher: list[Flag], reply_path: Path | None = None) -> str:
    """What the traffic controller delivers to one checker: the flags above its own, and the form of its reply."""
    lines = [_read(ROOT / CONFERRING_FILE).rstrip(), ""]
    lines.append(f"Write your reply to `{reply_path}`." if reply_path else "Reply with your reply only, in this form.")
    lines += ["", "# Your flags", ""]
    for flag in own:
        lines += _flag_lines(flag) + [""]
    lines += ["# Flags above yours", ""]
    for flag in higher:
        lines += _flag_lines(flag) + [""]
    return "\n".join(lines)


# ---------- the checkers' replies ----------

def parse_reply(text: str) -> tuple[list[Reply], list[tuple[str, str]]]:
    """A checker's reply: one line per flag of its own, and any disputes of flags above."""
    replies, disputes = [], []
    section = ""
    for line in text.splitlines():
        heading = re.match(r"^#{1,6}\s*(.+?)\s*$", line)
        if heading:
            section = heading.group(1).lower()
            continue
        item = re.match(r"^\s*[-*]?\s*\**(D-[0-9a-f]{8}\.\d+)\**\s*\|\s*(.*)$", line)
        if not item:
            continue
        fid, parts = item.group(1), [part.strip() for part in item.group(2).split("|")]
        if section.startswith("dispute"):
            disputes.append((fid, " | ".join(p for p in parts if p)))
            continue
        word = parts[0].lower()
        if word.startswith("follow"):
            found = re.search(r"D-[0-9a-f]{8}\.\d+", " ".join(parts[:2]))
            rest = parts[2:] if len(parts) > 1 and re.search(r"D-[0-9a-f]{8}\.\d+", parts[1]) else parts[1:]
            replies.append(Reply(fid, "follows", found.group(0) if found else "", " | ".join(p for p in rest if p)))
        elif word.startswith("withdraw"):
            replies.append(Reply(fid, "withdraw", "", " | ".join(p for p in parts[1:] if p)))
        elif word.startswith("stand"):
            replies.append(Reply(fid, "stands", "", " | ".join(p for p in parts[1:] if p)))
    return replies, disputes


def dispute_list(replies_by_label: dict[str, tuple[list[Reply], list[tuple[str, str]]]], points: list[DecisionPoint]) -> list[Dispute]:
    index = flag_index(points)
    out = []
    for label, (_, disputes) in sorted(replies_by_label.items()):
        for target, reason in disputes:
            level = label.split("-", 1)[0]
            dispute = Dispute(number=len(out) + 1, by_flag=label, by_level=level, target=target, reason=reason)
            if target in index and askable(index[target][1]):
                dispute.report = index[target][1].report
            out.append(dispute)
    return out


def dispute_text(disputes: list[Dispute], points: list[DecisionPoint], answer_path: Path | None = None) -> str:
    """What the traffic controller delivers to the checker of a disputed flag: the dispute, and the form of an answer."""
    index = flag_index(points)
    lines = [_read(ROOT / ANSWERING_FILE).rstrip(), ""]
    lines.append(f"Write your answers to `{answer_path}`." if answer_path else "Reply with your answers only, in this form.")
    for dispute in disputes:
        flag = index[dispute.target][1]
        lines += ["", f"# Question Q{dispute.number}, about your flag {dispute.target}", "", "Your flag, as you wrote it:", "", flag.raw, "",
                  f"The checker at Level {dispute.by_level} disputes it: {dispute.reason}"]
    return "\n".join(lines) + "\n"


def disputes_by_report(disputes: list[Dispute]) -> dict[str, list[Dispute]]:
    out: dict[str, list[Dispute]] = {}
    for dispute in disputes:
        if dispute.report:
            out.setdefault(dispute.report, []).append(dispute)
    return out


@dataclass
class Answer:
    verdict: str
    reason: str
    tag: str = ""
    what_fails: str = ""
    decision: str = ""
    kind: str = ""


def _sections(text: str) -> list[tuple[str, str]]:
    heads = list(re.finditer(r"^#{1,6}\s*(.+?)\s*$", text, re.MULTILINE))
    return [(h.group(1), text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]) for i, h in enumerate(heads)]


def parse_answers(text: str) -> dict[int, Answer]:
    answers = {}
    for heading, body in _sections(text):
        number = re.match(r"(?:question\s+)?Q(\d+)", heading, re.IGNORECASE)
        if not number:
            continue
        verdict = _field(body, "Verdict").lower()
        verdict = next((v for v in VERDICTS if verdict.startswith(v)), verdict)
        tag = _field(body, "Tag").upper().strip("[]:")
        kind = _field(body, "Kind").lower()
        answers[int(number.group(1))] = Answer(verdict=verdict, reason=_field(body, "Reason"), tag=tag if tag in SEVERITY_ORDER else "",
                                               what_fails=_field(body, "What fails"), decision=_field(body, "Decision"),
                                               kind="fork" if kind.startswith("fork") else "slip" if kind.startswith("slip") else "")
    return answers


# ---------- carrying out what the checkers said ----------

def root_id(keys: list[str], question: str) -> str:
    return "R-" + hashlib.sha1(("|".join(sorted(keys)) + "\n" + question).encode("utf-8")).hexdigest()[:8]


def _withdraw(points: list[DecisionPoint], flag: Flag, organized: Organized, reason: str, after: str) -> None:
    for point in points:
        if flag in point.flags:
            point.flags.remove(flag)
    organized.withdrawn.append({"flag": asdict(flag), "reason": reason, "after": after})


def resolve(points: list[DecisionPoint], replies_by_label: dict[str, tuple[list[Reply], list[tuple[str, str]]]],
            answers_by_label: dict[str, dict[int, Answer]], routed: dict[str, tuple[list[Flag], list[Flag]]]) -> tuple[list[DecisionPoint], Organized]:
    """Carry out the checkers' replies and answers, then gather each flag under the root it follows. Returns the points
    that still hold a flag, and what the organizer did."""
    organized = Organized()
    index = flag_index(points)
    offered = {label: ({f.id for f in own}, {h.id for h in higher}) for label, (own, higher) in routed.items()}

    # Disputes first: a flag its own checker withdraws cannot be followed.
    organized.disputes = dispute_list(replies_by_label, points)
    for dispute in organized.disputes:
        if dispute.target not in index:
            organized.notes.append(f"Level {dispute.by_level} disputes {dispute.target}, which is not a flag of this round; ignored.")
            continue
        if not dispute.report:
            organized.notes.append(f"Level {dispute.by_level} disputes {dispute.target}, whose checker is not in this round; shown to you, not sent.")
            continue
        answer = answers_by_label.get(dispute.report, {}).get(dispute.number)
        if answer is None or answer.verdict not in VERDICTS:
            organized.notes.append(f"Level {dispute.by_level}'s dispute of {dispute.target} got no usable answer; the flag stands as raised.")
            continue
        dispute.verdict, dispute.answer = answer.verdict, answer.reason
        flag = index[dispute.target][1]
        if answer.verdict == "withdraw":
            _withdraw(points, flag, organized, answer.reason, f"Level {dispute.by_level} disputed it: {dispute.reason}")
        elif answer.verdict == "revise":
            flag.severity = answer.tag or flag.severity
            flag.what_fails = answer.what_fails or flag.what_fails
            flag.decision = answer.decision or flag.decision
            flag.kind = answer.kind or flag.kind
            flag.note = f"Level {dispute.by_level} disputed this flag ({dispute.reason}); its checker revised it: {answer.reason}"
        else:
            flag.note = f"Level {dispute.by_level} disputed this flag ({dispute.reason}); its checker kept it: {answer.reason}"

    # Each checker's replies about its own flags.
    links: dict[str, Reply] = {}
    for label, (replies, _) in sorted(replies_by_label.items()):
        mine, above = offered.get(label, (set(), set()))
        for reply in replies:
            if reply.flag_id not in mine:
                organized.notes.append(f"The checker of report {label} replied about {reply.flag_id}, which was not routed to it; ignored.")
                continue
            organized.replies.append(reply)
            flag = index[reply.flag_id][1]
            if reply.verdict == "withdraw":
                _withdraw(points, flag, organized, reply.reason, "")
            elif reply.verdict == "follows":
                if reply.target not in mine | above or reply.target == reply.flag_id:
                    organized.notes.append(f"{reply.flag_id} names {reply.target or 'no flag'} to follow, which was not among the flags "
                                           "routed to its checker; it stands.")
                else:
                    links[reply.flag_id] = reply
        missing = mine - {r.flag_id for r in replies}
        if missing:
            organized.notes.append(f"The checker of report {label} did not reply about {', '.join(sorted(missing))}; "
                                   "those flags stand.")

    present = {f.id for p in points for f in p.flags}
    # The script's flags go under a checker's flag with the same rule on the same passage.
    for point in points:
        for flag in point.flags:
            if flag.level == "S" and is_open(flag):
                same = sorted((f for f in point.flags if f.level != "S" and f.rule == flag.rule and is_open(f)), key=_rank)
                if same:
                    links[flag.id] = Reply(flag.id, "follows", same[0].id, "The script's check of the same rule on the same passage.")

    def top(fid: str) -> str:
        seen = [fid]
        while fid in links and links[fid].target in present:
            fid = links[fid].target
            if fid in seen:  # a circle of flags that follow one another: the highest level among them leads
                return min(seen[seen.index(fid):], key=lambda f: (_rank(index[f][1]), f))
            seen.append(fid)
        return fid

    groups: dict[str, list[str]] = {}
    for fid, reply in links.items():
        if fid not in present:
            continue
        if reply.target not in present:
            organized.notes.append(f"{fid} followed {reply.target}, which its checker withdrew; {fid} stands.")
            continue
        head = top(fid)
        if head != fid:
            groups.setdefault(head, []).append(fid)
    for head, followers in groups.items():
        followers = sorted(set(followers), key=lambda f: (_rank(index[f][1]), f))
        keys = [flag_key(index[f][0].id, index[f][1]) for f in [head] + followers]
        organized.roots.append(Root(id=root_id(keys, index[head][1].decision), flag_id=head, followers=followers,
                                    reasons={f: links[f].reason for f in followers if f in links}, keys=keys))
    kept = [p for p in points if p.flags]
    for point in kept:
        point.severity = severity_of(point.flags)
    return kept, organized


# ---------- what the author reads ----------

def _levels_phrase(flags: list[Flag]) -> str:
    numbers = sorted({f.level for f in flags if f.level.isdigit()})
    parts = []
    if numbers:
        parts.append(("Level " if len(numbers) == 1 else "Levels ") + (", ".join(numbers[:-1]) + " and " + numbers[-1] if len(numbers) > 1 else numbers[0]))
    parts += [name for code, name in (("S", "the script"), ("W", "the word-choice pass")) if any(f.level == code for f in flags)]
    return " and ".join(parts)


def _where(flag: Flag, draft: Draft | None) -> str:
    for segment in quote_segments(flag.quote) if flag.quote else []:
        found = draft.find_sentence(segment) if draft else None
        if found:
            return found[0].location(found[1])
    return flag.location


def render_organized(points: list[DecisionPoint], organized: Organized, resolved: list[dict] | None = None,
                     low_priority: set[str] | None = None, digest: bool = False, draft_text: str = "") -> str:
    """The decisions after the checkers conferred: root questions first (a flag that others follow, with its followers under
    it), in order of reach; then the flags that stand alone; then what was decided before, what is gone, and what was withdrawn."""
    low = low_priority or set()
    draft = parse_draft(draft_text) if draft_text else None
    index = flag_index(points)
    under: dict[str, str] = {}
    live = []
    for root in organized.roots:
        if root.flag_id not in index or not is_open(index[root.flag_id][1]):
            continue
        followers = [index[f][1] for f in root.followers if f in index and is_open(index[f][1])]
        if followers:
            live.append((root, index[root.flag_id], followers))
            under[root.flag_id] = root.id
            under.update({f.id: root.id for f in followers})
    live.sort(key=lambda r: (not any(f.moved_up for f in [r[1][1]] + r[2]), -len(r[2]), SEVERITY_ORDER[severity_of([r[1][1]] + r[2])],
                             _rank(r[1][1]), r[1][0].position))
    singles = [(p, [f for f in p.flags if is_open(f) and f.id not in under]) for p in points]
    singles = [(p, s) for p, s in singles if s]
    if digest:
        singles = [(p, s) for p, s in singles if digest_filter(s)]
    singles.sort(key=lambda ps: _order(ps[0], ps[1], low))
    moved = [(p, s) for p, s in singles if any(f.moved_up for f in s)]
    rest = [(p, s) for p, s in singles if not any(f.moved_up for f in s)]

    total = sum(len(p.flags) for p in points) + len(organized.withdrawn)
    in_roots = sum(1 + len(f) for _, _, f in live)
    decided = sum(1 for p in points if not any(is_open(f) for f in p.flags))
    reads = len(live) + sum(len(s) for _, s in singles)
    lines = ["# Decisions for the author", ""]
    lines.append(f"{len(live) + len(singles)} questions to decide: {len(live)} root questions that settle {in_roots} flags, and "
                 f"{len(singles)} single points; {reads} decisions to read in all. They come from {total} flags"
                 + (f"; {decided} points were decided before" if decided else "")
                 + (f"; {len(resolved)} are gone since the last check" if resolved else "")
                 + (". Digest: root questions, and single points that are CRITICAL or raised at two or more levels." if digest else "."))
    follows = sum(1 for r in organized.replies if r.verdict == "follows")
    lines.append("")
    disputed = len(organized.disputes)
    lines.append(f"After the checkers reported, the organizer routed each flag to the checkers below it in the nest. They said {follows} of "
                 f"their flags follow from a flag above, withdrew {len(organized.withdrawn)}, and disputed {disputed} flag{'s' if disputed != 1 else ''} above theirs.")
    lines.append("")
    lines.append("A **root question** is a flag whose answer settles the flags under it: the same problem, seen from lower levels, as their "
                 "own checkers judged. A **fork** asks which version of the point you mean; only you can choose. A **slip** departs from "
                 "a choice the draft already made; one repair restores it. Answer in `rulings.md`, one line per question: "
                 "`R-xxxxxxxx | fixed, taste, answer, or later | your note` for a root question, and the same with `D-xxxxxxxx` for a "
                 "single point. `decisions-flat.md` lists every flag as the checkers raised it.")
    lines.append("")
    n = 0
    if moved:
        lines += ["## Your revision moved up a level: decide these first", "",
                  "A change you made put the unit above it out of step. The check went one level up on its own and stopped: "
                  "whether the point itself changes is your call.", ""]
        for point, shown in moved:
            n += 1
            lines.extend(point_block(n, point, shown))
    if live:
        lines += ["## Root questions: answer these first", ""]
        for root, (point, flag), followers in live:
            n += 1
            passages = len({f.id.rsplit(".", 1)[0] for f in [flag] + followers})
            tags = ", ".join(t for t in (severity_of([flag] + followers), flag.kind) if t)
            lines.append(f"### {n}. {root.id} [{tags}] {_who(flag)}: settles {len(followers)} more flag{'s' if len(followers) != 1 else ''} "
                         f"from {_levels_phrase(followers)}, on {passages} passage{'s' if passages != 1 else ''}")
            quote = "; ".join(f'"{q}"' for q in quote_segments(flag.quote)) if flag.quote else ""
            if quote:
                lines.append(f"Quote: {quote}")
            lines.append(f"What fails: {flag.what_fails or flag.raw.splitlines()[0]}")
            lines.append(f"Assessment: {flag.assessment or 'legacy unclassified'}; Ruleset: {flag.ruleset or 'unversioned'}")
            lines.append(f"Decision: {flag.decision}")
            if flag.note:
                lines.append(flag.note)
            lines.append("Your answer here settles:")
            for follower in followers:
                lines.append(f"  Assessment: {follower.assessment or 'legacy unclassified'}; Ruleset: {follower.ruleset or 'unversioned'}")
                fq = "; ".join(f'"{q}"' for q in quote_segments(follower.quote)) if follower.quote else ""
                where = _where(follower, draft)
                reason = root.reasons.get(follower.id, "")
                lines.append(f"- {_who(follower)}, on {fq}{' (' + where + ')' if where else ''}." + (f" {reason}" if reason else ""))
            lines.append("")
    if rest:
        lines += ["## Single points" if live else "## To decide", ""]
        for point, shown in rest:
            n += 1
            elsewhere = sorted({under[f.id] for f in point.flags if f.id in under})
            lines.extend(point_block(n, point, shown, note=f"Other flags on this passage are under {', '.join(elsewhere)}." if elsewhere else ""))
    settled = decided_lines(points)
    if settled:
        lines += ["## Decided before (not asked again)", ""] + settled + [""]
    if resolved:
        lines += ["## Gone since the last check (rechecked where the words changed, and not raised again)", ""]
        lines += [f"- {item['id']}: \"{item['quote'][:100]}\"" for item in resolved] + [""]
    if organized.withdrawn:
        lines += ["## Withdrawn by their own checkers", ""]
        for item in organized.withdrawn:
            flag = Flag(**item["flag"])
            after = f" {item['after'].rstrip('.')}." if item.get("after") else ""
            lines.append(f"- {flag.id}, {_who(flag)}, on \"{flag.quote}\".{after} Its checker withdrew it: {item['reason']}")
        lines.append("")
    if organized.notes:
        lines += ["## Notes on this round", ""] + [f"- {note}" for note in organized.notes] + [""]
    return "\n".join(lines)
