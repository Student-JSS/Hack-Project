"""SQLite persistence for Saakshya.

Only structured metadata lives here: case narrative, evidence metadata plus the
SHA-256 integrity record, share links, approvals and a content-free audit log.
Binary evidence always stays in Cloudinary.

Every public function takes an optional ``db_path`` so tests can point at a
temporary database without touching real data.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from src.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    user_story TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'en',
    status TEXT NOT NULL DEFAULT 'open',
    risk_level TEXT,
    issue_categories TEXT,
    followup_answers TEXT,
    timeline TEXT,
    timeline_gaps TEXT,
    action_plan TEXT,
    legal_matches TEXT,
    draft_text TEXT,
    verifier_status TEXT,
    human_approved INTEGER NOT NULL DEFAULT 0,
    approver TEXT,
    consent_accepted INTEGER NOT NULL DEFAULT 0,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    filename TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    public_id TEXT NOT NULL,
    secure_url TEXT,
    version INTEGER,
    format TEXT,
    num_bytes INTEGER,
    etag TEXT,
    sha256 TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    ocr_text TEXT,
    ocr_method TEXT,
    transcript TEXT,
    thumbnail_url TEXT,
    tags TEXT,
    context TEXT,
    integrity_status TEXT NOT NULL DEFAULT 'unverified',
    integrity_checked_at TEXT
);

CREATE TABLE IF NOT EXISTS share_links (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    evidence_id TEXT REFERENCES evidence(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    url TEXT NOT NULL,
    transformations TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    draft_text TEXT NOT NULL,
    approver TEXT,
    verifier_status TEXT,
    approved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence(case_id);
CREATE INDEX IF NOT EXISTS idx_share_case ON share_links(case_id);
CREATE INDEX IF NOT EXISTS idx_approval_case ON approvals(case_id);
"""

CASE_FIELDS = {
    "title",
    "user_story",
    "language",
    "status",
    "risk_level",
    "issue_categories",
    "followup_answers",
    "timeline",
    "timeline_gaps",
    "action_plan",
    "legal_matches",
    "draft_text",
    "verifier_status",
    "human_approved",
    "approver",
    "consent_accepted",
    "is_demo",
    "updated_at",
}
EVIDENCE_FIELDS = {
    "label",
    "filename",
    "evidence_type",
    "resource_type",
    "public_id",
    "secure_url",
    "version",
    "format",
    "num_bytes",
    "etag",
    "sha256",
    "uploaded_at",
    "ocr_text",
    "ocr_method",
    "transcript",
    "thumbnail_url",
    "tags",
    "context",
    "integrity_status",
    "integrity_checked_at",
}
JSON_CASE_FIELDS = ("issue_categories", "followup_answers", "timeline", "timeline_gaps", "action_plan", "legal_matches")
JSON_EVIDENCE_FIELDS = ("tags", "context")


def utc_now() -> str:
    """Current UTC time as an ISO-8601 string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    """Return a short, sortable, collision-safe identifier."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@contextmanager
