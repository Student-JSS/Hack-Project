"""Cloudinary storage adapter with a fully local mock.

Two implementations share one interface:

* :class:`CloudinaryStorage` - real assets uploaded with ``type="authenticated"``
  into a per-case folder, with signed/expiring URLs, face-blur transformations
  and deletes.
* :class:`MockStorage` - stores bytes under ``data/mock_cloudinary`` and emits
  HMAC-signed ``mock://`` URLs, so the app and the tests run offline.

Application code only calls :func:`get_storage`.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import urlopen

from src.config import Settings, get_logger, get_settings

LOGGER = get_logger("cloudinary")
FOLDER_ROOT = "saakshya"
THUMB_TRANSFORMATION = [{"width": 480, "height": 360, "crop": "fill", "quality": "auto", "fetch_format": "auto"}]
VIDEO_POSTER_TRANSFORMATION = [{"start_offset": "0", "width": 480, "height": 360, "crop": "fill"}]
HTTP_TIMEOUT = 25
MOCK_SECRET_FALLBACK = "saakshya-mock-signing-secret"


class StorageError(RuntimeError):
    """Raised when a Cloudinary operation fails (wrapped, never raw)."""


@dataclass(frozen=True)
class Region:
    """A rectangle to blur, in pixels relative to the original image."""

    x: int
    y: int
    width: int
    height: int

    def as_tuple(self) -> tuple[int, int, int, int]:
        """Return ``(x, y, width, height)`` with non-negative values."""
        return max(0, self.x), max(0, self.y), max(1, self.width), max(1, self.height)


class Storage(Protocol):
    """Interface every storage backend must provide."""

    def upload(
        self,
        path: Path | str,
        case_id: str,
        evidence_type: str,
        tags: Iterable[str] | None = None,
        context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Upload a file and return Cloudinary metadata."""

    def signed_url(
        self,
        public_id: str,
        resource_type: str = "image",
        expires_in: int = 3600,
        transformation: list[dict[str, Any]] | str | None = None,
        fmt: str | None = None,
        attachment: bool = False,
    ) -> str:
        """Return a signed URL that stops working after ``expires_in`` seconds."""

    def redacted_url(
        self,
        public_id: str,
        expires_in: int = 3600,
        blur_faces: bool = True,
        region: Region | None = None,
        resource_type: str = "image",
    ) -> str:
        """Return a signed URL for a privacy-safe (blurred) delivery."""

    def download_bytes(self, public_id: str, resource_type: str = "image", fmt: str | None = None) -> bytes:
        """Download the stored bytes (used for integrity verification)."""

    def transformed_url(
        self,
        public_id: str,
        transformation: list[dict[str, Any]] | str,
        resource_type: str = "image",
        fmt: str | None = None,
    ) -> str:
        """Return a signed delivery URL with a transformation applied."""

    def create_redacted_copy(
        self,
        public_id: str,
        resource_type: str = "image",
        blur_faces: bool = True,
        region: Region | None = None,
        fmt: str | None = None,
    ) -> dict[str, Any]:
        """Create a separate, shareable redacted asset and return its metadata."""

    def thumbnail_bytes(self, public_id: str, resource_type: str = "image") -> bytes | None:
        """Return preview bytes for galleries and the PDF, or ``None``."""

    def delete_asset(self, public_id: str, resource_type: str = "image") -> None:
        """Delete one asset."""

    def delete_derived(self, public_id: str) -> None:
        """Delete redacted copies derived from ``public_id``."""

    def delete_case_assets(self, case_id: str) -> None:
        """Delete every asset under ``saakshya/<case_id>/``."""


# --------------------------------------------------------------------- helpers
SHORT_KEYS: dict[str, str] = {
    "overlay": "l",
    "effect": "e",
    "crop": "c",
    "width": "w",
    "height": "h",
    "quality": "q",
    "fetch_format": "f",
    "flags": "fl",
    "start_offset": "so",
    "angle": "a",
    "gravity": "g",
    "color": "co",
}


