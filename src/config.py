"""Configuration and logging for Saakshya.

Every secret is read from the environment (``.env``); nothing is hard-coded.
``Settings.describe()`` is safe to show in the UI because it never returns
secret values. Story text and evidence content must never be logged - the
helper :func:`get_logger` exists so that only metadata reaches the logs.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

SUPPORTED_PROVIDERS = ("google", "openai", "anthropic")
DEFAULT_MODELS = {
    "google": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
}
_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
_LOGGING_READY = False


def _env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment flag (``1/true/yes/on`` are true)."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_int(name: str, default: int) -> int:
    """Read an integer environment value, falling back on a bad value."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float environment value, falling back on a bad value."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_path(name: str, default: str) -> Path:
    """Read a path, resolved relative to the project root when relative."""
    raw = os.getenv(name, "").strip() or default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path)


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the app configuration."""

    # LLM
    llm_provider: str = "google"
    llm_model: str = ""
    llm_temperature: float = 0.2
    llm_enabled: bool = True
    google_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Cloudinary
    cloudinary_url: str = ""
    cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    use_mock_cloudinary: bool = False
    cloudinary_ocr_enabled: bool = False

    # App
    demo_mode: bool = False
    db_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "saakshya.db")
    checkpoint_backend: str = "memory"
    checkpoint_db_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "checkpoints.db"
    )
    share_default_hours: int = 24

    # Tracing
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "saakshya"

    log_level: str = "INFO"

    # Derived directories (not read from the environment).
    project_root: Path = PROJECT_ROOT
    kb_dir: Path = PROJECT_ROOT / "data" / "legal_kb"
    samples_dir: Path = PROJECT_ROOT / "data" / "samples"
    exports_dir: Path = PROJECT_ROOT / "data" / "exports"
    storage_dir: Path = PROJECT_ROOT / "data" / "mock_cloudinary"

    # ---------------------------------------------------------------- builders
    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from the current environment."""
        provider = (os.getenv("LLM_PROVIDER") or "google").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            provider = "google"
        return cls(
            llm_provider=provider,
            llm_model=(os.getenv("LLM_MODEL") or "").strip(),
            llm_temperature=_env_float("LLM_TEMPERATURE", 0.2),
            llm_enabled=_env_bool("LLM_ENABLED", True),
            google_api_key=(os.getenv("GOOGLE_API_KEY") or "").strip(),
            openai_api_key=(os.getenv("OPENAI_API_KEY") or "").strip(),
            anthropic_api_key=(os.getenv("ANTHROPIC_API_KEY") or "").strip(),
            cloudinary_url=(os.getenv("CLOUDINARY_URL") or "").strip(),
            cloud_name=(os.getenv("CLOUD_NAME") or "").strip(),
            cloudinary_api_key=(os.getenv("CLOUDINARY_API_KEY") or "").strip(),
            cloudinary_api_secret=(os.getenv("CLOUDINARY_API_SECRET") or "").strip(),
            use_mock_cloudinary=_env_bool("USE_MOCK_CLOUDINARY", False),
            cloudinary_ocr_enabled=_env_bool("CLOUDINARY_OCR_ENABLED", False),
            demo_mode=_env_bool("DEMO_MODE", False),
            db_path=_env_path("DB_PATH", "data/saakshya.db"),
            checkpoint_backend=(os.getenv("CHECKPOINT_BACKEND") or "memory").strip().lower(),
            checkpoint_db_path=_env_path("CHECKPOINT_DB_PATH", "data/checkpoints.db"),
            share_default_hours=_env_int("SHARE_DEFAULT_HOURS", 24),
            langsmith_tracing=_env_bool("LANGSMITH_TRACING", False),
            langsmith_api_key=(os.getenv("LANGSMITH_API_KEY") or "").strip(),
            langsmith_project=(os.getenv("LANGSMITH_PROJECT") or "saakshya").strip(),
            log_level=(os.getenv("LOG_LEVEL") or "INFO").strip().upper(),
            exports_dir=_env_path("EXPORTS_DIR", "data/exports"),
            storage_dir=_env_path("MOCK_STORAGE_DIR", "data/mock_cloudinary"),
        )

    # ------------------------------------------------------------ derived flags
    @property
    def model_name(self) -> str:
        """Model id for the selected provider (provider default when unset)."""
        return self.llm_model or DEFAULT_MODELS.get(self.llm_provider, "")

    @property
    def provider_api_key(self) -> str:
        """API key belonging to the configured provider."""
        return {
            "google": self.google_api_key,
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
        }.get(self.llm_provider, "")

    @property
    def has_llm_credentials(self) -> bool:
        """True when the selected provider has a key configured."""
        return bool(self.provider_api_key)

    @property
    def llm_ready(self) -> bool:
        """True when LLM calls should be attempted at all."""
        return self.llm_enabled and self.has_llm_credentials and not self.demo_mode

    @property
    def cloudinary_configured(self) -> bool:
        """True when enough Cloudinary config exists to sign requests."""
        if self.use_mock_cloudinary:
            return True
        return bool(self.cloudinary_url) or bool(
            self.cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret
        )

    # --------------------------------------------------------------- utilities
    def ensure_dirs(self) -> None:
        """Create the writable directories the app uses (idempotent)."""
        for path in (self.db_path.parent, self.exports_dir, self.storage_dir):
            path.mkdir(parents=True, exist_ok=True)
        if self.checkpoint_backend == "sqlite":
            self.checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)

    def describe(self) -> dict[str, Any]:
        """Return a UI-safe summary (booleans instead of secret values)."""
        return {
            "llm_provider": self.llm_provider,
            "llm_model": self.model_name,
            "llm_ready": self.llm_ready,
            "demo_mode": self.demo_mode,
            "mock_cloudinary": self.use_mock_cloudinary,
            "cloudinary_configured": self.cloudinary_configured,
            "cloudinary_ocr_enabled": self.cloudinary_ocr_enabled,
            "checkpoint_backend": self.checkpoint_backend,
            "db_path": str(self.db_path),
        }


def _configure_logging(level: str) -> None:
    """Install a single stderr handler (called once per process)."""
    global _LOGGING_READY
    if _LOGGING_READY:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root = logging.getLogger("saakshya")
    root.setLevel(getattr(logging, level, logging.INFO))
    root.addHandler(handler)
    root.propagate = False
    _LOGGING_READY = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings snapshot (cleared by ``reset_settings``)."""
    settings = Settings.from_env()
    _configure_logging(settings.log_level)
    settings.ensure_dirs()
    if settings.langsmith_tracing and settings.langsmith_api_key:
        # LangGraph/LangChain read these env vars directly.
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    return settings


def reset_settings() -> None:
    """Drop the cached settings (used by tests after changing env vars)."""
    get_settings.cache_clear()


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger. Never log story text or file content."""
    get_settings()
    return logging.getLogger(f"saakshya.{name}")
