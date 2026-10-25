"""Evidence ingestion service: hash -> upload -> OCR -> integrity record.

This is the single path the UI uses to add evidence, so the order of operations
(SHA-256 **before** upload, hash stored with the Cloudinary ids, OCR best-effort)
cannot accidentally be skipped.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from src import db
from src.cloudinary_client import Storage, get_storage
from src.config import get_logger, get_settings
from src.integrity import IntegrityResult, sha256_bytes, verify_integrity
from src.ocr import OcrResult, extract_text

LOGGER = get_logger("ingest")

IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff", "heic"}
TEXT_SUFFIXES = {"txt", "md", "csv", "log", "json"}


def _suffix(filename: str) -> str:
    """Lowercase suffix without the dot."""
    return Path(filename).suffix.lower().lstrip(".")


def ingest_bytes(
    case_id: str,
    data: bytes,
    filename: str,
    evidence_type: str,
    note: str = "",
    storage: Storage | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Store one evidence file and return the saved metadata row.

    The hash is computed on the bytes in memory before they leave the device,
    then Cloudinary receives the file from a temporary copy that is deleted
    immediately afterwards.
    """
    if not data:
        raise ValueError("The selected file is empty.")
    storage = storage or get_storage()
    settings = get_settings()
    suffix = _suffix(filename) or "bin"

    with tempfile.TemporaryDirectory(prefix="saakshya_upload_") as tmp_dir:
        local_path = Path(tmp_dir) / f"evidence.{suffix}"
        local_path.write_bytes(data)
        sha_before = sha256_bytes(data)
        LOGGER.info("Ingesting %s (%d bytes) for case %s", suffix, len(data), case_id)
        uploaded = storage.upload(
            local_path,
            case_id=case_id,
            evidence_type=evidence_type,
            tags=["evidence", evidence_type],
            context={"uploaded_at": db.utc_now()},
        )

    ocr_result = OcrResult(text="", method="none", note="")
    if suffix in IMAGE_SUFFIXES:
        ocr_result = extract_text(
            data,
            public_id=uploaded.get("public_id"),
            filename=filename,
            enabled_addon=settings.cloudinary_ocr_enabled and not settings.use_mock_cloudinary,
        )
    elif suffix in TEXT_SUFFIXES:
        ocr_result = OcrResult(text=data.decode("utf-8", errors="replace")[:20000], method="text_file")

    record = {
        "filename": filename,
        "evidence_type": evidence_type,
        "resource_type": uploaded.get("resource_type", "image"),
        "public_id": uploaded["public_id"],
        "secure_url": uploaded.get("secure_url"),
        "version": uploaded.get("version"),
        "format": uploaded.get("format"),
        "num_bytes": uploaded.get("num_bytes"),
        "etag": uploaded.get("etag"),
        "sha256": sha_before,
        "uploaded_at": db.utc_now(),
        "ocr_text": ocr_result.text or None,
        "ocr_method": ocr_result.method,
        "transcript": note or None,
        "thumbnail_url": uploaded.get("thumbnail_url"),
        "tags": uploaded.get("tags"),
        "context": uploaded.get("context"),
        "integrity_status": "unverified",
    }
    row = db.add_evidence(case_id, record, db_path=db_path)
    LOGGER.info(
        "Evidence %s stored (%s, OCR=%s). Hash recorded; no content logged.",
        row["label"],
        row["resource_type"],
        row["ocr_method"],
    )
    return row


def ingest_path(
    case_id: str,
    path: Path | str,
    evidence_type: str,
    note: str = "",
    storage: Storage | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Read a local file and ingest it (used by Demo Mode samples)."""
    file_path = Path(path)
    return ingest_bytes(
        case_id,
        file_path.read_bytes(),
        file_path.name,
        evidence_type,
        note=note,
        storage=storage,
        db_path=db_path,
    )


def verify_evidence(
    evidence_id: str,
    storage: Storage | None = None,
    db_path: Path | str | None = None,
) -> IntegrityResult:
    """Re-download an asset and compare it with the stored SHA-256."""
    storage = storage or get_storage()
    row = db.get_evidence(evidence_id, db_path=db_path)
    if row is None:
        return IntegrityResult("error", "", "", "Evidence not found.")
    try:
        remote = storage.download_bytes(
            row["public_id"], resource_type=row["resource_type"], fmt=row.get("format")
        )
    except Exception as exc:
        LOGGER.warning("Integrity download failed for %s: %s", row["label"], exc)
        result = IntegrityResult(
            "error", row["sha256"], "", f"Could not download the asset: {exc}"
        )
    else:
        result = verify_integrity(row, remote)
        db.update_evidence(
            evidence_id,
            db_path=db_path,
            integrity_status=result.status,
            integrity_checked_at=db.utc_now(),
        )
        db.log_event(row["case_id"], "integrity_checked", detail=f"{row['label']}:{result.status}", db_path=db_path)
    return result


def delete_evidence(
    evidence_id: str,
    storage: Storage | None = None,
    db_path: Path | str | None = None,
) -> None:
    """Delete one asset from Cloudinary and its metadata row."""
    storage = storage or get_storage()
    row = db.get_evidence(evidence_id, db_path=db_path)
    if row is None:
        return
    try:
        storage.delete_asset(row["public_id"], resource_type=row["resource_type"])
        storage.delete_derived(row["public_id"])
    except Exception as exc:
        LOGGER.warning("Cloudinary delete failed for %s: %s", row["label"], exc)
    db.delete_evidence_row(evidence_id, db_path=db_path)
    db.log_event(row["case_id"], "evidence_deleted", detail=row["label"], db_path=db_path)


def delete_case(case_id: str, storage: Storage | None = None, db_path: Path | str | None = None) -> None:
    """Delete the whole case: remote folder, then every local row."""
    storage = storage or get_storage()
    try:
        storage.delete_case_assets(case_id)
    except Exception as exc:
        LOGGER.warning("Remote case delete failed for %s: %s", case_id, exc)
    db.delete_case(case_id, db_path=db_path)
    LOGGER.info("Case %s deleted locally and remotely", case_id)
