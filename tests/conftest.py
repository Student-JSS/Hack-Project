"""Test fixtures: isolated SQLite DB, mock Cloudinary storage, no LLM keys."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import db  # noqa: E402
from src.cloudinary_client import reset_storage  # noqa: E402
from src.config import reset_settings  # noqa: E402
from src.graph.build import reset_graph  # noqa: E402
from src.rag import reset_kb  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point every external dependency at a temporary, offline location."""
    monkeypatch.setenv("USE_MOCK_CLOUDINARY", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "saakshya.db"))
    monkeypatch.setenv("MOCK_STORAGE_DIR", str(tmp_path / "mock_cloudinary"))
    monkeypatch.setenv("EXPORTS_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("CHECKPOINT_BACKEND", "memory")
    monkeypatch.setenv("LLM_ENABLED", "true")
    for key in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    reset_settings()
    reset_storage()
    reset_graph()
    reset_kb()
    db.init_db()
    yield tmp_path
    reset_settings()
    reset_storage()
    reset_graph()
    reset_kb()
