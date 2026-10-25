"""PDF packet generation with reportlab (thumbnails from mock Cloudinary)."""

from __future__ import annotations

import base64
import re
import zlib
from pathlib import Path

import pytest
from PIL import Image

from src import db
from src.cloudinary_client import get_storage
from src.ingest import ingest_bytes
from src.pdf_export import build_evidence_packet
from src.rag import get_kb


@pytest.fixture()
def case_with_evidence(tmp_path: Path) -> dict:
    case = db.create_case("PDF test case", "My husband hit me on 5 March 2026.", "en")
    image = tmp_path / "proof.png"
    Image.new("RGB", (240, 180), (245, 240, 250)).save(image)
    ingest_bytes(case["id"], image.read_bytes(), "proof.png", "screenshot", note="synthetic proof")
    return case


def _extract_pdf_text(path: Path) -> str:
    """Decompress PDF content streams so assertions can look for real text."""
    raw = path.read_bytes()
    chunks: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        payload = match.group(1).strip()
        try:
            chunks.append(zlib.decompress(payload))
            continue
        except zlib.error:
            pass
        if payload.endswith(b"~>"):
            payload = payload[:-2]
        try:
            chunks.append(zlib.decompress(base64.a85decode(payload)))
        except Exception:
            continue
    return b"\n".join(chunks).decode("latin-1", errors="replace")


def test_pdf_contains_required_sections(case_with_evidence: dict, tmp_path: Path) -> None:
    case = case_with_evidence
    evidence = db.list_evidence(case["id"])
    matches = [entry.to_dict() for entry in get_kb().entries[:2]]
    evidence[0]["integrity_status"] = "match"
    db.update_evidence(evidence[0]["id"], integrity_status="match")

    output = build_evidence_packet(
        case,
        db.list_evidence(case["id"]),
        [
            {
                "date": "2026-03-05",
                "date_display": "5 March 2026",
                "title": "He hit me",
                "source": "story",
                "evidence_label": None,
            }
        ],
        "Complaint citing [KB-01] and evidence E1.",
        matches,
        [{"priority": 1, "title": "Safety", "detail": "Call 112", "contact": "112"}],
        output_path=tmp_path / "packet.pdf",
        storage=get_storage(),
    )
    assert output.exists()
    raw = output.read_bytes()
    assert raw.startswith(b"%PDF")
    assert raw.count(b"/Type /Page") >= 3
    text = _extract_pdf_text(output)
    assert "SHA-256" in text
    assert case["id"] in text
    assert "not legal advice" in text
    assert "Evidence index" in text


def test_pdf_without_thumbnails_or_evidence(tmp_path: Path) -> None:
    case = db.create_case("Empty case", "Just a story, no evidence.", "en")
    output = build_evidence_packet(
        case,
        [],
        [],
        "",
        [],
        [],
        output_path=tmp_path / "empty.pdf",
        storage=get_storage(),
        include_thumbnails=False,
    )
    assert output.exists()
    assert output.stat().st_size > 2000


def test_pdf_handles_hindi_draft_without_font(case_with_evidence: dict, tmp_path: Path) -> None:
    case = case_with_evidence
    output = build_evidence_packet(
        case,
        db.list_evidence(case["id"]),
        [],
        "महोदय, मेरे पति ने मुझे 5 मार्च 2026 को मारा। [KB-01]",
        [{"kb_id": "KB-01", "title": "Protection orders", "act": "PWDVA 2005", "plain_summary": "Summary",
          "last_reviewed": "2026-09-30"}],
        [],
        output_path=tmp_path / "hindi.pdf",
        storage=get_storage(),
    )
    assert output.exists()
    assert output.stat().st_size > 2000
