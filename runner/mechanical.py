"""Offline regex observations, not semantic logic validation.

Supported author-year matching has limited coverage and can misread formats.
Quantifiers raise context questions, not proven failures; user word lists are policy
notes. Normative wording alone is not flagged. All observations need author review.
"""

import re
from dataclasses import dataclass

from .draft import Draft, Paragraph, is_references, normalize, parse_draft
from .prompts import RULESET_ID

_YEAR = r"(?:1[89]\d{2}|20\d{2})[a-z]?|n\.d\."
_PREFIXES = re.compile(r"^(?:e\.g\.,?|i\.e\.,?|see(?: also)?|cf\.|for example,?|for a review,? see|as cited in|compare)\s+", re.IGNORECASE)
_ABSOLUTES = re.compile(r"\b(always|never|invariably|without exception|in every case|necessarily)\b", re.IGNORECASE)


@dataclass
class Citation:
    authors: str  # the author text as written (for narrative citations, the words before the year)
    year: str
    shown: str  # how the citation appears, for the flag's quote
    paragraph: Paragraph
    sentence: int


@dataclass
class Entry:
    first_author: str
    year: str
    text: str


def _strip_quotes(sentence: str) -> str:
    """Remove quoted material, which the author reports rather than asserts."""
    return re.sub(r"[\"“][^\"”]{0,400}[\"”]", " ", sentence)


def _surname_key(name: str) -> str:
    return normalize(name).replace(" ", "")


def reference_entries(draft: Draft) -> list[Entry]:
    entries = []
    for paragraph in draft.paragraphs:
        if not is_references(paragraph.section):
            continue
        match = re.search(rf"\(({_YEAR}|in press)\)", paragraph.text)
        if not match:
            continue
        author_part = paragraph.text[: match.start()].strip()
        person = re.match(r"^(.+?),\s+[A-Z][.\-]", author_part)  # "Surname, X." (particles such as "van" included)
        first = person.group(1) if person else author_part.rstrip(". ")  # an organization as author
        entries.append(Entry(first_author=first.strip(), year=match.group(1), text=paragraph.text))
    return entries


def in_text_citations(draft: Draft) -> list[Citation]:
    found = []
    for paragraph in draft.paragraphs:
        if is_references(paragraph.section) or paragraph.section == "(front matter)":
            continue
        for number, sentence in enumerate(paragraph.sentences, 1):
            # Parenthetical: (Author, 2014; Author & Author, 2017, p. 3)
            for group in re.finditer(r"\(([^()]*?(?:" + _YEAR + r")[^()]*)\)", sentence):
                for item in group.group(1).split(";"):
                    item = _PREFIXES.sub("", item.strip())
                    match = re.match(rf"^(.+?),\s*((?:{_YEAR})(?:\s*,\s*(?:{_YEAR}))*)", item)
                    if not match or not re.match(r"^[A-Z]|^(?:van|von|de|der|di|du|le|la|da|del|dos)\s", match.group(1)):
                        continue
                    for year in re.findall(_YEAR, match.group(2)):
                        found.append(Citation(match.group(1), year, f"{match.group(1)}, {year}", paragraph, number))
            # Narrative: Author (2019), Author and Author (2017), Author et al. (2014), Author's (2019)
            for match in re.finditer(rf"\((({_YEAR})(?:\s*,\s*(?:{_YEAR}))*)(?:,\s*pp?\.\s*[\d\-–]+)?\)", sentence):
                before = sentence[: match.start()].rstrip()
                window = re.split(r"[.;:()]\s", before)[-1][-120:]
                name = re.search(r"((?:[A-Z][\w'’\-]+|(?:van|von|de|der|di|du|le|la|da|del|dos)\s[A-Z][\w'’\-]+)(?:\s+et al\.)?)(?:['’]s)?\s*$", window)
                if not name:
                    continue
                for year in re.findall(_YEAR, match.group(1)):
                    found.append(Citation(window, year, f"{name.group(1)} ({year})", paragraph, number))
    return found


def _names(citation: Citation, entry: Entry) -> bool:
    name = normalize(entry.first_author)
    return bool(name) and re.search(rf"\b{re.escape(name)}\b", normalize(citation.authors)) is not None


def _cites(citation: Citation, entry: Entry) -> bool:
    return citation.year == entry.year and _names(citation, entry)


def _flag(severity: str, rule: str, location: str, quote: str, fails: str, decision: str, kind: str) -> str:
    assessment = "reference_check" if rule == "5.8" else "policy_note" if rule.startswith("P.") else "indeterminate"
    return (f"[{severity}:] Rule {rule}. Location: {location}\nQuote: \"{quote}\"\nWhat fails: {fails}\n"
            f"Decision: {decision}\nKind: {kind}\nAssessment: {assessment}\n")


def _window(sentence: str, match: re.Match, before: int = 8, after: int = 10) -> str:
    """A verbatim stretch of the sentence around a match, so the quote locates its sentence."""
    head = sentence[: match.start()].split()
    tail = sentence[match.end():].split()
    start = " ".join(head[-before:])
    end = " ".join(tail[:after])
    text = f"{start} {match.group(0)} {end}".strip()
    return text if text in sentence else sentence


