"""PDF evidence packet built with reportlab.

Sections: cover + disclaimer, timeline, evidence index with integrity hashes,
thumbnail gallery (fetched through short-lived signed Cloudinary URLs), the
approved complaint draft, the cited rights summary, and the court-admissibility
note. Nothing here is generated unless the draft was approved in the UI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.cloudinary_client import Storage, get_storage
from src.config import get_logger, get_settings
from src.integrity import short_hash
from src.rag import citations_block

LOGGER = get_logger("pdf")

BRAND = colors.HexColor("#5B3A6E")
ACCENT = colors.HexColor("#C9A7D8")
INK = colors.HexColor("#1F1B24")
MUTED = colors.HexColor("#6B6273")
WARNING_BG = colors.HexColor("#FBEFE6")
TABLE_GRID = colors.HexColor("#D9D2DE")

DISCLAIMER = (
    "Saakshya provides general information, not legal advice. This packet was generated from "
    "information the user entered and from files she uploaded. Verify every legal point with a "
    "lawyer or the District Legal Services Authority before filing anything."
)
ADMISSIBILITY_NOTE = (
    "Electronic records usually need a certificate when they are produced in court. In India the "
    "Bharatiya Sakshya Adhiniyam, 2023 (which replaced the Indian Evidence Act, 1872) deals with "
    "electronic records and their certificate around section 63 - confirm the current format with a "
    "lawyer. Keep the original device and files; a PDF or screenshot alone can be challenged. The "
    "SHA-256 hashes in this packet show that the files did not change after they were stored."
)
DEVANAGARI_HINT = (
    "A Devanagari font was not found in assets/fonts, so Hindi text below may not render correctly in "
    "this PDF. Add a Noto Sans Devanagari .ttf file to assets/fonts and rebuild the packet, or use the "
    "English version for printing."
)


def _styles() -> dict[str, ParagraphStyle]:
    """Paragraph styles tuned for a calm, readable packet."""
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "SaakshyaBody",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    return {
        "title": ParagraphStyle(
            "SaakshyaTitle",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=BRAND,
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "SaakshyaSubtitle", parent=body, fontSize=11, leading=15, textColor=MUTED
        ),
        "heading": ParagraphStyle(
            "SaakshyaHeading",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=BRAND,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "body": body,
        "small": ParagraphStyle("SaakshyaSmall", parent=body, fontSize=8, leading=11),
        "mono": ParagraphStyle(
            "SaakshyaMono", parent=body, fontName="Courier", fontSize=6.6, leading=8.6
        ),
        "warn": ParagraphStyle(
            "SaakshyaWarn", parent=body, fontSize=8.8, leading=12, textColor=colors.HexColor("#7A3B12")
        ),
    }


def _register_devanagari_font() -> str | None:
    """Register a Devanagari-capable TTF from ``assets/fonts`` if provided."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception:  # pragma: no cover - reportlab always ships these
        return None
    font_dir = get_settings().project_root / "assets" / "fonts"
    for candidate in sorted(font_dir.glob("*.ttf")):
        try:
            pdfmetrics.registerFont(TTFont("SaakshyaDevanagari", str(candidate)))
            return "SaakshyaDevanagari"
        except Exception as exc:
            LOGGER.warning("Could not register font %s: %s", candidate.name, type(exc).__name__)
    return None


