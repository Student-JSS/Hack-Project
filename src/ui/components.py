"""Reusable Streamlit components (safety, privacy, badges, previews)."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from src import db
from src.cloudinary_client import MockStorage, Storage
from src.i18n import t
from src.ocr import method_label

NEUTRAL_SITE = "https://www.accuweather.com/"
PIN_ITERATIONS = 200_000
PIN_KEY = "app_pin_hash"


# --------------------------------------------------------------------- privacy
def hash_pin(pin: str, salt: str | None = None) -> str:
    """Return ``salt$pbkdf2_sha256`` for a PIN (never store the PIN itself)."""
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt), PIN_ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_pin(pin: str, stored: str | None) -> bool:
    """Check a PIN against the stored salted hash."""
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt), PIN_ITERATIONS)
    return hmac.compare_digest(candidate.hex(), digest)


def pin_is_set() -> bool:
    """True when the optional app PIN has been configured."""
    return bool(db.get_setting(PIN_KEY))


def pin_gate() -> None:
    """Stop the page until the PIN is entered (when a PIN is configured)."""
    if not pin_is_set() or st.session_state.get("unlocked"):
        return
    st.markdown(f"### 🔒 {t('pin_enter', get_lang())}")
    with st.form("pin_form"):
        pin = st.text_input(t("pin_enter", get_lang()), type="password", label_visibility="collapsed")
        submitted = st.form_submit_button(t("consent_continue", get_lang()), type="primary")
    if submitted:
        if verify_pin(pin, db.get_setting(PIN_KEY)):
            st.session_state["unlocked"] = True
            st.rerun()
        st.error(t("pin_wrong", get_lang()))
    st.stop()


def pin_controls(lang: str) -> None:
    """Sidebar controls to set, change or remove the app PIN."""
    with st.sidebar.expander(f"🔒 {t('pin', lang)}"):
        if pin_is_set():
            if st.button(t("pin_clear", lang), key="pin_clear"):
                db.delete_setting(PIN_KEY)
                st.session_state["unlocked"] = False
                st.success("PIN removed")
                st.rerun()
        new_pin = st.text_input(t("pin_set", lang), type="password", key="pin_new")
        if st.button(t("pin_set", lang), key="pin_save") and new_pin:
            if len(new_pin) < 4:
                st.warning("Use at least 4 characters.")
            else:
                db.set_setting(PIN_KEY, hash_pin(new_pin))
                st.session_state["unlocked"] = True
                st.success("PIN saved")
                st.rerun()


def quick_exit(lang: str) -> None:
    """Clear the session and jump to a neutral page (device-sharing safety)."""
    st.sidebar.markdown('<div class="saakshya-quick-exit">', unsafe_allow_html=True)
    if st.sidebar.button(f"🚪 {t('quick_exit', lang)}", help=t("quick_exit_help", lang), width="stretch"):
        st.session_state.clear()
        components.html(
            f"<script>window.top.location.replace('{NEUTRAL_SITE}');</script>",
            height=0,
        )
        st.stop()
    st.sidebar.markdown('</div>', unsafe_allow_html=True)


def get_lang() -> str:
    """Current UI language (session value, English default)."""
    return str(st.session_state.get("language", "en"))


# ----------------------------------------------------------------------- safety
def safety_banner(state: dict[str, Any], lang: str) -> None:
    """Prominent urgent-help block shown before anything else."""
    lines = state.get("urgent_help") or []
    if not lines:
        return
    lines_html = "".join(f"<div style='margin-bottom: 4px;'>• {line}</div>" for line in lines)
    helplines = [h.strip() for h in t("helplines", lang).split("·") if h.strip()]
    helplines_html = "".join(f'<span class="saakshya-helpline-chip">{h}</span>' for h in helplines)
    st.markdown(
        f"""
        <div class="saakshya-safety-box">
            <div class="saakshya-safety-title">🚨 {t('risk_high', lang)}</div>
            <div class="saakshya-safety-lines">{lines_html}</div>
            <div class="saakshya-helplines">{helplines_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def disclaimer(lang: str) -> None:
    """The legal-information disclaimer used at the bottom of every tab."""
    st.markdown(
        f'<div class="saakshya-disclaimer"><span style="font-size: 1.15rem;">⚖️</span><span>{t("disclaimer", lang)}</span></div>',
        unsafe_allow_html=True,
    )


def demo_banner(lang: str) -> None:
    """Display a banner indicating that the current case is using synthetic sample data."""
    st.markdown(
        f"""
        <div style="background: #EFF6FF; border: 1.5px solid #BFDBFE; border-radius: 12px; padding: 12px 18px; margin-bottom: 18px; display: flex; align-items: center; gap: 12px; box-shadow: 0 1px 3px rgba(37, 99, 235, 0.08);">
            <span style="font-size: 1.3rem;">🧪</span>
            <div style="font-size: 0.90rem; color: #1E40AF; font-weight: 500;">
                <strong style="color: #1E3A8A;">{t('demo_mode', lang)}:</strong> {t('demo_banner', lang)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------- badges
def pill(text: str, kind: str = "neutral") -> str:
    """Return the HTML for one small status pill."""
    return f'<span class="saakshya-pill saakshya-pill-{kind}">{text}</span>'


def integrity_pill(status: str | None, lang: str) -> str:
    """Map an integrity status to a coloured pill."""
    mapping = {
        "match": ("ok", t("integrity_ok", lang)),
        "mismatch": ("bad", t("integrity_bad", lang)),
        "error": ("warn", t("integrity_error", lang)),
    }
    kind, label = mapping.get(str(status or "unverified"), ("neutral", t("integrity_unchecked", lang)))
    return pill(label, kind)


def ocr_pill(method: str | None) -> str:
    """Show which OCR engine produced the text."""
    return pill(method_label(str(method or "none")), "neutral")


def stage_pills(state: dict[str, Any], lang: str) -> str:
    """Risk level, OCR methods and approval state in one line."""
    risk = str(state.get("risk_level") or "low")
    kind = {"high": "bad", "medium": "warn"}.get(risk, "ok")
    pills = [pill(f"{t('risk', lang)}: {risk.upper()}", kind)]
    if state.get("human_approved"):
        pills.append(pill(f"✓ {t('approved', lang)}", "ok"))
    if state.get("errors"):
        pills.append(pill(f"{len(state['errors'])} error(s)", "warn"))
    return " ".join(pills)


# -------------------------------------------------------------------- previews
def preview_source(item: dict[str, Any], storage: Storage, expires_in: int = 1800) -> bytes | str | None:
    """Return bytes (mock/offline) or a signed URL for an evidence preview."""
    public_id = str(item.get("public_id") or "")
    resource_type = str(item.get("resource_type") or "image")
    if not public_id:
        return None
    if isinstance(storage, MockStorage):
        try:
            return storage.thumbnail_bytes(public_id, resource_type)
        except Exception:
            return None
    try:
        return storage.signed_url(
            public_id,
            resource_type=resource_type,
            expires_in=expires_in,
            transformation=[{"width": 480, "height": 360, "crop": "fill"}],
        )
    except Exception:
        return None


def render_media(item: dict[str, Any], storage: Storage, lang: str) -> None:
    """Render an image preview or an audio/video player for one item."""
    resource_type = str(item.get("resource_type") or "image")
    try:
        if resource_type == "image":
            source = preview_source(item, storage)
            if isinstance(source, bytes):
                st.image(source, width="stretch")
            elif isinstance(source, str):
                st.image(source, width="stretch")
            else:
                st.caption("Preview unavailable.")
        elif resource_type in {"video", "raw"} and str(item.get("format")) in {
            "mp3", "wav", "m4a", "ogg", "aac", "opus", "mp4", "mov", "webm", "m4v",
        }:
            data = storage.download_bytes(
                str(item["public_id"]), resource_type=resource_type, fmt=str(item.get("format") or "")
            )
            is_audio = str(item.get("format")) in {"mp3", "wav", "m4a", "ogg", "aac", "opus"}
            if is_audio:
                st.audio(data, format=f"audio/{item.get('format')}")
            else:
                st.video(data)
        else:
            st.caption("No inline preview for this file type.")
    except Exception as exc:
        st.caption(f"Preview unavailable ({type(exc).__name__}).")


# ------------------------------------------------------------------- formatting
def human_size(num_bytes: Any) -> str:
    """Format bytes as KB/MB."""
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def storage_badge(storage: Storage, lang: str) -> str:
    """Pill showing whether Cloudinary is real or mocked."""
    if isinstance(storage, MockStorage):
        return pill(t("mock_badge", lang), "warn")
    return pill("Cloudinary (authenticated)", "ok")