def transformation_to_str(transformation: list[dict[str, Any]] | str | None) -> str:
    """Flatten a transformation list into Cloudinary's short URL form."""
    if not transformation:
        return ""
    if isinstance(transformation, str):
        return transformation
    layers: list[str] = []
    for layer in transformation:
        parts: list[str] = []
        for key, value in layer.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            if value is None:
                continue
            short = SHORT_KEYS.get(key)
            parts.append(f"{short}_{value}" if short else f"{key}={value}")
        if parts:
            layers.append(",".join(parts))
    return "/".join(layers)


def redaction_transformation(
    public_id: str, blur_faces: bool = True, region: Region | None = None
) -> list[dict[str, Any]]:
    """Build the transformation that hides bystanders before sharing.

    ``e_blur_faces`` blurs every detected face. An optional user-drawn region is
    covered by layering the same asset (``l_``), cropping it to that rectangle,
    blurring that crop (``e_blur``) and applying it back at the same offset.
    """
    transformation: list[dict[str, Any]] = []
    if blur_faces:
        transformation.append({"effect": "blur_faces:1200"})
    if region is not None:
        x, y, width, height = region.as_tuple()
        transformation.extend(
            [
                {"overlay": public_id.replace("/", ":")},
                {"crop": "crop", "width": width, "height": height, "x": x, "y": y},
                {"effect": "blur:900"},
                {"flags": "layer_apply", "x": x, "y": y},
            ]
        )
    return transformation


def _mock_secret(settings: Settings) -> str:
    """Secret used to sign mock URLs (never a real credential)."""
    return settings.cloudinary_api_secret or MOCK_SECRET_FALLBACK


def _sign(secret: str, payload: str) -> str:
    """Return a short HMAC signature for mock URLs."""
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def verify_mock_url(url: str, secret: str | None = None, now: float | None = None) -> tuple[bool, str]:
    """Check signature and expiry of a ``mock://`` URL.

    Returns ``(ok, reason)``. Non-mock URLs return ``(True, "not-a-mock-url")``
    because their validity is enforced by Cloudinary itself.
    """
    if not url.startswith("mock://"):
        return True, "not-a-mock-url"
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    public_id = unquote(parsed.path.lstrip("/"))
    expires_raw = query.get("expires", [""])[0]
    transformation = query.get("t", [""])[0]
    kind = query.get("kind", ["view"])[0]
    signature = query.get("sig", [""])[0]
    if not (public_id and expires_raw.isdigit() and signature):
        return False, "malformed-url"
    expected = _sign(secret or _mock_secret(get_settings()), f"{public_id}|{expires_raw}|{transformation}|{kind}")
    if not hmac.compare_digest(expected, signature):
        return False, "bad-signature"
    if int(expires_raw) <= int(now if now is not None else time.time()):
        return False, "expired"
    return True, "ok"


def _parse_cloudinary_url(url: str) -> dict[str, str]:
    """Parse ``cloudinary://key:secret@cloud_name`` into config parts."""
    parsed = urlparse(url)
    return {
        "cloud_name": parsed.hostname or "",
        "api_key": unquote(parsed.username or ""),
        "api_secret": unquote(parsed.password or ""),
    }