def _esc(text: Any) -> str:
    """Escape text for reportlab's mini-HTML and keep line breaks."""
    raw = str(text or "")
    return (
        raw.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _has_devanagari(text: str) -> bool:
    """True when the text contains Devanagari code points."""
    return any("\u0900" <= char <= "\u097F" for char in text or "")


def _thumbnail_flowable(
    item: dict[str, Any], storage: Storage, width: float = 82 * mm, height: float = 62 * mm
) -> Any:
    """Return an Image flowable for the item, or a text placeholder."""
    resource_type = item.get("resource_type", "image")
    if resource_type not in {"image", "video"}:
        return Paragraph(f"{_esc(item.get('label'))}: no preview for this file type", _styles()["small"])
    try:
        data = storage.thumbnail_bytes(str(item.get("public_id")), resource_type=resource_type)
    except Exception as exc:
        LOGGER.warning("Thumbnail fetch failed for %s: %s", item.get("label"), type(exc).__name__)
        data = None
    if not data:
        return Paragraph(f"{_esc(item.get('label'))}: preview unavailable offline", _styles()["small"])
    try:
        return Image(BytesIO(data), width=width, height=height, kind="proportional")
    except Exception as exc:
        LOGGER.warning("Could not embed thumbnail for %s: %s", item.get("label"), type(exc).__name__)
        return Paragraph(f"{_esc(item.get('label'))}: preview could not be embedded", _styles()["small"])


def _footer(canvas: Any, doc: Any) -> None:
    """Page footer with the disclaimer and page number."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 12 * mm, "Saakshya - general information, not legal advice.")
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 16 * mm, A4[0] - 18 * mm, 16 * mm)
    canvas.restoreState()


def build_evidence_packet(
    case: dict[str, Any],
    evidence: Iterable[dict[str, Any]],
    timeline: Iterable[dict[str, Any]] | None = None,
    draft_text: str = "",
    legal_matches: Iterable[dict[str, Any]] | None = None,
    action_plan: Iterable[dict[str, Any]] | None = None,
    output_path: Path | str | None = None,
    storage: Storage | None = None,
    include_thumbnails: bool = True,
) -> Path:
    """Build the packet and return its path.

    ``draft_text`` must be the approved draft; callers check ``human_approved``
    before calling this function.
    """
    storage = storage or get_storage()
    settings = get_settings()
    evidence_list = list(evidence or [])
    timeline_list = list(timeline or [])
    matches = list(legal_matches or [])
    plan = list(action_plan or [])
    styles = _styles()

    if output_path is None:
        safe_id = str(case.get("id", "case")).replace("/", "_")
        output_path = settings.exports_dir / f"saakshya_packet_{safe_id}.pdf"
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=f"Saakshya evidence packet - {case.get('title', '')}",
        author="Saakshya",
        subject="Evidence packet (not legal advice)",
    )

    story: list[Any] = []
    devanagari_font = _register_devanagari_font()
    full_text = " ".join(
        [str(case.get("title", "")), str(case.get("user_story", "")), draft_text]
        + [str(item.get("ocr_text") or "") for item in evidence_list]
    )

    # ---------------------------------------------------------------- cover
    story.append(Paragraph("Saakshya evidence packet", styles["title"]))
    story.append(Paragraph("A private record of what happened, prepared by the survivor.", styles["subtitle"]))
    story.append(Spacer(1, 6 * mm))
    meta_rows = [
        ["Case id", str(case.get("id", ""))],
        ["Case title", str(case.get("title", ""))],
        ["Generated", datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")],
        ["Language", "Hindi" if case.get("language") == "hi" else "English"],
        ["Evidence items", str(len(evidence_list))],
        ["Integrity", ", ".join(
            f"{sum(1 for item in evidence_list if item.get('integrity_status') == status)} {status}"
            for status in ("match", "mismatch", "unverified")
            if any(item.get("integrity_status") == status for item in evidence_list)
        ) or "not checked yet"],
        ["Approval", "Approved by " + (case.get("approver") or "the survivor") if case.get("human_approved") else "Not approved"],
    ]
    meta_table = Table(meta_rows, colWidths=[38 * mm, 132 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, TABLE_GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 6 * mm))

    disclaimer_box = Table([[Paragraph(_esc(DISCLAIMER), styles["warn"])]], colWidths=[170 * mm])
    disclaimer_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WARNING_BG),
                ("BOX", (0, 0), (-1, -1), 0.4, ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(disclaimer_box)
    if _has_devanagari(full_text) and devanagari_font is None:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(_esc(DEVANAGARI_HINT), styles["warn"]))
    story.append(Spacer(1, 5 * mm))
    if timeline_list:
        story.append(Paragraph("What this packet contains", styles["heading"]))
        story.append(
            Paragraph(
                f"{len(timeline_list)} timeline entries, {len(evidence_list)} evidence items with "
                f"SHA-256 hashes, {len(plan)} action steps, the approved complaint draft and "
                f"{len(matches)} cited rights references.",
                styles["body"],
            )
        )
    story.append(PageBreak())

    # ------------------------------------------------------------- timeline
    story.append(Paragraph("1. Timeline", styles["heading"]))
    if timeline_list:
        rows = [["Date", "What happened", "Source"]]
        for event in timeline_list:
            rows.append(
                [
                    Paragraph(_esc(event.get("date_display") or event.get("date") or "date not stated"), styles["small"]),
                    Paragraph(_esc(event.get("title") or event.get("detail") or ""), styles["small"]),
                    Paragraph(_esc(event.get("evidence_label") or event.get("source") or "story"), styles["small"]),
                ]
            )
        table = Table(rows, colWidths=[30 * mm, 112 * mm, 28 * mm], repeatRows=1)
        table.setStyle(_grid_style())
        story.append(table)
    else:
        story.append(Paragraph("No dated events were found. Add dates to the story for a stronger record.", styles["body"]))
    gaps = case.get("timeline_gaps") or []
    if gaps:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Gaps flagged by the pipeline", styles["body"]))
        for gap in gaps:
            story.append(Paragraph(f"- {_esc(gap)}", styles["small"]))

    # --------------------------------------------------------- evidence index
    story.append(Paragraph("2. Evidence index", styles["heading"]))
    story.append(
        Paragraph(
            "Each file below was hashed with SHA-256 before it was uploaded. If a file is downloaded "
            "later and the hash differs, the file changed after it was stored.",
            styles["body"],
        )
    )
    if evidence_list:
        rows = [["ID", "Type", "Uploaded", "Integrity", "SHA-256"]]
        for item in evidence_list:
            rows.append(
                [
                    Paragraph(_esc(item.get("label")), styles["small"]),
                    Paragraph(_esc(item.get("evidence_type")), styles["small"]),
                    Paragraph(_esc(str(item.get("uploaded_at", ""))[:16].replace("T", " ")), styles["small"]),
                    Paragraph(_esc(item.get("integrity_status", "unverified")), styles["small"]),
                    Paragraph(_esc(short_hash(str(item.get("sha256", "")), 24)), styles["mono"]),
                ]
            )
        table = Table(rows, colWidths=[14 * mm, 32 * mm, 34 * mm, 24 * mm, 66 * mm], repeatRows=1)
        table.setStyle(_grid_style())
        story.append(table)

        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Full hashes and extracted text", styles["body"]))
        for item in evidence_list:
            excerpt = str(item.get("ocr_text") or item.get("transcript") or "").strip()
            block = [
                Paragraph(
                    f"<b>{_esc(item.get('label'))}</b> {_esc(item.get('filename'))} "
                    f"({_esc(item.get('evidence_type'))})",
                    styles["small"],
                ),
                Paragraph(
                    f"SHA-256: {_esc(item.get('sha256'))}<br/>"
                    f"Cloudinary public_id: {_esc(item.get('public_id'))} | version: {_esc(item.get('version'))}",
                    styles["mono"],
                ),
            ]
            if excerpt:
                block.append(Paragraph(f"Extracted text: {_esc(excerpt[:600])}", styles["small"]))
            story.append(KeepTogether(block))
            story.append(Spacer(1, 2.5 * mm))

        if include_thumbnails:
            story.append(Paragraph("3. Evidence gallery (signed, expiring URLs)", styles["heading"]))
            cells: list[Any] = []
            for item in evidence_list:
                cells.append(
                    [
                        _thumbnail_flowable(item, storage, width=80 * mm, height=58 * mm),
                        Paragraph(
                            f"{_esc(item.get('label'))} - {_esc(item.get('evidence_type'))}", styles["small"]
                        ),
                    ]
                )
            for start in range(0, len(cells), 2):
                pair = cells[start : start + 2]
                while len(pair) < 2:
                    pair.append("")
                gallery = Table([pair], colWidths=[85 * mm, 85 * mm])
                gallery.setStyle(
                    TableStyle(
                        [
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("BOX", (0, 0), (-1, -1), 0.3, TABLE_GRID),
                            ("INNERGRID", (0, 0), (-1, -1), 0.3, TABLE_GRID),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(gallery)
                story.append(Spacer(1, 2 * mm))
    else:
        story.append(Paragraph("No evidence was uploaded for this case.", styles["body"]))

    # --------------------------------------------------------- action plan
    if plan:
        story.append(Paragraph("4. Action plan", styles["heading"]))
        for step in sorted(plan, key=lambda entry: entry.get("priority", 99)):
            story.append(
                Paragraph(
                    f"<b>{_esc(step.get('title'))}</b><br/>{_esc(step.get('detail'))}"
                    + (f"<br/>Contact: {_esc(step.get('contact'))}" if step.get("contact") else ""),
                    styles["body"],
                )
            )
            story.append(Spacer(1, 1.5 * mm))

    # ------------------------------------------------------ complaint draft
    story.append(Paragraph("5. Approved complaint draft", styles["heading"]))
    if draft_text.strip():
        for block in draft_text.split("\n\n"):
            story.append(Paragraph(_esc(block), styles["body"]))
    else:
        story.append(Paragraph("No approved draft is attached. Approve the draft in the app first.", styles["body"]))

    # ------------------------------------------------------------- rights
    if matches:
        story.append(Paragraph("6. Rights summary and citations", styles["heading"]))
        story.append(
            Paragraph(
                "These are plain-language summaries from Saakshya's curated knowledge base, not a legal "
                "opinion. Each one is marked with its source id and the date it was last reviewed.",
                styles["body"],
            )
        )
        for match in matches:
            story.append(
                Paragraph(
                    f"<b>[{_esc(match.get('kb_id'))}] {_esc(match.get('title'))}</b><br/>"
                    f"{_esc(match.get('plain_summary'))}<br/>"
                    f"<i>{_esc(match.get('act'))}</i> - last reviewed {_esc(match.get('last_reviewed'))}; "
                    f"verify with a lawyer.",
                    styles["body"],
                )
            )
            story.append(Spacer(1, 2 * mm))
        citation_text = citations_block(matches)
        if citation_text:
            story.append(Paragraph("Citation list", styles["body"]))
            for line in citation_text.splitlines():
                story.append(Paragraph(_esc(line), styles["small"]))

    # ------------------------------------------------------- admissibility
    story.append(Paragraph("7. Using this packet in court or with the police", styles["heading"]))
    story.append(Paragraph(_esc(ADMISSIBILITY_NOTE), styles["body"]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(_esc(DISCLAIMER), styles["small"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    LOGGER.info("PDF packet written for case %s (%d bytes)", case.get("id"), output.stat().st_size)
    return output


def _grid_style() -> TableStyle:
    """Shared table styling."""
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4EEF8")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.3, TABLE_GRID),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )
