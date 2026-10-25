"""Mock Cloudinary behaviour: authenticated uploads, signed expiry, redaction."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote

import pytest
from PIL import Image

from src.cloudinary_client import (
    CloudinaryStorage,
    MockStorage,
    Region,
    StorageError,
    get_storage,
    redaction_transformation,
    verify_mock_url,
)
from src.config import get_settings


@pytest.fixture()
def storage() -> MockStorage:
    backend = get_storage()
    assert isinstance(backend, MockStorage)
    return backend


@pytest.fixture()
def image_path(tmp_path: Path) -> Path:
    path = tmp_path / "chat screenshot.png"
    Image.new("RGB", (320, 240), (250, 245, 252)).save(path)
    return path


def test_upload_returns_cloudinary_shaped_metadata(storage: MockStorage, image_path: Path) -> None:
    result = storage.upload(
        image_path,
        case_id="case_test123",
        evidence_type="screenshot",
        tags=["evidence"],
        context={"uploaded_at": "2026-10-25T10:00:00Z"},
    )
    assert result["public_id"].startswith("saakshya/case_test123/")
    assert result["resource_type"] == "image"
    assert result["num_bytes"] == image_path.stat().st_size
    assert len(result["etag"]) == 32
    assert result["version"] > 0
    assert result["thumbnail_url"].startswith("mock://")
    assert "uploaded_at" in result["context"]


def test_signed_url_is_valid_then_expires(storage: MockStorage, image_path: Path) -> None:
    uploaded = storage.upload(image_path, "case_expiry", "screenshot")
    url = storage.signed_url(uploaded["public_id"], expires_in=3600)
    ok, reason = verify_mock_url(url)
    assert ok and reason == "ok"
    expired_ok, expired_reason = verify_mock_url(url, now=time.time() + 7200)
    assert not expired_ok
    assert expired_reason == "expired"


def test_signature_cannot_be_tampered_with(storage: MockStorage, image_path: Path) -> None:
    uploaded = storage.upload(image_path, "case_sig", "screenshot")
    url = storage.signed_url(uploaded["public_id"], expires_in=3600)
    tampered = url.replace("sig=", "sig=0")[: -1] + "0"
    ok, reason = verify_mock_url(tampered)
    assert not ok
    assert reason == "bad-signature"


def test_short_expiry_is_clamped_to_one_minute(storage: MockStorage, image_path: Path) -> None:
    uploaded = storage.upload(image_path, "case_short", "screenshot")
    url = storage.signed_url(uploaded["public_id"], expires_in=1)
    expires = int(url.split("expires=")[1].split("&")[0])
    assert expires - int(time.time()) >= 55


def test_redacted_url_blurs_faces_and_region(storage: MockStorage, image_path: Path) -> None:
    uploaded = storage.upload(image_path, "case_blur", "screenshot")
    url = storage.redacted_url(
        uploaded["public_id"], expires_in=3600, blur_faces=True, region=Region(12, 34, 120, 60)
    )
    decoded = unquote(url)
    assert "blur_faces" in decoded
    assert "l_saakshya:case_blur" in decoded
    assert "e_blur" in decoded
    assert "x=12" in decoded and "y=34" in decoded
    ok, _ = verify_mock_url(url)
    assert ok


def test_redaction_transformation_shape() -> None:
    transformation = redaction_transformation("saakshya/c1/pic", blur_faces=True, region=Region(1, 2, 3, 4))
    assert transformation[0] == {"effect": "blur_faces:1200"}
    assert transformation[1]["overlay"] == "saakshya:c1:pic"
    assert transformation[-1]["flags"] == "layer_apply"


def test_thumbnail_and_download(storage: MockStorage, image_path: Path) -> None:
    uploaded = storage.upload(image_path, "case_bytes", "screenshot")
    thumb = storage.thumbnail_bytes(uploaded["public_id"])
    assert thumb and thumb[:4] == b"\x89PNG"
    original = storage.download_bytes(uploaded["public_id"], fmt=uploaded["format"])
    assert original == image_path.read_bytes()


def test_redacted_copy_is_separate_and_shareable(storage: MockStorage, image_path: Path) -> None:
    uploaded = storage.upload(image_path, "case_copy", "screenshot")
    copy = storage.create_redacted_copy(
        uploaded["public_id"], blur_faces=True, region=Region(4, 6, 40, 30)
    )
    assert copy["public_id"] != uploaded["public_id"]
    assert copy["public_id"].startswith("saakshya/case_copy/")
    assert copy["derived_from"] == uploaded["public_id"]
    assert "blur_faces" in copy["transformation"]
    assert copy["num_bytes"] > 0
    share_url = storage.signed_url(copy["public_id"], expires_in=3600, fmt=copy["format"])
    ok, reason = verify_mock_url(share_url)
    assert ok and reason == "ok"
    # The copy can be removed on its own without touching the original.
    storage.delete_derived(uploaded["public_id"])
    with pytest.raises(StorageError):
        storage.download_bytes(copy["public_id"], fmt=copy["format"])
    assert storage.download_bytes(uploaded["public_id"], fmt=uploaded["format"])


def test_delete_asset_and_prefix(storage: MockStorage, image_path: Path) -> None:
    uploaded = storage.upload(image_path, "case_delete", "screenshot")
    storage.delete_asset(uploaded["public_id"])
    with pytest.raises(StorageError):
        storage.download_bytes(uploaded["public_id"], fmt=uploaded["format"])

    storage.upload(image_path, "case_delete", "screenshot")
    storage.delete_case_assets("case_delete")
    with pytest.raises(StorageError):
        storage.download_bytes(uploaded["public_id"], fmt=uploaded["format"])


def test_missing_file_raises_storage_error(storage: MockStorage, tmp_path: Path) -> None:
    with pytest.raises(StorageError):
        storage.upload(tmp_path / "nope.png", "case_missing", "screenshot")


def test_missing_cloudinary_config_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh clone with no .env must still start (mock backend, warning)."""
    from src.cloudinary_client import reset_storage, storage_status
    from src.config import reset_settings

    monkeypatch.setenv("USE_MOCK_CLOUDINARY", "false")
    monkeypatch.delenv("CLOUDINARY_URL", raising=False)
    monkeypatch.delenv("CLOUD_NAME", raising=False)
    monkeypatch.delenv("CLOUDINARY_API_KEY", raising=False)
    monkeypatch.delenv("CLOUDINARY_API_SECRET", raising=False)
    reset_settings()
    reset_storage()
    backend = get_storage()
    assert isinstance(backend, MockStorage)
    assert storage_status()["backend"] == "mock"


def test_real_client_signs_expiring_urls_without_network() -> None:
    """The real SDK path is exercised for config + local URL signing only."""
    settings = replace(
        get_settings(),
        use_mock_cloudinary=False,
        cloudinary_url="cloudinary://123456789:abcdefghij@demo-cloud",
    )
    storage = CloudinaryStorage(settings)
    assert storage.cloud_name == "demo-cloud"

    signed = storage.signed_url("saakshya/case_x/evidence", resource_type="image", expires_in=3600)
    assert "expires_at=" in signed
    assert "signature=" in signed
    assert "type=authenticated" in signed

    transformed = storage.redacted_url(
        "saakshya/case_x/evidence", expires_in=3600, blur_faces=True, region=Region(10, 20, 80, 60)
    )
    assert transformed.startswith("https://res.cloudinary.com/demo-cloud/image/authenticated/")
    assert "e_blur_faces" in transformed
    assert "l_saakshya:case_x:evidence" in transformed
