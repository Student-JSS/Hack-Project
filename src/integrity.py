"""Evidence integrity: SHA-256 hashing computed *before* upload.

The hash is stored in SQLite next to the Cloudinary ``public_id``/``version`` and
can be recomputed later from the downloaded asset. A mismatch means the bytes
changed after upload (or the file is not the one she uploaded).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Literal

CHUNK_SIZE = 1 << 20  # 1 MiB

IntegrityStatus = Literal["match", "mismatch", "error", "unverified"]


@dataclass(frozen=True)
class IntegrityResult:
    """Outcome of verifying one evidence file."""

    status: IntegrityStatus
    expected_sha256: str
    actual_sha256: str
    detail: str = ""
    etag_matches: bool | None = None

    @property
    def ok(self) -> bool:
        """True only when the stored hash equals the freshly computed hash."""
        return self.status == "match"


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_stream(stream: BinaryIO) -> str:
    """Hash an open binary stream without loading it fully in memory."""
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path | str) -> str:
    """Return the hex SHA-256 of a file's bytes."""
    with Path(path).open("rb") as handle:
        return sha256_stream(handle)


def build_integrity_record(path: Path | str) -> dict[str, Any]:
    """Compute the pre-upload integrity fields for a local file."""
    file_path = Path(path)
    return {
        "filename": file_path.name,
        "sha256": sha256_file(file_path),
        "num_bytes": file_path.stat().st_size,
        "hashed_at": None,  # filled by the caller with a UTC timestamp
    }


def verify_integrity(stored: dict[str, Any], remote_bytes: bytes) -> IntegrityResult:
    """Compare freshly downloaded bytes with the stored integrity record.

    ``stored`` is the evidence row (or the subset with ``sha256`` and ``etag``).
    """
    expected = str(stored.get("sha256") or "")
    if not expected:
        return IntegrityResult("error", "", "", "No stored hash for this evidence item.")
    actual = sha256_bytes(remote_bytes)
    detail = ""
    if expected == actual:
        status: IntegrityStatus = "match"
    else:
        status = "mismatch"
        detail = "The stored hash and the downloaded file differ."

    etag = str(stored.get("etag") or "").strip()
    etag_matches: bool | None = None
    if etag:
        # Cloudinary's etag is the MD5 of the delivered bytes, not SHA-256.
        etag_matches = hmac.compare_digest(etag.lower(), hashlib.md5(remote_bytes).hexdigest())
    return IntegrityResult(
        status=status,
        expected_sha256=expected,
        actual_sha256=actual,
        detail=detail,
        etag_matches=etag_matches,
    )


def short_hash(value: str, keep: int = 12) -> str:
    """Shorten a hash for display while keeping it comparable."""
    return f"{value[:keep]}…" if len(value) > keep else value


def hash_matches(a: str, b: str) -> bool:
    """Constant-time comparison for two hex digests."""
    return hmac.compare_digest(a.strip().lower(), b.strip().lower())