# ------------------------------------------------------------------ real cloud
class CloudinaryStorage:
    """Thin, defensive wrapper around the Cloudinary Python SDK."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._configure()

    def _configure(self) -> None:
        """Configure the SDK from CLOUDINARY_URL or the three separate parts."""
        import cloudinary  # imported lazily so the mock works without the SDK

        if self.settings.cloudinary_url:
            parts = _parse_cloudinary_url(self.settings.cloudinary_url)
        else:
            parts = {
                "cloud_name": self.settings.cloud_name,
                "api_key": self.settings.cloudinary_api_key,
                "api_secret": self.settings.cloudinary_api_secret,
            }
        if not all(parts.values()):
            raise StorageError(
                "Cloudinary is not configured. Set CLOUDINARY_URL (or CLOUD_NAME, "
                "CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET) in .env."
            )
        cloudinary.config(secure=True, **parts)
        self.cloud_name = parts["cloud_name"]

    # -- upload ------------------------------------------------------------
    def upload(
        self,
        path: Path | str,
        case_id: str,
        evidence_type: str,
        tags: Iterable[str] | None = None,
        context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Upload one file as a private (authenticated) asset."""
        import cloudinary.uploader

        file_path = Path(path)
        if not file_path.exists():
            raise StorageError(f"File not found: {file_path.name}")
        context_payload = {"case_id": case_id, "evidence_type": evidence_type}
        context_payload.update({k: str(v) for k, v in (context or {}).items()})
        tag_list = ["saakshya", case_id, evidence_type, *(tags or [])]
        try:
            result = cloudinary.uploader.upload(
                str(file_path),
                resource_type="auto",
                type="authenticated",
                folder=f"{FOLDER_ROOT}/{case_id}",
                use_filename=True,
                unique_filename=True,
                overwrite=False,
                tags=",".join(dict.fromkeys(tag_list)),
                context=context_payload,
            )
        except Exception as exc:  # SDK raises many unrelated exception types
            LOGGER.warning("Cloudinary upload failed for case %s: %s", case_id, exc)
            raise StorageError(f"Cloudinary upload failed: {exc}") from exc
        public_id = result.get("public_id", "")
        resource_type = result.get("resource_type", "image")
        return {
            "public_id": public_id,
            "secure_url": result.get("secure_url", ""),
            "version": int(result.get("version") or 0),
            "num_bytes": int(result.get("bytes") or 0),
            "etag": result.get("etag"),
            "resource_type": resource_type,
            "format": result.get("format"),
            "thumbnail_url": self.transformed_url(
                public_id,
                VIDEO_POSTER_TRANSFORMATION if resource_type == "video" else THUMB_TRANSFORMATION,
                resource_type=resource_type,
                fmt="jpg" if resource_type == "video" else None,
            ),
            "poster_url": (
                self.transformed_url(
                    public_id, VIDEO_POSTER_TRANSFORMATION, resource_type="video", fmt="jpg"
                )
                if resource_type == "video"
                else None
            ),
            "folder": result.get("folder", f"{FOLDER_ROOT}/{case_id}"),
        }

    # -- signed urls -------------------------------------------------------
    def transformed_url(
        self,
        public_id: str,
        transformation: list[dict[str, Any]] | str,
        resource_type: str = "image",
        fmt: str | None = None,
    ) -> str:
        """Signed delivery URL with a transformation (CDN, signature, no expiry).

        Cloudinary's per-URL expiry for authenticated assets is only available on
        the download endpoint (``private_download_url``), which does not apply
        transformations. So transformed URLs are used for previews, and anything
        shared with a time limit is either the original asset or a redacted copy
        (see :meth:`create_redacted_copy`).
        """
        import cloudinary.utils

        try:
            url, _ = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type=resource_type,
                type="authenticated",
                sign_url=True,
                secure=True,
                transformation=transformation,
                format=fmt,
            )
            return url
        except Exception as exc:
            LOGGER.warning("Could not build a transformation URL for %s: %s", public_id, exc)
            raise StorageError(f"Could not create a transformed link: {exc}") from exc

    def signed_url(
        self,
        public_id: str,
        resource_type: str = "image",
        expires_in: int = 3600,
        transformation: list[dict[str, Any]] | str | None = None,
        fmt: str | None = None,
        attachment: bool = False,
    ) -> str:
        """Return an expiring, signed link (Cloudinary enforces the expiry)."""
        import cloudinary.utils

        if transformation:
            return self.transformed_url(public_id, transformation, resource_type=resource_type, fmt=fmt)
        expires_at = int(time.time()) + max(60, int(expires_in))
        try:
            return cloudinary.utils.private_download_url(
                public_id,
                fmt or "",
                resource_type=resource_type,
                type="authenticated",
                expires_at=expires_at,
                attachment=attachment,
            )
        except Exception as exc:
            LOGGER.warning("Could not sign URL for %s: %s", public_id, exc)
            raise StorageError(f"Could not create a signed link: {exc}") from exc

    def redacted_url(
        self,
        public_id: str,
        expires_in: int = 3600,
        blur_faces: bool = True,
        region: Region | None = None,
        resource_type: str = "image",
    ) -> str:
        """Return the transformation URL for the blurred/redacted delivery."""
        transformation = redaction_transformation(public_id, blur_faces, region)
        return self.transformed_url(
            public_id, transformation, resource_type=resource_type
        )

    def create_redacted_copy(
        self,
        public_id: str,
        resource_type: str = "image",
        blur_faces: bool = True,
        region: Region | None = None,
        fmt: str | None = None,
    ) -> dict[str, Any]:
        """Fetch the blurred delivery and store it as a separate authenticated asset.

        A derived asset is what makes a *time-limited* redacted share possible:
        the copy gets its own ``public_id``, which can be shared through
        ``private_download_url`` with a 1h/24h/7d expiry and deleted afterwards.
        """
        import cloudinary.uploader

        transformation = redaction_transformation(public_id, blur_faces, region)
        preview_url = self.transformed_url(public_id, transformation, resource_type=resource_type, fmt=fmt)
        try:
            with urlopen(preview_url, timeout=HTTP_TIMEOUT) as response:  # noqa: S310
                data = response.read()
        except Exception as exc:
            raise StorageError(f"Could not render the redacted copy: {exc}") from exc
        folder = public_id.rsplit("/", 1)[0] if "/" in public_id else FOLDER_ROOT
        copy_id = f"{public_id.rsplit('/', 1)[-1]}_redacted_{int(time.time())}"
        try:
            result = cloudinary.uploader.upload(
                data,
                resource_type=resource_type,
                type="authenticated",
                folder=folder,
                public_id=copy_id,
                tags="saakshya,redacted",
                context={"derived_from": public_id, "purpose": "privacy-safe share copy"},
                overwrite=False,
            )
        except Exception as exc:
            raise StorageError(f"Could not store the redacted copy: {exc}") from exc
        return {
            "public_id": result.get("public_id", f"{folder}/{copy_id}"),
            "resource_type": result.get("resource_type", resource_type),
            "format": result.get("format", fmt),
            "num_bytes": int(result.get("bytes") or len(data)),
            "transformation": transformation_to_str(transformation),
            "derived_from": public_id,
        }

    def delete_derived(self, public_id: str) -> None:
        """Delete redacted copies created for ``public_id``."""
        import cloudinary.api

        prefix = f"{public_id}_redacted"
        for resource_type in ("image", "video", "raw"):
            try:
                cloudinary.api.delete_resources_by_prefix(
                    prefix, resource_type=resource_type, type="authenticated"
                )
            except Exception as exc:  # nothing to delete is fine
                LOGGER.info("No derived copies removed for %s (%s)", public_id, exc)

    # -- bytes -------------------------------------------------------------
    def download_bytes(self, public_id: str, resource_type: str = "image", fmt: str | None = None) -> bytes:
        """Download the asset through a short-lived signed URL."""
        url = self.signed_url(public_id, resource_type=resource_type, expires_in=300, fmt=fmt)
        try:
            with urlopen(url, timeout=HTTP_TIMEOUT) as response:  # noqa: S310 - URL is signed by us
                return response.read()
        except Exception as exc:
            LOGGER.warning("Download failed for %s: %s", public_id, exc)
            raise StorageError(f"Could not download the asset: {exc}") from exc

    def thumbnail_bytes(self, public_id: str, resource_type: str = "image") -> bytes | None:
        """Fetch a small derived preview, or ``None`` when the fetch fails."""
        if resource_type not in {"image", "video"}:
            return None
        transformation = VIDEO_POSTER_TRANSFORMATION if resource_type == "video" else THUMB_TRANSFORMATION
        try:
            url = self.transformed_url(
                public_id,
                transformation,
                resource_type=resource_type,
                fmt="jpg" if resource_type == "video" else None,
            )
            with urlopen(url, timeout=HTTP_TIMEOUT) as response:  # noqa: S310
                return response.read()
        except Exception as exc:
            LOGGER.warning("Thumbnail fetch failed for %s: %s", public_id, exc)
            return None

    # -- deletes -----------------------------------------------------------
    def delete_asset(self, public_id: str, resource_type: str = "image") -> None:
        """Destroy one asset (``invalidate`` clears the CDN copy too)."""
        import cloudinary.uploader

        try:
            cloudinary.uploader.destroy(
                public_id, resource_type=resource_type, type="authenticated", invalidate=True
            )
        except Exception as exc:
            LOGGER.warning("Delete failed for %s: %s", public_id, exc)
            raise StorageError(f"Could not delete the asset: {exc}") from exc

    def delete_case_assets(self, case_id: str) -> None:
        """Delete every asset in the case folder, resource type by resource type."""
        import cloudinary.api

        prefix = f"{FOLDER_ROOT}/{case_id}/"
        errors: list[str] = []
        for resource_type in ("image", "video", "raw"):
            try:
                cloudinary.api.delete_resources_by_prefix(
                    prefix, resource_type=resource_type, type="authenticated"
                )
            except Exception as exc:  # an empty folder can raise; keep going
                errors.append(f"{resource_type}: {exc}")
                LOGGER.info("No %s assets deleted for case %s (%s)", resource_type, case_id, exc)
        if len(errors) == 3:
            raise StorageError(f"Could not delete the case folder remotely: {errors[0]}")


