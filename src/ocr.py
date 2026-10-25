"""Text extraction for screenshots and photos, with a visible fallback chain.

Order of attempts:

1. Cloudinary's OCR add-on (``ocr="adv_ocr"``) on the already-uploaded asset.
2. The multimodal LLM (Gemini/OpenAI/Anthropic) if the add-on is unavailable.
3. Nothing - the item is still usable, it just has no extracted text.

Every attempt is wrapped in ``try/except`` and the method is reported back so the
UI can show a badge ("Cloudinary OCR", "LLM vision", "none").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config import get_logger

LOGGER = get_logger("ocr")

OCR_PROMPT = (
    "Transcribe every readable character of text in this screenshot, in the "
    "original language and layout order. Then, on a new line starting with "
    "'SUMMARY:', describe in one sentence what the screenshot shows, including "
    "visible sender names and dates. Do not invent text that is not visible. "
    "If you cannot read it, say 'UNREADABLE'."
)


@dataclass(frozen=True)
class OcrResult:
    """Extracted text plus which engine produced it."""

    text: str
    method: str
    note: str = ""

    @property
    def ok(self) -> bool:
        """True when any text was extracted."""
        return bool(self.text.strip())


def _parse_adv_ocr(result: dict[str, Any]) -> str:
    """Pull text out of the many shapes Cloudinary's adv_ocr response can take."""
    info = result.get("info") or {}
    ocr = info.get("ocr") or {}
    adv = ocr.get("adv_ocr") or {}
    data = adv.get("data") or []
    if isinstance(data, dict):
        data = [data]
    chunks: list[str] = []
    for page in data:
        if not isinstance(page, dict):
            continue
        annotations = page.get("textAnnotations") or []
        for annotation in annotations:
            if isinstance(annotation, dict) and annotation.get("description"):
                chunks.append(str(annotation["description"]))
        if not chunks and page.get("fullTextAnnotation"):
            full = page["fullTextAnnotation"]
            if isinstance(full, dict) and full.get("text"):
                chunks.append(str(full["text"]))
    text = "\n".join(chunk.strip() for chunk in chunks if chunk.strip())
    if not text and isinstance(ocr.get("text"), str):
        text = ocr["text"]
    return text.strip()


def try_cloudinary_ocr(public_id: str | None) -> OcrResult:
    """Ask Cloudinary's OCR add-on to read an authenticated image."""
    if not public_id:
        return OcrResult("", "none", "No Cloudinary public id yet.")
    try:
        import cloudinary.uploader

        result = cloudinary.uploader.explicit(
            public_id,
            type="authenticated",
            resource_type="image",
            ocr="adv_ocr",
        )
    except Exception as exc:
        LOGGER.warning(
            "OCR add-on unavailable for %s (%s). Falling back to the vision LLM.",
            public_id,
            exc,
        )
        return OcrResult("", "none", f"Cloudinary OCR failed: {exc}")
    text = _parse_adv_ocr(result if isinstance(result, dict) else {})
    if not text:
        LOGGER.warning("OCR add-on returned no text for %s. Falling back to the vision LLM.", public_id)
        return OcrResult("", "none", "Cloudinary OCR returned no text.")
    return OcrResult(text, "cloudinary_ocr")


def try_llm_vision(image_bytes: bytes, mime: str = "image/png") -> OcrResult:
    """Fallback: send the image to the multimodal LLM."""
    from src.llm import get_llm

    llm = get_llm()
    if llm is None:
        return OcrResult("", "none", "No vision-capable LLM configured.")
    try:
        from langchain_core.messages import HumanMessage

        from src.cloudinary_client import image_bytes_to_data_uri

        message = HumanMessage(
            content=[
                {"type": "text", "text": OCR_PROMPT},
                {"type": "image_url", "image_url": {"url": image_bytes_to_data_uri(image_bytes, mime)}},
            ]
        )
        response = llm.invoke([message])
        text = getattr(response, "content", "") or ""
        if isinstance(text, list):  # some providers return content blocks
            text = "\n".join(
                block.get("text", "") if isinstance(block, dict) else str(block) for block in text
            )
        text = str(text).strip()
        if not text:
            return OcrResult("", "none", "The vision model returned nothing.")
        return OcrResult(text, "llm_vision")
    except Exception as exc:
        LOGGER.warning("Vision LLM fallback failed: %s", exc)
        return OcrResult("", "none", f"Vision LLM failed: {exc}")


def extract_text(
    image_bytes: bytes,
    public_id: str | None = None,
    filename: str = "",
    enabled_addon: bool = True,
) -> OcrResult:
    """Run the OCR chain and never raise: the caller gets a method badge."""
    if enabled_addon:
        result = try_cloudinary_ocr(public_id)
        if result.ok:
            LOGGER.info("OCR for %s used Cloudinary adv_ocr", filename or public_id)
            return result
    else:
        LOGGER.info("OCR add-on disabled by config; using the vision LLM for %s", filename or "image")
    vision = try_llm_vision(image_bytes)
    if vision.ok:
        LOGGER.info("OCR for %s used the vision LLM", filename or "image")
        return vision
    note = vision.note or "No OCR method was available."
    return OcrResult("", "none", note)


def method_label(method: str) -> str:
    """Human label for the OCR method badge."""
    return {
        "cloudinary_ocr": "Cloudinary OCR",
        "llm_vision": "LLM vision (fallback)",
        "text_file": "Plain text file",
    }.get(method, "No text extracted")
