"""Curated KB: schema guarantees, retrieval quality and citation text."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.graph.state import CATEGORIES
from src.rag import (
    CATEGORY_LABELS,
    KBEntry,
    LegalKB,
    citations_block,
    format_citation,
    get_kb,
    tokenize,
)


def test_kb_loads_with_required_metadata() -> None:
    kb = get_kb()
    assert len(kb.entries) >= 10
    ids = [entry.id for entry in kb.entries]
    assert len(ids) == len(set(ids))
    for entry in kb.entries:
        assert entry.verify_with_lawyer is True
        assert entry.last_reviewed
        date.fromisoformat(entry.last_reviewed)  # must be a real ISO date
        assert entry.plain_summary.strip()
        assert entry.key_points
        assert entry.sources
        assert entry.id.startswith("KB-")


def test_every_supported_category_has_an_entry() -> None:
    kb = get_kb()
    covered = {category for entry in kb.entries for category in entry.categories}
    for category in CATEGORIES:
        assert category in covered, f"no KB entry covers {category}"
        assert category in CATEGORY_LABELS


def test_search_finds_stalking_and_citations() -> None:
    kb = get_kb()
    hits = kb.search("my ex keeps following me and calls from unknown numbers", k=4)
    assert hits
    assert any("stalking" in hit.entry.categories for hit in hits)
    top = hits[0]
    assert top.score > 0
    assert top.matched_terms
    citation = format_citation(top.entry)
    assert f"[{top.entry.id}]" in citation
    assert "verify with a lawyer" in citation
    assert top.entry.last_reviewed in citation


def test_search_prefers_dowry_entry_for_dowry_query() -> None:
    kb = get_kb()
    hits = kb.search("dahej dowry demand from in-laws", k=3)
    assert hits
    assert "dowry_related" in hits[0].entry.categories


def test_category_boost_keeps_results_relevant() -> None:
    kb = get_kb()
    hits = kb.search("complaint process", k=3, categories=["workplace_sexual_harassment"])
    assert hits
    assert any("workplace_sexual_harassment" in hit.entry.categories for hit in hits[:3])


def test_empty_query_falls_back_to_categories() -> None:
    kb = get_kb()
    hits = kb.search("", k=3, categories=["cyber_harassment"])
    assert hits
    assert all("cyber_harassment" in hit.entry.categories for hit in hits)


def test_citations_block_lists_every_id() -> None:
    kb = get_kb()
    matches = [entry.to_dict() for entry in kb.entries[:3]]
    block = citations_block(matches)
    for match in matches:
        assert match["kb_id"] in block
    assert block.count("- [KB-") == 3


def test_invalid_entry_is_rejected() -> None:
    payload = {
        "id": "KB-99",
        "title": "Broken",
        "act": "Test Act",
        "categories": ["other"],
        "plain_summary": "x",
        "key_points": ["y"],
        "sources": [{"label": "z", "url": "https://example.com"}],
        "last_reviewed": "2026-01-01",
        "verify_with_lawyer": False,
    }
    with pytest.raises(ValueError):
        KBEntry.from_dict(payload, origin="test.json")
    payload["verify_with_lawyer"] = True
    payload["plain_summary"] = " "
    with pytest.raises(ValueError):
        KBEntry.from_dict(payload, origin="test.json")


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    entry = {
        "id": "KB-77",
        "title": "Duplicate",
        "act": "Test Act",
        "categories": ["other"],
        "plain_summary": "Summary",
        "key_points": ["Point"],
        "sources": [{"label": "Source", "url": "https://example.com"}],
        "last_reviewed": "2026-01-01",
        "verify_with_lawyer": True,
    }
    (tmp_path / "a.json").write_text(json.dumps({"entries": [entry]}), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"entries": [entry]}), encoding="utf-8")
    with pytest.raises(ValueError):
        LegalKB.load(tmp_path)


def test_tokenizer_drops_stopwords() -> None:
    tokens = tokenize("The woman should file an FIR with the police")
    assert "the" not in tokens
    assert "fir" in tokens
    assert "police" in tokens
