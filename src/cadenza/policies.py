"""Store manual: parse the policy PDF into numbered sections grouped by topic."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path

from pypdf import PdfReader

OFFICIAL_WHATSAPP = "(67) 3341-4444"
OFFICIAL_EMAIL = "contato@emporiodamusica.com.br"
# The manual lists conflicting contacts; the official ones win (docs/data-issues.md).
CONTACT_FIXES = {
    "contato@empóriodamusica.com.br": OFFICIAL_EMAIL,
    "(67) 3321-4500": OFFICIAL_WHATSAPP,
}

# Topic -> top-level manual sections. 7 and 10 are staff guidelines, used in the system prompt.
TOPIC_SECTIONS = {
    "sobre_a_loja": ("1",),
    "horario": ("2",),
    "pagamento": ("3",),
    "trocas_devolucoes": ("4",),
    "frete_entregas": ("5",),
    "promocoes": ("6",),
    "garantia": ("8",),
    "privacidade": ("9",),
}

# Manual section 2, by weekday (Monday is 0). Sunday is closed; holidays are not detected yet.
OPENING_HOURS = {0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: (9, 13)}

# How the code resolves conflicts inside a topic, sent along with the manual text.
TOPIC_NOTES = {
    "sobre_a_loja": "The '300+ instruments' figure is marketing copy; availability comes only from the catalog tools.",
    "pagamento": "Section 3.1 is more specific than the summary table and prevails: up to 3x the "
    "minimum installment is R$ 50, 4x-6x R$ 80, 7x-12x R$ 100. Product tools already compute "
    "the maximum installments per product.",
}

# Titles start at column 0; the numbered steps in 7.2 are indented, so they never match.
TITLE_RE = re.compile(r"^(\d+(?:\.\d+)?)\.?\s+(\S.*)$")
PAGE_NOISE_RE = re.compile(
    r"^(Empório da Música Manual de|Página \d+$|Empório da Música — Sua música|Última atualização)"
)


@dataclass
class Section:
    """One numbered manual section or subsection."""

    number: str
    title: str
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join([f"{self.number} {self.title}", *self.lines])


def clean_line(line: str) -> str:
    """Collapse layout spacing and replace conflicting contacts with the official ones."""
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", line)).strip()
    for wrong, official in CONTACT_FIXES.items():
        text = text.replace(wrong, official)
    return text


def read_manual_lines(pdf_path: Path) -> list[str]:
    """Raw layout lines of every page except the cover, without headers and footers."""
    lines = []
    for page in PdfReader(pdf_path).pages[1:]:
        for raw in page.extract_text(extraction_mode="layout").splitlines():
            if raw.strip() and not PAGE_NOISE_RE.match(raw.strip()):
                lines.append(unicodedata.normalize("NFC", raw.rstrip()))
    return lines


def parse_sections(lines: list[str]) -> list[Section]:
    """Split raw lines into sections at column-0 numbered titles."""
    sections: list[Section] = []
    for raw in lines:
        match = TITLE_RE.match(raw)
        if match:
            sections.append(Section(match[1], clean_line(match[2])))
        elif sections:
            sections[-1].lines.append(clean_line(raw))
    return sections


def load_manual(pdf_path: Path) -> list[Section]:
    """Parse the store manual PDF into sections."""
    return parse_sections(read_manual_lines(pdf_path))


def topic_text(sections: list[Section], topic: str) -> str:
    """Text of every section and subsection that belongs to a topic."""
    roots = TOPIC_SECTIONS[topic]
    chosen = [s for s in sections if s.number.split(".")[0] in roots]
    return "\n\n".join(s.text for s in chosen)


def next_opening(now: datetime) -> datetime:
    """When the team is next available: `now` itself while the store is open."""
    for offset in range(8):
        day = now.date() + timedelta(days=offset)
        hours = OPENING_HOURS.get(day.weekday())
        if hours is None:
            continue
        opens = datetime.combine(day, time(hours[0]), tzinfo=now.tzinfo)
        closes = datetime.combine(day, time(hours[1]), tzinfo=now.tzinfo)
        if now < closes:
            return max(opens, now)
    raise AssertionError("OPENING_HOURS must open at least once a week")
