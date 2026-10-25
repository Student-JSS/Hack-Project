"""Local retrieval over the curated legal knowledge base.

The KB is deliberately tiny (12 hand-written entries), so a BM25 keyword index is
both more accurate for legal terms ("zero FIR", "s.66E") and far more predictable
than embeddings - and it needs no API key or model download. No vector store is
therefore required; swapping in FAISS/Chroma later only means implementing
:meth:`LegalKB.search` differently (see ARCHITECTURE.md).

Every retrieved entry carries a KB id, a ``last_reviewed`` date and an explicit
"verify with a lawyer" flag. Every emitted claim cites that id.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from src.config import get_logger, get_settings

LOGGER = get_logger("rag")

CATEGORY_LABELS: dict[str, str] = {
    "domestic_violence": "Domestic violence",
    "workplace_sexual_harassment": "Workplace sexual harassment",
    "stalking": "Stalking / following",
    "cyber_harassment": "Cyber harassment / image abuse",
    "dowry_related": "Dowry-related demands",
    "other": "Other harassment",
}

REQUIRED_FIELDS = (
    "id",
    "title",
    "act",
    "categories",
    "plain_summary",
    "key_points",
    "sources",
    "last_reviewed",
    "verify_with_lawyer",
)

STOPWORDS = frozenset(
    """a an and are as at be been but by can could do does for from had has have how i if in
    into is it its may me my no not of on or our she should so than that the their them then
    there these they this to was we were what when where which who why will with you your
    about after before also any more most other some such only own same very just""".split()
)

_TOKEN_RE = re.compile(r"[a-z0-9\u0900-\u097F]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens without stopwords (Devanagari is preserved)."""
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in STOPWORDS]


