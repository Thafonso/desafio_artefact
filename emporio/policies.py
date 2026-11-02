"""Search index over the store's policy manual.

The manual is 8 pages and 10 numbered sections — small enough to fit whole in
a prompt. It is still exposed to the agent as a *search tool*, for two
reasons:

1. it keeps the system prompt small and stable (good for prompt caching);
2. it makes the "this is a policy question" decision explicit and auditable —
   which is exactly the behaviour the agent has to get right.

Retrieval is BM25 over the sections. With ~25 short passages and questions in
Portuguese full of the manual's own words ("troca", "garantia", "boleto"),
lexical search is enough and avoids pulling in a second provider just to
generate embeddings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from pypdf import PdfReader
from rank_bm25 import BM25Okapi

from .config import POLICIES_FILE
from .data import normalize

PAGE_HEADER = re.compile(r"^Empório da Música\s+Manual de Políticas", re.IGNORECASE)
PAGE_FOOTER = re.compile(r"^Página\s+\d+\s*$", re.IGNORECASE)
HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2})?)\.?\s+(\S.*)$")

STOPWORDS = {
    "a", "ao", "aos", "as", "da", "das", "de", "do", "dos", "e", "em", "na",
    "nas", "no", "nos", "o", "os", "para", "por", "que", "um", "uma", "com",
    "qual", "quais", "como", "posso", "pode", "meu", "minha", "eu", "voces",
    "se", "sobre", "tem", "ter", "ser", "ou",
}


@dataclass(frozen=True)
class Section:
    number: str
    title: str
    body: str

    def __str__(self) -> str:
        heading = f"{self.number} {self.title}".strip()
        return f"[{heading}]\n{self.body}"


def _clean_lines() -> list[str]:
    reader = PdfReader(POLICIES_FILE)
    lines: list[str] = []
    for page in reader.pages:
        for line in page.extract_text(extraction_mode="layout").splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if not line or PAGE_HEADER.match(line) or PAGE_FOOTER.match(line):
                continue
            lines.append(line)
    return lines


def _split_into_sections(lines: list[str]) -> list[Section]:
    sections: list[Section] = []
    number, title = "0", "Identificação da loja"
    body: list[str] = []

    for line in lines:
        match = HEADING.match(line)
        # A line only becomes a heading if it is short: this keeps table rows
        # that start with a number ("3 dias úteis", "90 dias ...") out.
        if match and len(line) < 70 and not line.endswith("."):
            # A section with no body of its own (a "5." followed straight by
            # "5.1") still gets indexed: the title is what answers "what do
            # you cover?".
            if body or number != "0":
                sections.append(Section(number, title, "\n".join(body)))
            number, title = match.group(1), match.group(2)
            body = []
        else:
            body.append(line)

    if body:
        sections.append(Section(number, title, "\n".join(body)))
    return sections


# Prefix stem instead of a real stemmer. The customer writes "me arrependi"
# and the manual says "Direito de Arrependimento"; "devolver" vs "devolução";
# "trocar" vs "trocas". Cutting at 5 characters brings those families together
# without the dependency (and the false positives) of a full stemmer on a
# corpus of ~25 passages.
STEM_LENGTH = 5


def _tokenize(text: str) -> list[str]:
    words = normalize(text).split()
    return [w[:STEM_LENGTH] for w in words if w not in STOPWORDS and len(w) > 1]


@dataclass
class PolicyIndex:
    sections: list[Section]
    _bm25: BM25Okapi

    def search(self, question: str, k: int = 3) -> list[Section]:
        query = _tokenize(question)
        if not query:
            return self.sections[:k]
        scores = self._bm25.get_scores(query)
        ranked = sorted(zip(scores, self.sections), key=lambda pair: pair[0], reverse=True)
        return [section for score, section in ranked[:k] if score > 0]

    def by_number(self, number: str) -> Section | None:
        return next((s for s in self.sections if s.number == number), None)

    def table_of_contents(self) -> list[str]:
        return [f"{s.number} {s.title}".strip() for s in self.sections]


@lru_cache(maxsize=1)
def load_policies() -> PolicyIndex:
    sections = _split_into_sections(_clean_lines())
    # The title goes into the indexed document twice: on a short query like
    # "trocas e devoluções" it is the strongest signal there is.
    corpus = [_tokenize(f"{s.title} {s.title} {s.body}") for s in sections]
    return PolicyIndex(sections=sections, _bm25=BM25Okapi(corpus))