# ------------------------------------------------------------------ mock cloud
class MockStorage:
    """Local stand-in that mimics authenticated uploads and signed URLs."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.storage_dir
        self.thumb_dir = self.root / "thumbs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self._secret = _mock_secret(self.settings)

    # -- helpers -----------------------------------------------------------
    def _url(
        self,
        public_id: str,
        expires_in: int,
        transformation: str,
        kind: str,
    ) -> str:
        """Build a signed ``mock://`` URL with an expiry timestamp."""
        expires = int(time.time()) + max(60, int(expires_in))
        signature = _sign(self._secret, f"{public_id}|{expires}|{transformation}|{kind}")
        query = f"expires={expires}&sig={signature}&kind={kind}"
        if transformation:
            query += f"&t={quote(transformation, safe='')}"
        return f"mock://cdn/{quote(public_id, safe='')}?{query}"

    def _stored_path(self, public_id: str, fmt: str | None) -> Path:
        """Local path for a mock asset."""
        suffix = f".{fmt.lstrip('.')}" if fmt else ""
        return self.root / f"{public_id}{suffix}"

    def _resolve_any(self, public_id: str, fmt: str | None = None) -> Path | None:
        """Find the stored file, trying the given format then any suffix."""
        direct = self._stored_path(public_id, fmt)
        if direct.exists():
            return direct
        base = self.root / public_id
        if not base.parent.exists():
            return None
        for candidate in base.parent.glob(f"{base.name}.*"):
            if candidate.is_file():
                return candidate
        return None

    # -- upload ------------------------------------------------------------
    def upload(
        self,
        path: Path | str,
        case_id: str,
        evidence_type: str,
        tags: Iterable[str] | None = None,
        context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Copy the file locally and return Cloudinary-shaped metadata."""
        file_path = Path(path)
        if not file_path.exists():
            raise StorageError(f"File not found: {file_path.name}")
        suffix = file_path.suffix.lower().lstrip(".") or "bin"
        stem = "".join(ch for ch in file_path.stem if ch.isalnum() or ch in "-_")[:40] or "file"
        public_id = f"{FOLDER_ROOT}/{case_id}/{stem}_{uuid.uuid4().hex[:6]}"
        destination = self._stored_path(public_id, suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file_path, destination)
        data = destination.read_bytes()
        resource_type = _guess_resource_type(suffix)
        thumb_path = self._make_thumbnail(destination, public_id, resource_type)
        sign_args = dict(expires_in=3600)
        thumb_url = (
            self._url(public_id, sign_args["expires_in"], transformation_to_str(THUMB_TRANSFORMATION), "view")
            if resource_type in {"image", "video"}
            else ""
        )
        return {
            "public_id": public_id,
            "secure_url": self._url(public_id, 3600, "", "view"),
            "version": int(time.time()),
            "num_bytes": len(data),
            "etag": hashlib.md5(data).hexdigest(),  # noqa: S324 - parity with Cloudinary's etag
            "resource_type": resource_type,
            "format": suffix,
            "thumbnail_url": thumb_url,
            "poster_url": None,
            "folder": f"{FOLDER_ROOT}/{case_id}",
            "mock_thumb_path": str(thumb_path) if thumb_path else "",
            "tags": list(dict.fromkeys(["saakshya", case_id, evidence_type, *(tags or [])])),
            "context": {"case_id": case_id, "evidence_type": evidence_type, **(context or {})},
        }

    def _make_thumbnail(self, source: Path, public_id: str, resource_type: str) -> Path | None:
        """Create a local JPEG/PNG preview for images (best effort)."""
        if resource_type != "image":
            return None
        try:
            from PIL import Image

            with Image.open(source) as image:
                image = image.convert("RGB")
                image.thumbnail((480, 360))
                target = self.thumb_dir / f"{public_id.replace('/', '_')}.png"
                image.save(target, format="PNG")
                return target
        except Exception as exc:  # corrupt or unusual image: no preview
            LOGGER.info("Mock thumbnail skipped for %s (%s)", public_id, exc)
            return None

    # -- urls --------------------------------------------------------------
    def signed_url(
        self,
        public_id: str,
        resource_type: str = "image",
        expires_in: int = 3600,
        transformation: list[dict[str, Any]] | str | None = None,
        fmt: str | None = None,
        attachment: bool = False,
    ) -> str:
        """Return a signed mock URL (validated by :func:`verify_mock_url`)."""
        transformation_str = transformation_to_str(transformation)
        return self._url(public_id, expires_in, transformation_str, "download" if attachment else "view")

    def redacted_url(
        self,
        public_id: str,
        expires_in: int = 3600,
        blur_faces: bool = True,
        region: Region | None = None,
        resource_type: str = "image",
    ) -> str:
        """Return a signed mock URL that records the applied redaction."""
        transformation = transformation_to_str(redaction_transformation(public_id, blur_faces, region))
        return self._url(public_id, expires_in, transformation, "view")

    def transformed_url(
        self,
        public_id: str,
        transformation: list[dict[str, Any]] | str,
        resource_type: str = "image",
        fmt: str | None = None,
    ) -> str:
        """Return a signed mock URL carrying the transformation string."""
        return self._url(public_id, 3600, transformation_to_str(transformation), "view")

    def create_redacted_copy(
        self,
        public_id: str,
        resource_type: str = "image",
        blur_faces: bool = True,
        region: Region | None = None,
        fmt: str | None = None,
    ) -> dict[str, Any]:
        """Blur the image locally with Pillow and store it as a separate asset."""
        data = self.download_bytes(public_id, resource_type=resource_type, fmt=fmt)
        suffix = fmt or "png"
        if resource_type == "image":
            try:
                from PIL import Image, ImageFilter

                with Image.open(io.BytesIO(data)) as image:
                    blurred = image.convert("RGB")
                    if blur_faces:
                        blurred = blurred.filter(ImageFilter.GaussianBlur(radius=10))
                    buffer = io.BytesIO()
                    blurred.save(buffer, format="PNG")
                    data = buffer.getvalue()
                    suffix = "png"
            except Exception as exc:
                LOGGER.info("Mock redaction fell back to a byte copy (%s)", type(exc).__name__)
        folder = public_id.rsplit("/", 1)[0] if "/" in public_id else FOLDER_ROOT
        case_id = folder.split("/")[-1]
        stem = public_id.rsplit("/", 1)[-1]
        with tempfile.TemporaryDirectory(prefix="saakshya_redact_") as tmp_dir:
            path = Path(tmp_dir) / f"{stem}_redacted.{suffix}"
            path.write_bytes(data)
            uploaded = self.upload(path, case_id=case_id, evidence_type="redacted", tags=["redacted"])
        return {
            "public_id": uploaded["public_id"],
            "resource_type": uploaded["resource_type"],
            "format": uploaded["format"],
            "num_bytes": uploaded["num_bytes"],
            "transformation": transformation_to_str(
                redaction_transformation(public_id, blur_faces, region)
            ),
            "derived_from": public_id,
        }

    # -- bytes -------------------------------------------------------------
    def download_bytes(self, public_id: str, resource_type: str = "image", fmt: str | None = None) -> bytes:
        """Read the stored mock bytes."""
        path = self._resolve_any(public_id, fmt)
        if path is None:
            raise StorageError(f"Mock asset not found: {public_id}")
        return path.read_bytes()

    def thumbnail_bytes(self, public_id: str, resource_type: str = "image") -> bytes | None:
        """Read the local preview image, if it exists."""
        if resource_type != "image":
            return None
        path = self.thumb_dir / f"{public_id.replace('/', '_')}.png"
        return path.read_bytes() if path.exists() else None

    # -- deletes -----------------------------------------------------------
    def delete_asset(self, public_id: str, resource_type: str = "image") -> None:
        """Delete the stored file and its preview."""
        path = self._resolve_any(public_id)
        if path is not None:
            path.unlink(missing_ok=True)
        (self.thumb_dir / f"{public_id.replace('/', '_')}.png").unlink(missing_ok=True)

    def delete_derived(self, public_id: str) -> None:
        """Delete locally stored redacted copies of one asset."""
        folder, _, stem = public_id.rpartition("/")
        directory = self.root / folder
        if directory.exists():
            for candidate in directory.glob(f"{stem}_redacted*"):
                candidate.unlink(missing_ok=True)
        for thumb in self.thumb_dir.glob(f"{folder.replace('/', '_')}_{stem}_redacted*.png"):
            thumb.unlink(missing_ok=True)

    def delete_case_assets(self, case_id: str) -> None:
        """Delete the case folder and every preview belonging to it."""
        prefix = f"{FOLDER_ROOT}/{case_id}"
        folder = self.root / prefix
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        for thumb in self.thumb_dir.glob(f"{prefix.replace('/', '_')}_*.png"):
            thumb.unlink(missing_ok=True)

    # -- extras ------------------------------------------------------------
    def preview_bytes(self, public_id: str, resource_type: str = "image") -> bytes | None:
        """Alias used by the UI for mock previews."""
        return self.thumbnail_bytes(public_id, resource_type)


def _guess_resource_type(suffix: str) -> str:
    """Map a file suffix to Cloudinary's resource type (``auto`` result)."""
    if suffix in {"png", "jpg", "jpeg", "webp", "gif", "heic", "bmp", "tif", "tiff"}:
        return "image"
    if suffix in {"mp4", "mov", "webm", "avi", "mkv", "m4v"}:
        return "video"
    if suffix in {"mp3", "wav", "m4a", "ogg", "aac", "opus"}:
        return "video"
    return "raw"


_STORAGE: Storage | None = None


def get_storage(force_new: bool = False) -> Storage:
    """Return the process-wide storage backend (real or mock).

    A missing or broken Cloudinary configuration must never take the app down,
    so it falls back to :class:`MockStorage` with a warning that the UI shows.
    """
    global _STORAGE
    if force_new or _STORAGE is None:
        settings = get_settings()
        if settings.use_mock_cloudinary:
            _STORAGE = MockStorage(settings)
        elif not settings.cloudinary_configured:
            LOGGER.warning(
                "Cloudinary is not configured; using offline mock storage. "
                "Set CLOUDINARY_URL in .env for real uploads."
            )
            _STORAGE = MockStorage(settings)
        else:
            try:
                _STORAGE = CloudinaryStorage(settings)
            except StorageError as exc:
                LOGGER.warning("Cloudinary setup failed (%s); using offline mock storage.", exc)
                _STORAGE = MockStorage(settings)
        LOGGER.info("Storage backend: %s", type(_STORAGE).__name__)
    return _STORAGE


def reset_storage() -> None:
    """Drop the cached backend (tests change settings between cases)."""
    global _STORAGE
    _STORAGE = None


def storage_status() -> dict[str, Any]:
    """Describe the storage backend without leaking credentials."""
    settings = get_settings()
    backend = "mock" if isinstance(get_storage(), MockStorage) else "cloudinary"
    return {
        "backend": backend,
        "configured": settings.cloudinary_configured,
        "ocr_addon_enabled": settings.cloudinary_ocr_enabled,
        "root": str(settings.storage_dir) if backend == "mock" else f"{FOLDER_ROOT}/<case_id>/",
    }


def image_bytes_to_data_uri(data: bytes, mime: str = "image/png") -> str:
    """Encode bytes as a data URI (used for the vision-LLM OCR fallback)."""
    import base64

    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
