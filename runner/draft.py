"""Parse a Markdown draft into sections, headings, paragraphs, and sentences."""

import re
from dataclasses import dataclass, field

_ABBREVIATIONS = (
    "e.g.", "i.e.", "et al.", "cf.", "vs.", "etc.", "p.", "pp.", "no.", "vol.",
    "dr.", "prof.", "fig.", "eq.", "ch.", "sec.", "approx.", "u.s.", "u.k.",
)
_REFERENCE_HEADINGS = re.compile(r"^(references|reference list|bibliography|works cited|literature cited)$", re.IGNORECASE)


def normalize(text: str) -> str:
    """Lowercase, drop punctuation and Markdown emphasis, collapse whitespace."""
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[*_`]", "", text)
    text = re.sub(r"[^\w\s']", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences, keeping common abbreviations and initials intact."""
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    pieces = re.split(r"(?<=[.!?])[\"')\]]*\s+(?=[A-Z\"'(\[“])", text)
    sentences: list[str] = []
    for piece in pieces:
        if sentences:
            previous = sentences[-1]
            last_word = previous.rsplit(" ", 1)[-1].lower()
            if last_word in _ABBREVIATIONS or re.fullmatch(r"[a-z]\.", last_word):
                sentences[-1] = previous + " " + piece
                continue
        sentences.append(piece)
    return sentences


@dataclass
class Paragraph:
    index: int  # position in the whole draft, from 1
    headings: list[str]
    text: str
    sentences: list[str] = field(default_factory=list)
    number: int = 1  # position under its lowest heading, from 1, as a reader would count it
    section: str = "(front matter)"  # the top-level section it belongs to

    @property
    def heading(self) -> str:
        return self.headings[-1] if self.headings else "(no heading)"

    @property
    def first_sentence(self) -> str:
        return self.sentences[0] if self.sentences else self.text

    @property
    def is_proposition(self) -> bool:
        return bool(re.match(r"^\W*(proposition|hypothesis)\s+\d+[a-z]?\b", self.text, re.IGNORECASE))

    def location(self, sentence: int | None = None) -> str:
        where = f"{self.heading}, paragraph {self.number}"
        return f"{where}, sentence {sentence}" if sentence else where


@dataclass
class Draft:
    text: str
    paragraphs: list[Paragraph]
    headings: list[tuple[int, str]] = field(default_factory=list)  # every heading, in order: (level, title)

    def find_paragraph(self, item: str) -> Paragraph | None:
        """Find the paragraph a pass-down item names by quoting (the opening of) its first sentence.

        Checkers often shorten the quote, so the longest quoted opening of at least 30 characters wins.
        """
        target = normalize(item)
        best, best_length = None, 0
        for paragraph in self.paragraphs:
            key = normalize(paragraph.first_sentence)
            for length in (80, 60, 45, 30):
                prefix = key[:length]
                if len(prefix) >= 30 and prefix in target:
                    if len(prefix) > best_length:
                        best, best_length = paragraph, len(prefix)
                    break
        return best

    def find_sentence(self, quote: str) -> tuple[Paragraph, int] | None:
        """The paragraph and sentence number (from 1) that contain a quoted passage, if exactly one does."""
        key = normalize(quote)
        if not key:
            return None
        hits = [(p, i) for p in self.paragraphs for i, s in enumerate(p.sentences, 1) if key in normalize(s)]
        return hits[0] if len(hits) == 1 else None

    def sections(self, include_references: bool = False) -> dict[str, list[Paragraph]]:
        """Top-level sections in order, each with its paragraphs."""
        out: dict[str, list[Paragraph]] = {}
        for paragraph in self.paragraphs:
            if not include_references and is_references(paragraph.section):
                continue
            out.setdefault(paragraph.section, []).append(paragraph)
        return out

    def references_text(self) -> str:
        return "\n\n".join(p.text for p in self.paragraphs if is_references(p.section))

    def body_words(self) -> int:
        return sum(len(p.text.split()) for p in self.paragraphs if not is_references(p.section))

    def skeleton(self) -> str:
        """The headings and the first sentence of every paragraph, in order: the argument read alone."""
        lines, last = [], None
        for paragraph in self.paragraphs:
            if is_references(paragraph.section):
                continue
            if paragraph.headings and paragraph.headings != last:
                lines.append(f"\n{'#' * min(len(paragraph.headings) + 1, 6)} {paragraph.heading}")
                last = paragraph.headings
            lines.append(f"- {paragraph.first_sentence}")
        return "\n".join(lines).strip()


def is_references(section: str) -> bool:
    return bool(_REFERENCE_HEADINGS.match(section.strip()))


def parse_draft(text: str) -> Draft:
    """Read a Markdown draft: headings set the current heading path; blank lines separate paragraphs.

    A lone top-level heading is the title; the sections are the headings at the highest level used more than once.
    """
    paragraphs: list[Paragraph] = []
    paths: list[list[tuple[int, str]]] = []
    all_headings: list[tuple[int, str]] = []
    headings: list[tuple[int, str]] = []
    block: list[str] = []

    def flush() -> None:
        body = " ".join(line.strip() for line in block).strip()
        block.clear()
        if body:
            path = [h for _, h in headings]
            paths.append(list(headings))
            paragraphs.append(
                Paragraph(
                    index=len(paragraphs) + 1,
                    headings=path,
                    text=body,
                    sentences=split_sentences(body),
                    number=1 + sum(1 for p in paragraphs if p.headings == path),
                )
            )

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            flush()
            level, title = len(match.group(1)), match.group(2).strip()
            headings = [h for h in headings if h[0] < level] + [(level, title)]
            all_headings.append((level, title))
        elif not line.strip():
            flush()
        else:
            block.append(line)
    flush()

    levels = [level for level, _ in all_headings]
    repeated = sorted({level for level in levels if levels.count(level) > 1})
    top = repeated[0] if repeated else (min(levels) if levels else 1)
    for paragraph, path in zip(paragraphs, paths):
        at_top = [title for level, title in path if level == top]
        paragraph.section = at_top[0] if at_top else "(front matter)"
    return Draft(text=text, paragraphs=paragraphs, headings=all_headings)
