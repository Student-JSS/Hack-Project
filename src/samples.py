"""Synthetic demo data.

Demo Mode must never touch a real person's data, so the sample files here are
generated locally with Pillow (screenshots, a photo-style note) and the standard
``wave`` module (a short audio note). Names, numbers and messages are fake.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Any

from src import db
from src.config import get_logger, get_settings
from src.ingest import ingest_path

LOGGER = get_logger("samples")

DEMO_TITLE = "Demo case - synthetic data (not a real person)"
DEMO_STORY = (
    "This is a synthetic demo story. My husband Rohit hit me on 5 March 2026 after I said I would "
    "not ask my parents for more money. On 12 March 2026 he sent me messages on WhatsApp saying he "
    "will post my photos on Instagram if I leave the house. I am afraid of what he will do next. "
    "I have screenshots of the messages and a photo of the note he left at my parents' house."
)
DEMO_LANGUAGE = "en"

CHAT_LINES = [
    ("Rohit", "Where are you? Come back right now."),
    ("Me", "I am at my parents' house. I do not want to come back today."),
    ("Rohit", "You will regret this."),
    ("Rohit", "I have your photos. Send Rs 50,000 or I will post them on Instagram."),
    ("Me", "Please do not do this."),
    ("Rohit", "Try me. 12 March 2026"),
]


def _font(size: int = 16) -> Any:
    """Best-effort font (Pillow's default font is used as a fallback)."""
    from PIL import ImageFont

    for name in ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _chat_screenshot(path: Path) -> None:
    """Draw a fake messaging screenshot with synthetic text."""
    from PIL import Image, ImageDraw

    width, height = 720, 900
    image = Image.new("RGB", (width, height), (247, 245, 249))
    draw = ImageDraw.Draw(image)
    title_font = _font(22)
    body_font = _font(17)
    small = _font(14)
    draw.rectangle([(0, 0), (width, 74)], fill=(91, 58, 110))
    draw.text((24, 22), "Rohit  ·  WhatsApp (sample)", font=title_font, fill=(255, 255, 255))
    y = 100
    for sender, text in CHAT_LINES:
        mine = sender == "Me"
        bubble = (216, 248, 214) if mine else (255, 255, 255)
        x0 = 300 if mine else 24
        x1 = width - 24 if mine else 470
        lines = _wrap(text, 34)
        box_height = 18 + 26 * len(lines)
        draw.rounded_rectangle([(x0, y), (x1, y + box_height)], radius=14, fill=bubble)
        draw.text((x0 + 12, y + 8), f"{sender} · 21:{40 + y % 18}", font=small, fill=(110, 100, 120))
        for index, line in enumerate(lines):
            draw.text((x0 + 12, y + 28 + index * 22), line, font=body_font, fill=(30, 26, 36))
        y += box_height + 14
        if y > height - 120:
            break
    draw.text((24, height - 60), "SYNTHETIC SAMPLE - not a real conversation", font=small, fill=(150, 140, 160))
    image.save(path, format="PNG")


def _call_log_screenshot(path: Path) -> None:
    """Draw a fake missed-call log screenshot."""
    from PIL import Image, ImageDraw

    width, height = 720, 520
    image = Image.new("RGB", (width, height), (250, 249, 252))
    draw = ImageDraw.Draw(image)
    draw.text((24, 24), "Recents (sample)", font=_font(24), fill=(40, 34, 48))
    rows = [
        ("Unknown +91 90000 00000", "Missed call · 14 times · 11:42 PM"),
        ("Unknown +91 90000 00000", "Missed call · 4 times · 11:05 PM"),
        ("Rohit", "Outgoing call · 8:15 PM"),
        ("Unknown +91 90000 00000", "Missed call · 11 March 2026 · 11:58 PM"),
    ]
    y = 90
    for name, detail in rows:
        draw.rectangle([(0, y - 8), (width, y + 70)], fill=(255, 255, 255))
        draw.text((28, y), name, font=_font(19), fill=(35, 30, 42))
        draw.text((28, y + 30), detail, font=_font(15), fill=(120, 110, 130))
        y += 92
    draw.text((24, height - 40), "SYNTHETIC SAMPLE - fake phone number", font=_font(13), fill=(150, 140, 160))
    image.save(path, format="PNG")


def _note_photo(path: Path) -> None:
    """Draw a photo-style image of a handwritten note."""
    from PIL import Image, ImageDraw

    width, height = 720, 720
    image = Image.new("RGB", (width, height), (231, 224, 206))
    draw = ImageDraw.Draw(image)
    for y in range(120, height - 40, 56):
        draw.line([(48, y), (width - 48, y)], fill=(206, 196, 176), width=2)
    draw.text((70, 60), "14/03/2026", font=_font(22), fill=(70, 56, 44))
    lines = [
        "I am scared to go back.",
        "He said he will take the jewellery",
        "and that I cannot meet my parents.",
        "Neighbours heard him shouting on",
        "12 March 2026.",
    ]
    for index, line in enumerate(lines):
        draw.text((70, 150 + index * 56), line, font=_font(24), fill=(50, 40, 34))
    draw.text((70, height - 60), "SYNTHETIC SAMPLE - handwritten note", font=_font(13), fill=(130, 118, 100))
    image.save(path, format="PNG")


def _voice_note(path: Path) -> None:
    """Generate a short placeholder audio note (a soft tone)."""
    sample_rate = 16000
    duration = 1.6
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for index in range(int(sample_rate * duration)):
            value = int(1200 * math.sin(2 * math.pi * 320 * index / sample_rate))
            frames += struct.pack("<h", value)
        handle.writeframes(bytes(frames))


def _wrap(text: str, width: int) -> list[str]:
    """Wrap text into lines of ``width`` characters."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def ensure_sample_files(directory: Path | str | None = None) -> list[Path]:
    """Create the synthetic sample files if they are missing."""
    target = Path(directory) if directory else get_settings().samples_dir
    target.mkdir(parents=True, exist_ok=True)
    files = {
        "screenshot_whatsapp.png": _chat_screenshot,
        "screenshot_call_log.png": _call_log_screenshot,
        "photo_note.png": _note_photo,
        "voice_note.wav": _voice_note,
    }
    created: list[Path] = []
    for name, builder in files.items():
        path = target / name
        if not path.exists():
            try:
                builder(path)
                LOGGER.info("Generated sample file %s", name)
            except Exception as exc:  # Pillow missing font etc.
                LOGGER.warning("Could not generate %s: %s", name, type(exc).__name__)
        if path.exists():
            created.append(path)
    return created


SAMPLE_TYPES = {
    "screenshot_whatsapp.png": "screenshot",
    "screenshot_call_log.png": "screenshot",
    "photo_note.png": "photo",
    "voice_note.wav": "audio",
}
SAMPLE_NOTES = {
    "screenshot_whatsapp.png": "WhatsApp messages from Rohit, 12 March 2026 (synthetic).",
    "screenshot_call_log.png": "Missed calls from an unknown number at night (synthetic).",
    "photo_note.png": "Note photographed at my parents' house, 14 March 2026 (synthetic).",
    "voice_note.wav": "Voice note placeholder: no speech in the synthetic file.",
}


def create_demo_case(db_path: Path | str | None = None) -> dict[str, Any]:
    """Create a case with the synthetic story and upload the sample files."""
    case = db.create_case(DEMO_TITLE, DEMO_STORY, DEMO_LANGUAGE, is_demo=True, db_path=db_path)
    for path in ensure_sample_files():
        evidence_type = SAMPLE_TYPES.get(path.name, "other")
        try:
            ingest_path(
                case["id"],
                path,
                evidence_type,
                note=SAMPLE_NOTES.get(path.name, ""),
                db_path=db_path,
            )
        except Exception as exc:
            LOGGER.warning("Demo upload failed for %s: %s", path.name, type(exc).__name__)
    LOGGER.info("Demo case created with %d evidence items", len(db.list_evidence(case["id"], db_path=db_path)))
    return case
