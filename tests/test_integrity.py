"""SHA-256 hashing and integrity comparison."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.integrity import (
    build_integrity_record,
    hash_matches,
    sha256_bytes,
    sha256_file,
    sha256_stream,
    short_hash,
    verify_integrity,
)


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    path = tmp_path / "note.txt"
    path.write_bytes(b"chat screenshot bytes")
    return path


def test_sha256_matches_hashlib(sample_file: Path) -> None:
    expected = hashlib.sha256(b"chat screenshot bytes").hexdigest()
    assert sha256_bytes(b"chat screenshot bytes") == expected
    assert sha256_file(sample_file) == expected
    with sample_file.open("rb") as handle:
        assert sha256_stream(handle) == expected


def test_build_integrity_record(sample_file: Path) -> None:
    record = build_integrity_record(sample_file)
    assert record["sha256"] == sha256_file(sample_file)
    assert record["num_bytes"] == sample_file.stat().st_size
    assert record["filename"] == "note.txt"


def test_verify_matches_and_etag(sample_file: Path) -> None:
    data = sample_file.read_bytes()
    stored = {"sha256": sha256_bytes(data), "etag": hashlib.md5(data).hexdigest()}
    result = verify_integrity(stored, data)
    assert result.status == "match"
    assert result.ok
    assert result.etag_matches is True


def test_verify_detects_tampering(sample_file: Path) -> None:
    data = sample_file.read_bytes()
    stored = {"sha256": sha256_bytes(data)}
    result = verify_integrity(stored, data + b"tampered")
    assert result.status == "mismatch"
    assert not result.ok
    assert result.actual_sha256 != result.expected_sha256
    assert "differ" in result.detail


def test_verify_without_stored_hash_is_error() -> None:
    result = verify_integrity({}, b"anything")
    assert result.status == "error"
    assert not result.ok


def test_short_hash_and_compare() -> None:
    digest = sha256_bytes(b"abc")
    assert short_hash(digest).endswith("…")
    assert hash_matches(digest.upper(), digest)
    assert not hash_matches(digest, sha256_bytes(b"abd"))