def get_conn(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection with row access by name, committing on success."""
    path = Path(db_path) if db_path else get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    """Create every table if it does not exist yet (idempotent)."""
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)


def _dump(value: Any) -> str | None:
    """JSON-encode a value for storage (``None`` stays ``None``)."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _load(value: Any) -> Any:
    """Decode a JSON column, returning ``None`` when empty or invalid."""
    if value in (None, ""):
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _row(row: sqlite3.Row | None, json_fields: tuple[str, ...]) -> dict[str, Any] | None:
    """Convert a row to a dict with selected JSON columns decoded."""
    if row is None:
        return None
    data = dict(row)
    for field in json_fields:
        if field in data:
            data[field] = _load(data[field])
    return data


# --------------------------------------------------------------------- cases
def create_case(
    title: str,
    user_story: str,
    language: str = "en",
    is_demo: bool = False,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Insert a new case and return it."""
    case_id = new_id("case")
    now = utc_now()
    with get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO cases (id, title, user_story, language, status, is_demo,
                                  created_at, updated_at)
               VALUES (?, ?, ?, ?, 'open', ?, ?, ?)""",
            (case_id, title.strip() or "Untitled case", user_story, language, int(is_demo), now, now),
        )
    log_event(case_id, "case_created", detail="demo" if is_demo else "", db_path=db_path)
    case = get_case(case_id, db_path=db_path)
    assert case is not None
    return case


def get_case(case_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Fetch one case by id."""
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return _row(row, JSON_CASE_FIELDS)


def list_cases(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """List cases newest-first."""
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
    return [_row(r, JSON_CASE_FIELDS) or {} for r in rows]


def update_case(case_id: str, db_path: Path | str | None = None, **fields: Any) -> None:
    """Update whitelisted case columns; JSON fields are encoded automatically."""
    updates = {k: v for k, v in fields.items() if k in CASE_FIELDS}
    if not updates:
        return
    if "updated_at" not in updates:
        updates["updated_at"] = utc_now()
    payload = {k: (_dump(v) if k in JSON_CASE_FIELDS else v) for k, v in updates.items()}
    assignments = ", ".join(f"{name} = ?" for name in payload)
    with get_conn(db_path) as conn:
        conn.execute(
            f"UPDATE cases SET {assignments} WHERE id = ?",
            (*payload.values(), case_id),
        )


def delete_case(case_id: str, db_path: Path | str | None = None) -> None:
    """Delete a case and every dependent row (evidence, shares, approvals)."""
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))


# ------------------------------------------------------------------ evidence
def next_evidence_label(case_id: str, db_path: Path | str | None = None) -> str:
    """Return the next human-friendly evidence label (E1, E2, ...)."""
    with get_conn(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM evidence WHERE case_id = ?", (case_id,)
        ).fetchone()["n"]
    return f"E{int(count) + 1}"


def add_evidence(case_id: str, record: dict[str, Any], db_path: Path | str | None = None) -> dict[str, Any]:
    """Insert an evidence metadata row together with its integrity record."""
    evidence_id = record.get("id") or new_id("ev")
    label = record.get("label") or next_evidence_label(case_id, db_path=db_path)
    payload = {
        "label": label,
        "filename": record.get("filename", "file"),
        "evidence_type": record.get("evidence_type", "other"),
        "resource_type": record.get("resource_type", "image"),
        "public_id": record["public_id"],
        "secure_url": record.get("secure_url"),
        "version": record.get("version"),
        "format": record.get("format"),
        "num_bytes": record.get("num_bytes"),
        "etag": record.get("etag"),
        "sha256": record["sha256"],
        "uploaded_at": record.get("uploaded_at") or utc_now(),
        "ocr_text": record.get("ocr_text"),
        "ocr_method": record.get("ocr_method"),
        "transcript": record.get("transcript"),
        "thumbnail_url": record.get("thumbnail_url"),
        "tags": record.get("tags"),
        "context": record.get("context"),
        "integrity_status": record.get("integrity_status", "unverified"),
        "integrity_checked_at": record.get("integrity_checked_at"),
    }
    columns = ", ".join(payload)
    placeholders = ", ".join("?" for _ in payload)
    with get_conn(db_path) as conn:
        conn.execute(
            f"INSERT INTO evidence (id, case_id, {columns}) VALUES (?, ?, {placeholders})",
            (evidence_id, case_id, *(_dump(v) if k in JSON_EVIDENCE_FIELDS else v for k, v in payload.items())),
        )
    log_event(case_id, "evidence_added", detail=label, db_path=db_path)
    evidence = get_evidence(evidence_id, db_path=db_path)
    assert evidence is not None
    return evidence


def get_evidence(evidence_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Fetch one evidence row."""
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone()
    return _row(row, JSON_EVIDENCE_FIELDS)


def list_evidence(case_id: str, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """List evidence for a case in upload order."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM evidence WHERE case_id = ? ORDER BY uploaded_at ASC, label ASC",
            (case_id,),
        ).fetchall()
    return [_row(r, JSON_EVIDENCE_FIELDS) or {} for r in rows]


def update_evidence(evidence_id: str, db_path: Path | str | None = None, **fields: Any) -> None:
    """Update whitelisted evidence columns."""
    updates = {k: v for k, v in fields.items() if k in EVIDENCE_FIELDS}
    if not updates:
        return
    payload = {k: (_dump(v) if k in JSON_EVIDENCE_FIELDS else v) for k, v in updates.items()}
    assignments = ", ".join(f"{name} = ?" for name in payload)
    with get_conn(db_path) as conn:
        conn.execute(
            f"UPDATE evidence SET {assignments} WHERE id = ?", (*payload.values(), evidence_id)
        )


def delete_evidence_row(evidence_id: str, db_path: Path | str | None = None) -> None:
    """Delete an evidence row (the Cloudinary asset is deleted separately)."""
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM evidence WHERE id = ?", (evidence_id,))


def evidence_counts(case_id: str, db_path: Path | str | None = None) -> dict[str, int]:
    """Return total / matched / mismatch counts for a case's evidence."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT integrity_status, COUNT(*) AS n FROM evidence WHERE case_id = ? GROUP BY integrity_status",
            (case_id,),
        ).fetchall()
    counts = {"total": 0, "match": 0, "mismatch": 0, "unverified": 0}
    for row in rows:
        counts["total"] += int(row["n"])
        status = str(row["integrity_status"])
        counts[status] = counts.get(status, 0) + int(row["n"])
    return counts


# ---------------------------------------------------------------- share links
def add_share(
    case_id: str,
    kind: str,
    url: str,
    expires_at: str,
    evidence_id: str | None = None,
    transformations: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Persist a signed share link so the owner can audit and revoke it."""
    share_id = new_id("share")
    now = utc_now()
    with get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO share_links (id, case_id, evidence_id, kind, url, transformations,
                                        expires_at, created_at, revoked)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (share_id, case_id, evidence_id, kind, url, transformations, expires_at, now),
        )
    log_event(case_id, "share_created", detail=f"{kind} until {expires_at}", db_path=db_path)
    return {
        "id": share_id,
        "case_id": case_id,
        "evidence_id": evidence_id,
        "kind": kind,
        "url": url,
        "transformations": transformations,
        "expires_at": expires_at,
        "created_at": now,
        "revoked": 0,
    }


def list_shares(case_id: str, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """List share links for a case, newest first."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM share_links WHERE case_id = ? ORDER BY created_at DESC", (case_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def revoke_share(share_id: str, db_path: Path | str | None = None) -> None:
    """Mark a share link revoked (it also expires on its own)."""
    with get_conn(db_path) as conn:
        conn.execute("UPDATE share_links SET revoked = 1 WHERE id = ?", (share_id,))


# ----------------------------------------------------------------- approvals
def save_approval(
    case_id: str,
    draft_text: str,
    approver: str | None = None,
    verifier_status: str | None = None,
    db_path: Path | str | None = None,
) -> None:
    """Record a human approval of a complaint draft (nothing exported without it)."""
    with get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO approvals (case_id, draft_text, approver, verifier_status, approved_at)
               VALUES (?, ?, ?, ?, ?)""",
            (case_id, draft_text, approver, verifier_status, utc_now()),
        )
    update_case(
        case_id,
        db_path=db_path,
        draft_text=draft_text,
        human_approved=1,
        approver=approver,
        verifier_status=verifier_status,
    )
    log_event(case_id, "draft_approved", db_path=db_path)


def get_approval(case_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Return the most recent approval for a case, if any."""
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM approvals WHERE case_id = ? ORDER BY approved_at DESC LIMIT 1",
            (case_id,),
        ).fetchone()
    return dict(row) if row else None


# -------------------------------------------------------------- app settings
def get_setting(key: str, db_path: Path | str | None = None) -> str | None:
    """Read an app-level setting (used for the optional PIN and consent)."""
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str, db_path: Path | str | None = None) -> None:
    """Upsert an app-level setting."""
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def delete_setting(key: str, db_path: Path | str | None = None) -> None:
    """Remove an app-level setting."""
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))


# ------------------------------------------------------------------ audit log
def log_event(
    case_id: str | None, action: str, detail: str = "", db_path: Path | str | None = None
) -> None:
    """Append a metadata-only audit entry (never story or evidence content)."""
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO audit_log (case_id, action, detail, created_at) VALUES (?, ?, ?, ?)",
            (case_id, action, detail[:200], utc_now()),
        )


def list_events(case_id: str, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """List audit entries for a case, newest first."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE case_id = ? ORDER BY id DESC", (case_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_everything(db_path: Path | str | None = None) -> None:
    """Delete every row in every table (the 'delete everything' button)."""
    with get_conn(db_path) as conn:
        for table in ("approvals", "share_links", "evidence", "cases", "audit_log", "app_settings"):
            conn.execute(f"DELETE FROM {table}")