def personal_words(personal_text: str, heading: str = "Words to flag") -> list[tuple[str, str]]:
    """Words the author asked to be flagged, from the personal layer's "Words to flag" list: `- term -> plainer word`.
    The same form serves a project layer's "Terms to avoid"."""
    section = re.search(rf"^#+\s*{heading}\s*$(.*?)(?=^#+\s|\Z)", personal_text or "", re.MULTILINE | re.DOTALL | re.IGNORECASE)
    pairs = []
    for line in (section.group(1).splitlines() if section else []):
        match = re.match(r"^\s*[-*]\s*(.+?)\s*(?:->|→)\s*(.*)$", line)
        if match:
            pairs.append((match.group(1).strip(), match.group(2).strip()))
        elif re.match(r"^\s*[-*]\s*\S", line):
            pairs.append((re.sub(r"^\s*[-*]\s*", "", line).strip(), ""))
    return pairs


@dataclass
class ScriptResult:
    report: str
    flags: int
    checked_citations: bool  # False when the draft has no author-year citations the script could read


def script_pass(draft_text: str, personal_text: str = "", project_text: str = "") -> ScriptResult:
    draft = parse_draft(draft_text)
    flags: list[str] = []

    entries = reference_entries(draft)
    citations = in_text_citations(draft)
    checked = bool(entries and citations)
    if checked:
        unmatched = [c for c in citations if not any(_cites(c, e) for e in entries)]
        seen = set()
        for c in unmatched:
            key = (_surname_key(c.shown), c.year)
            if key in seen:
                continue
            seen.add(key)
            near = [e for e in entries if _names(c, e) and e.year != c.year]
            hint = f" The reference list has {near[0].first_author} ({near[0].year}); is this the same source with a different year?" if near else ""
            flags.append(_flag(
                "ISSUE", "5.8", c.paragraph.location(c.sentence), c.shown,
                f"The draft cites {c.shown} but the reference list has no entry for it.{hint}",
                f"Add the reference entry for {c.shown}, or correct or remove the citation?", "slip"))
        for e in entries:
            if not any(_cites(c, e) for c in citations):
                flags.append(_flag(
                    "ISSUE", "5.8", "References", e.text[:160],
                    f"The reference list has an entry for {e.first_author} ({e.year}) that the draft never cites.",
                    "Cite this source where the draft relies on it, or remove the entry?", "slip"))

    words = personal_words(personal_text)
    terms = personal_words(project_text, "Terms to avoid")
    for paragraph in draft.paragraphs:
        if is_references(paragraph.section) or paragraph.section == "(front matter)":
            continue
        for number, sentence in enumerate(paragraph.sentences, 1):
            own = _strip_quotes(sentence)
            for match in _ABSOLUTES.finditer(own):
                if match.group(0).lower() == "necessarily" and re.search(r"\bnot\s+necessarily\b", own, re.IGNORECASE):
                    continue
                quote_match = re.search(re.escape(match.group(0)), sentence)
                flags.append(_flag(
                    "SUGGEST", "4.4", paragraph.location(number), _window(sentence, quote_match),
                    f"\"{match.group(0)}\" claims the effect without exception; the claim holds only if its support shows no exception.",
                    f"Does the support show \"{match.group(0)}\", or a weaker claim (\"can\", \"often\", \"under these conditions\")?", "fork"))
            for term, plain in words:
                hit = re.search(rf"\b{re.escape(term)}\b", own, re.IGNORECASE)
                if hit:
                    quote_match = re.search(re.escape(hit.group(0)), sentence)
                    swap = f" Your personal layer suggests \"{plain}\"." if plain else ""
                    flags.append(_flag(
                        "SUGGEST", "P.1", paragraph.location(number), _window(sentence, quote_match),
                        f"\"{hit.group(0)}\" is on your list of words to flag.{swap}",
                        f"Keep \"{hit.group(0)}\" here, or replace it?", "slip"))
            for term, preferred in terms:
                hit = re.search(rf"\b{re.escape(term)}\b", own, re.IGNORECASE)
                if hit:
                    quote_match = re.search(re.escape(hit.group(0)), sentence)
                    use = f"; this project uses \"{preferred}\"" if preferred else ""
                    flags.append(_flag(
                        "ISSUE", "P.2", paragraph.location(number), _window(sentence, quote_match),
                        f"\"{hit.group(0)}\" is a term this project avoids{use}.",
                        f"Replace \"{hit.group(0)}\"" + (f" with \"{preferred}\"" if preferred else "") + ", or is a different meaning intended here?", "slip"))

    note = "" if checked else "\nNo author-year citations with a reference list were found, so rule 5.8 was not checked by the script.\n"
    report = f"Ruleset: {RULESET_ID}\n\n## Script checks\n\n" + ("\n".join(flags) if flags else "No findings.\n") + note + "\n### Pass down\nNone\n"
    return ScriptResult(report=report, flags=len(flags), checked_citations=checked)