@dataclass(frozen=True)
class KBEntry:
    """One curated legal knowledge entry."""

    id: str
    title: str
    act: str
    categories: tuple[str, ...]
    plain_summary: str
    key_points: tuple[str, ...]
    sources: tuple[dict[str, str], ...]
    last_reviewed: str
    verify_with_lawyer: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any], origin: str = "") -> "KBEntry":
        """Validate and build an entry, raising ``ValueError`` on bad data."""
        missing = [field_name for field_name in REQUIRED_FIELDS if field_name not in data]
        if missing:
            raise ValueError(f"KB entry in {origin or '?'} is missing fields: {missing}")
        if not data["verify_with_lawyer"]:
            raise ValueError(f"KB entry {data['id']} must be marked verify_with_lawyer")
        if not str(data["plain_summary"]).strip():
            raise ValueError(f"KB entry {data['id']} has an empty summary")
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            act=str(data["act"]),
            categories=tuple(str(c) for c in data["categories"]),
            plain_summary=str(data["plain_summary"]),
            key_points=tuple(str(point) for point in data["key_points"]),
            sources=tuple(dict(source) for source in data["sources"]),
            last_reviewed=str(data["last_reviewed"]),
            verify_with_lawyer=bool(data["verify_with_lawyer"]),
        )

    def searchable_text(self) -> str:
        """Weighted text used for indexing (title and act appear twice)."""
        points = " ".join(self.key_points)
        categories = " ".join(self.categories)
        return " ".join(
            [
                self.title,
                self.title,
                self.act,
                self.act,
                self.plain_summary,
                points,
                categories,
                self.id,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        """Plain dict for the graph state and the PDF."""
        return {
            "kb_id": self.id,
            "title": self.title,
            "act": self.act,
            "categories": list(self.categories),
            "plain_summary": self.plain_summary,
            "key_points": list(self.key_points),
            "sources": [dict(source) for source in self.sources],
            "last_reviewed": self.last_reviewed,
            "verify_with_lawyer": self.verify_with_lawyer,
        }


@dataclass(frozen=True)
class Hit:
    """A scored retrieval hit."""

    entry: KBEntry
    score: float
    matched_terms: tuple[str, ...] = field(default_factory=tuple)

    @property
    def citation(self) -> str:
        """Standard citation string used everywhere in the app."""
        return format_citation(self.entry)


def format_citation(entry: KBEntry) -> str:
    """Render the citation shown next to every legal claim."""
    return (
        f"[{entry.id}] {entry.act} - {entry.title} "
        f"(last reviewed {entry.last_reviewed}; verify with a lawyer)"
    )


class LegalKB:
    """BM25 index over curated KB entries."""

    def __init__(self, entries: Iterable[KBEntry]) -> None:
        self.entries: tuple[KBEntry, ...] = tuple(entries)
        if not self.entries:
            raise ValueError("The legal knowledge base is empty.")
        self._by_id = {entry.id: entry for entry in self.entries}
        self._docs = [tokenize(entry.searchable_text()) for entry in self.entries]
        self._doc_len = [len(doc) for doc in self._docs]
        self._avg_len = sum(self._doc_len) / len(self._doc_len)
        self._term_freqs = [Counter(doc) for doc in self._docs]
        doc_freq: Counter[str] = Counter()
        for doc in self._docs:
            doc_freq.update(set(doc))
        self._doc_freq = doc_freq
        self._total_docs = len(self._docs)

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, kb_dir: Path | str | None = None) -> "LegalKB":
        """Load every ``*.json`` file in ``data/legal_kb`` and validate it."""
        directory = Path(kb_dir) if kb_dir else get_settings().kb_dir
        entries: list[KBEntry] = []
        seen: set[str] = set()
        for path in sorted(directory.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            records = raw.get("entries", []) if isinstance(raw, dict) else raw
            if not isinstance(records, list):
                raise ValueError(f"{path.name}: expected a list of entries")
            for record in records:
                entry = KBEntry.from_dict(record, origin=path.name)
                if entry.id in seen:
                    raise ValueError(f"Duplicate KB id {entry.id} in {path.name}")
                seen.add(entry.id)
                entries.append(entry)
        kb = cls(entries)
        LOGGER.info("Loaded %d KB entries from %s", len(entries), directory.name)
        return kb

    # ------------------------------------------------------------------ retrieval
    def by_id(self, kb_id: str) -> KBEntry | None:
        """Look up an entry by id."""
        return self._by_id.get(kb_id)

    def _idf(self, term: str) -> float:
        """BM25 inverse document frequency with a positive floor."""
        df = self._doc_freq.get(term, 0)
        return math.log(1 + (self._total_docs - df + 0.5) / (df + 0.5))

    def search(
        self,
        query: str,
        k: int = 4,
        categories: Iterable[str] | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> list[Hit]:
        """Rank entries for ``query``, optionally boosting category matches."""
        terms = tokenize(query)
        category_set = {str(category) for category in (categories or [])}
        if not terms:
            return self.for_categories(category_set, k=k)
        scores: list[float] = []
        matched: list[tuple[str, ...]] = []
        for index, freqs in enumerate(self._term_freqs):
            length = self._doc_len[index] or 1
            score = 0.0
            hits: list[str] = []
            for term in terms:
                frequency = freqs.get(term, 0)
                if not frequency:
                    continue
                hits.append(term)
                denominator = frequency + k1 * (1 - b + b * length / self._avg_len)
                score += self._idf(term) * frequency * (k1 + 1) / denominator
            if category_set & set(self.entries[index].categories):
                score += 2.5
            scores.append(score)
            matched.append(tuple(dict.fromkeys(hits)))
        ranked = sorted(
            zip(self.entries, scores, matched), key=lambda item: item[1], reverse=True
        )
        return [
            Hit(entry=entry, score=round(score, 4), matched_terms=terms_hit)
            for entry, score, terms_hit in ranked
            if score > 0
        ][:k]

    def for_categories(self, categories: Iterable[str], k: int = 6) -> list[Hit]:
        """Return the entries tagged with any of ``categories``."""
        wanted = {str(category) for category in categories}
        matches = [entry for entry in self.entries if wanted & set(entry.categories)]
        return [Hit(entry=entry, score=1.0, matched_terms=tuple(sorted(wanted))) for entry in matches][:k]


_KB: LegalKB | None = None


def get_kb(force_new: bool = False) -> LegalKB:
    """Return the process-wide KB index."""
    global _KB
    if force_new or _KB is None:
        _KB = LegalKB.load()
    return _KB


def reset_kb() -> None:
    """Drop the cached KB (tests point at a fixture directory)."""
    global _KB
    _KB = None


def citations_block(entries: Iterable[dict[str, Any]] | Iterable[KBEntry]) -> str:
    """Render a bullet list of citations for drafts and the PDF."""
    lines: list[str] = []
    for item in entries:
        if isinstance(item, KBEntry):
            lines.append(f"- {format_citation(item)}")
            continue
        kb_id = item.get("kb_id") or item.get("id") or "KB-?"
        lines.append(
            f"- [{kb_id}] {item.get('act', '')} - {item.get('title', '')} "
            f"(last reviewed {item.get('last_reviewed', '?')}; verify with a lawyer)"
        )
    return "\n".join(dict.fromkeys(lines))
