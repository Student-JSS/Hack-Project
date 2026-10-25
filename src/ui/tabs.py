"""The seven tabs of the Saakshya app.

Each renderer takes a :class:`UIContext` so the tab code never reaches for global
state. All destructive actions ask for confirmation, and everything that leaves
the device (share link, PDF) is explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

from src import db
from src.cloudinary_client import Region, Storage, StorageError
from src.config import Settings
from src.graph.build import NODE_ORDER, graph_mermaid, graph_node_table, pending_interrupt
from src.i18n import LANGUAGES, t
from src.ingest import delete_case, delete_evidence, ingest_bytes, verify_evidence
from src.pdf_export import build_evidence_packet
from src.rag import get_kb
from src.ui.components import (
    disclaimer,
    human_size,
    integrity_pill,
    ocr_pill,
    pill,
    preview_source,
    render_media,
    stage_pills,
)
from src.ui.state import clear_run

EVIDENCE_TYPES = ["screenshot", "photo", "audio", "video", "document", "other"]
SHARE_OPTIONS = {1: "1 hour", 24: "24 hours", 168: "7 days"}
STAGE_ORDER = {
    "new": 0,
    "intake_questions": 0,
    "intake_error": 0,
    "intake_done": 1,
    "safety_checked": 2,
    "evidence_analyzed": 3,
    "timeline_built": 4,
    "classified": 5,
    "rights_matched": 6,
    "plan_ready": 7,
    "draft_ready": 8,
    "verification_failed": 9,
    "verified": 10,
    "approved": 10,
    "changes_requested": 10,
}
RIGHTS_FALLBACK_IDS = ("KB-01", "KB-03", "KB-05", "KB-07", "KB-09", "KB-11", "KB-13")


@dataclass
class UIContext:
    """Everything a tab needs to render."""

    lang: str
    case: dict[str, Any] | None
    state: dict[str, Any]
    run_index: int
    settings: Settings
    storage: Storage


# ------------------------------------------------------------------- utilities
def _utc_iso(hours: int) -> str:
    """ISO timestamp ``hours`` from now."""
    return (
        (datetime.now(timezone.utc) + timedelta(hours=hours))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _remaining(expires_at: str) -> str:
    """Human countdown until a share link expires."""
    try:
        target = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    delta = target - datetime.now(timezone.utc)
    if delta.total_seconds() <= 0:
        return "expired"
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def parse_region(text: str) -> Region | None:
    """Parse ``x, y, width, height`` into a :class:`Region`."""
    parts = [part.strip() for part in (text or "").split(",")]
    if len(parts) != 4:
        return None
    try:
        x, y, width, height = (int(float(part)) for part in parts)
    except ValueError:
        return None
    if width <= 0 or height <= 0 or x < 0 or y < 0:
        return None
    return Region(x, y, width, height)


def _require_case(ctx: UIContext) -> bool:
    """Render a hint and return ``False`` when no case is selected."""
    if ctx.case is None:
        st.info(t("no_case", ctx.lang))
        return False
    return True


# --------------------------------------------------------------- tab 1: story
def render_case_tab(ctx: UIContext) -> None:
    """Create or update the case and start the agent pipeline."""
    lang = ctx.lang
    st.subheader(f"📝 {t('tab_case', lang)}")
    stage_pills_html = stage_pills(ctx.state, lang)
    if stage_pills_html:
        st.markdown(stage_pills_html, unsafe_allow_html=True)

    case = ctx.case
    with st.form("case_form"):
        title = st.text_input(
            t("case_title", lang),
            value=(case or {}).get("title", ""),
            placeholder="e.g. Messages from my husband, March 2026",
        )
        story = st.text_area(
            t("story_label", lang),
            value=(case or {}).get("user_story", ""),
            height=220,
            help=t("story_help", lang),
        )
        language = st.radio(
            t("language", lang),
            options=list(LANGUAGES),
            format_func=lambda code: LANGUAGES[code],
            index=list(LANGUAGES).index((case or {}).get("language", lang) or "en"),
            horizontal=True,
        )
        submitted = st.form_submit_button(f"✨ {t('analyse', lang)}", type="primary")

    if submitted:
        if len(story.strip()) < 12:
            st.warning("Please add a little more detail (at least a sentence).")
        else:
            if case is None:
                created = db.create_case(
                    title or "My case",
                    story.strip(),
                    language,
                    is_demo=bool(st.session_state.get("demo_mode")),
                )
                st.session_state["case_id"] = created["id"]
            else:
                db.update_case(
                    case["id"],
                    title=title or case.get("title", "My case"),
                    user_story=story.strip(),
                    language=language,
                )
            clear_run()
            st.session_state["pending_run"] = True
            st.rerun()

    if case is None:
        st.caption(t("demo_run_hint", lang))
        disclaimer(lang)
        return

    # Follow-up question loop (bounded to one round of up to three questions).
    questions = ctx.state.get("followup_questions") or []
    if questions and not ctx.state.get("intake_complete"):
        st.divider()
        st.markdown(f"#### {t('followup_title', lang)}")
        st.caption(t("followup_help", lang))
        with st.form("followup_form"):
            answers = [
                st.text_area(question, key=f"followup_{index}", height=70, placeholder=t("answer_placeholder", lang))
                for index, question in enumerate(questions)
            ]
            if st.form_submit_button(t("submit_answers", lang), type="primary"):
                cleaned = [answer.strip() for answer in answers if answer.strip()]
                if not cleaned:
                    st.warning("Please answer at least one question.")
                else:
                    db.update_case(
                        case["id"],
                        followup_answers=list(case.get("followup_answers") or []) + cleaned,
                    )
                    clear_run()
                    st.session_state["pending_run"] = True
                    st.rerun()

    if ctx.state.get("human_approved"):
        st.success(f"✅ {t('approved', lang)}")
    elif pending_interrupt(ctx.state):
        st.info("➡️ The draft is waiting for your approval in tab 6.")

    render_pipeline_panel(ctx.state, lang)

    with st.expander("🔁 " + t("rerun", lang)):
        st.caption(
            "Re-runs every node for this case, using the story and the evidence currently stored."
        )
        if st.button(t("rerun", lang), key="rerun_pipeline"):
            clear_run()
            st.session_state["pending_run"] = True
            st.rerun()
    disclaimer(lang)


def render_pipeline_panel(state: dict[str, Any], lang: str) -> None:
    """Show the graph nodes with live progress and the mermaid source."""
    stage = str(state.get("stage") or "new")
    done_upto = STAGE_ORDER.get(stage, 0)
    paused = pending_interrupt(state) is not None
    nodes = graph_node_table()
    with st.expander(f"🧭 {t('agent_steps', lang)}", expanded=False):
        rows = []
        for index, node in enumerate(NODE_ORDER, start=1):
            if index == 10 and paused:
                marker, css = "⏸", "saakshya-node-active"
            elif index <= done_upto:
                marker, css = "✅", "saakshya-node-done"
            else:
                marker, css = "○", ""
            label = nodes[index - 1]["label"]
            rows.append(f'<div class="saakshya-node {css}">{marker} {index:02d}. {label}</div>')
        st.markdown("".join(rows), unsafe_allow_html=True)
        if state.get("errors"):
            st.caption("Errors recorded: " + ", ".join(state["errors"]))
        st.caption(t("pipeline_graph", lang))
        st.code(graph_mermaid(), language="mermaid")


# -------------------------------------------------------------- tab 2: vault
def render_vault_tab(ctx: UIContext) -> None:
    """Upload, inspect, verify, share and delete evidence."""
    lang = ctx.lang
    st.subheader(f"🗄️ {t('tab_vault', lang)}")
    if not _require_case(ctx):
        return
    assert ctx.case is not None
    case_id = ctx.case["id"]
    evidence = db.list_evidence(case_id)

    counts = db.evidence_counts(case_id)
    cols = st.columns(3)
    cols[0].metric(t("evidence_count", lang), counts.get("total", 0))
    cols[1].metric(t("integrity_ok", lang), counts.get("match", 0))
    cols[2].metric(t("integrity_bad", lang), counts.get("mismatch", 0))

    with st.expander(f"➕ {t('upload', lang)}", expanded=not evidence):
        uploaded = st.file_uploader(
            t("add_files", lang),
            accept_multiple_files=True,
            type=["png", "jpg", "jpeg", "webp", "gif", "heic", "mp3", "wav", "m4a", "ogg", "mp4", "mov", "webm", "pdf", "txt"],
        )
        evidence_type = st.selectbox(
            t("file_type", lang), EVIDENCE_TYPES, index=0, format_func=lambda value: value.capitalize()
        )
        note = st.text_input(
            t("note_optional", lang),
            help="For audio or video, type what is said. This becomes part of the evidence index.",
        )
        if st.button(t("upload_button", lang), type="primary", disabled=not uploaded):
            with st.status(t("uploading", lang), expanded=True) as status:
                for file in uploaded or []:
                    try:
                        row = ingest_bytes(
                            case_id,
                            file.getvalue(),
                            file.name,
                            evidence_type,
                            note=note,
                            storage=ctx.storage,
                        )
                        st.write(
                            f"✅ {row['label']} · {file.name} · SHA-256 {str(row['sha256'])[:16]}… "
                            f"· OCR: {row['ocr_method']}"
                        )
                    except Exception as exc:
                        st.error(f"Could not store {file.name}: {type(exc).__name__}")
                status.update(label=t("agent_finished", lang), state="complete", expanded=False)
            clear_run()
            st.rerun()

    if not evidence:
        st.info(t("no_evidence", lang))
        disclaimer(lang)
        return

    st.markdown(f"#### {t('tab_vault', lang)}")
    for item in evidence:
        _render_evidence_card(item, ctx)

    _render_share_list(case_id, lang)
    disclaimer(lang)


def _render_evidence_card(item: dict[str, Any], ctx: UIContext) -> None:
    """One evidence card: preview, hashes, OCR text, sharing and deletion."""
    lang = ctx.lang
    with st.container(border=True):
        left, right = st.columns([1, 1.15], gap="large")
        with left:
            render_media(item, ctx.storage, lang)
        with right:
            st.markdown(
                f"**{item['label']} · {item['filename']}**  \n"
                f"{human_size(item.get('num_bytes'))} · {item.get('evidence_type')} · "
                f"{str(item.get('uploaded_at', ''))[:16].replace('T', ' ')} UTC",
                unsafe_allow_html=True,
            )
            st.markdown(
                integrity_pill(item.get("integrity_status"), lang) + ocr_pill(item.get("ocr_method")),
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="saakshya-hash">SHA-256 {item.get("sha256")}</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"Cloudinary: {item.get('public_id')} · v{item.get('version')} · {item.get('resource_type')}"
            )

            if st.button(t("verify", lang), key=f"verify_{item['id']}"):
                result = verify_evidence(item["id"], storage=ctx.storage)
                if result.ok:
                    st.success(f"{t('integrity_ok', lang)} · {result.actual_sha256[:24]}…")
                    if result.etag_matches is False:
                        st.warning("The Cloudinary etag did not match the downloaded bytes.")
                else:
                    st.error(f"{result.status}: {result.detail or 'hash mismatch'}")
                st.rerun()

            with st.expander(f"📄 {t('text_extraction', lang)}"):
                st.caption(f"{t('text_extraction', lang)}: {item.get('ocr_method') or 'none'}")
                st.code(item.get("ocr_text") or "— no text extracted —")
                manual = st.text_area(
                    t("note_optional", lang),
                    value=item.get("transcript") or "",
                    key=f"note_{item['id']}",
                    height=80,
                )
                if st.button(t("save_note", lang), key=f"save_note_{item['id']}"):
                    db.update_evidence(item["id"], transcript=manual.strip() or None)
                    clear_run()
                    st.rerun()

            if str(item.get("resource_type")) == "image":
                with st.expander(f"🔗 {t('share', lang)}"):
                    _render_share_controls(item, ctx)

            with st.expander(f"🗑️ {t('delete_evidence', lang)}"):
                confirmed = st.checkbox(
                    t("delete_evidence_confirm", lang), key=f"confirm_del_{item['id']}"
                )
                if st.button(t("delete_evidence", lang), key=f"del_{item['id']}", disabled=not confirmed):
                    delete_evidence(item["id"], storage=ctx.storage)
                    clear_run()
                    st.warning(f"{item['label']} deleted.")
                    st.rerun()


def _render_share_controls(item: dict[str, Any], ctx: UIContext) -> None:
    """Signed expiring link + privacy-safe (blurred) copy for one image."""
    lang = ctx.lang
    options = list(SHARE_OPTIONS)
    default_hours = ctx.settings.share_default_hours if ctx.settings.share_default_hours in options else 24
    hours = st.radio(
        t("share_expiry", lang),
        options=options,
        index=options.index(default_hours),
        format_func=lambda value: SHARE_OPTIONS[value],
        horizontal=True,
        key=f"hours_{item['id']}",
    )
    if st.button(t("create_link", lang), key=f"share_{item['id']}"):
        try:
            url = ctx.storage.signed_url(
                str(item["public_id"]),
                resource_type=str(item.get("resource_type") or "image"),
                expires_in=hours * 3600,
                fmt=str(item.get("format") or "") or None,
            )
        except StorageError as exc:
            st.error(str(exc))
        else:
            db.add_share(
                str(item["case_id"]),
                "asset",
                url,
                _utc_iso(hours),
                evidence_id=str(item["id"]),
                transformations="original",
            )
            st.session_state[f"share_url_{item['id']}"] = url
    stored = st.session_state.get(f"share_url_{item['id']}")
    if stored:
        st.code(stored, language="text")
        st.caption(f"{t('share_expiry', lang)}: {SHARE_OPTIONS[hours]} (server-signed expiry)")

    st.divider()
    st.markdown(f"**🕶️ {t('privacy_copy', lang)}**")
    blur_faces = st.checkbox(t("blur_faces", lang), value=True, key=f"blur_faces_{item['id']}")
    region_text = st.text_input(
        t("blur_region", lang),
        placeholder="e.g. 40, 260, 300, 120",
        key=f"region_{item['id']}",
    )
    if st.button(t("privacy_copy", lang), key=f"redact_{item['id']}"):
        region = parse_region(region_text) if region_text.strip() else None
        if region_text.strip() and region is None:
            st.warning("Use four numbers: x, y, width, height.")
        else:
            try:
                transformation_url = ctx.storage.redacted_url(
                    str(item["public_id"]),
                    expires_in=hours * 3600,
                    blur_faces=blur_faces,
                    region=region,
                )
                copy = ctx.storage.create_redacted_copy(
                    str(item["public_id"]),
                    resource_type=str(item.get("resource_type") or "image"),
                    blur_faces=blur_faces,
                    region=region,
                    fmt=str(item.get("format") or "") or None,
                )
                url = ctx.storage.signed_url(
                    str(copy["public_id"]),
                    resource_type=str(copy.get("resource_type") or "image"),
                    expires_in=hours * 3600,
                    fmt=str(copy.get("format") or "") or None,
                )
            except StorageError as exc:
                st.error(str(exc))
            else:
                db.add_share(
                    str(item["case_id"]),
                    "redacted",
                    url,
                    _utc_iso(hours),
                    evidence_id=str(item["id"]),
                    transformations=str(copy.get("transformation") or "blur_faces"),
                )
                st.success("Share this version instead of the original.")
                st.code(url, language="text")
                st.caption(
                    f"The blurred copy is a separate asset, so this link can expire in "
                    f"{SHARE_OPTIONS[hours]}. Cloudinary transformation used:"
                )
                st.code(str(transformation_url), language="text")
                preview = preview_source(
                    {"public_id": copy["public_id"], "resource_type": "image"}, ctx.storage
                )
                if isinstance(preview, (bytes, str)):
                    st.image(preview, width=260, caption="Redacted copy preview")


def _render_share_list(case_id: str, lang: str) -> None:
    """Audit and revoke share links."""
    shares = db.list_shares(case_id)
    with st.expander(f"🔗 {t('share_list', lang)} ({len(shares)})"):
        if not shares:
            st.caption("No links created yet. Links are the only way anything leaves this app.")
            return
        for share in shares:
            cols = st.columns([2.2, 1.2, 0.8])
            cols[0].markdown(
                f"`{share['kind']}` · {share['transformations'] or 'original'}<br/>"
                f'<span class="saakshya-hash">{str(share["url"])[:90]}…</span>',
                unsafe_allow_html=True,
            )
            cols[1].caption(f"expires in {_remaining(str(share['expires_at']))}")
            if share.get("revoked"):
                cols[2].caption("revoked")
            elif cols[2].button(t("revoke", lang), key=f"revoke_{share['id']}"):
                db.revoke_share(share["id"])
                st.rerun()


# ------------------------------------------------------------- tab 3: timeline
def render_timeline_tab(ctx: UIContext) -> None:
    """Chronological merge of story and evidence with flagged gaps."""
    lang = ctx.lang
    st.subheader(f"🕰️ {t('tab_timeline', lang)}")
    if not _require_case(ctx):
        return
    timeline = ctx.state.get("timeline") or (ctx.case or {}).get("timeline") or []
    gaps = ctx.state.get("timeline_gaps") or (ctx.case or {}).get("timeline_gaps") or []
    if not timeline:
        st.info(t("timeline_empty", lang))
        disclaimer(lang)
        return
    rows = [
        {
            "Date": event.get("date_display") or event.get("date") or "not stated",
            "What happened": event.get("title") or event.get("detail") or "",
            "Source": event.get("evidence_label") or event.get("source") or "story",
        }
        for event in timeline
    ]
    st.dataframe(rows, width="stretch", hide_index=True)
    if gaps:
        st.warning(f"**{t('gaps', lang)}**\n" + "\n".join(f"- {gap}" for gap in gaps))
    disclaimer(lang)


# --------------------------------------------------------------- tab 4: rights
def render_rights_tab(ctx: UIContext) -> None:
    """Search the curated KB; every entry is cited and dated."""
    lang = ctx.lang
    st.subheader(f"⚖️ {t('tab_rights', lang)}")
    st.caption(
        "Plain-language summaries from a small curated knowledge base. Each entry has a source id, "
        "the date it was last reviewed, and a reminder to verify with a lawyer."
    )
    query = st.text_input(
        t("search_rights", lang),
        placeholder="zero FIR · dowry · stalking · POSH · cybercrime.gov.in",
        key="rights_query",
    )
    kb = get_kb()
    entries: list[Any] = []
    if query.strip():
        entries = [hit.entry for hit in kb.search(query, k=5)]
        if not entries:
            st.info("No entry matched that search. Try simpler words like 'FIR' or 'dowry'.")
    else:
        for match in ctx.state.get("legal_matches") or []:
            entry = kb.by_id(str(match.get("kb_id")))
            if entry:
                entries.append(entry)
        if not entries:
            entries = [kb.by_id(kb_id) for kb_id in RIGHTS_FALLBACK_IDS if kb.by_id(kb_id)]
    for entry in entries:
        with st.container(border=True):
            st.markdown(f"**{entry.id} · {entry.title}**")
            st.caption(f"{entry.act}")
            st.markdown(
                pill(t("verify_lawyer", lang), "warn")
                + pill(f"{t('reviewed', lang)}: {entry.last_reviewed}", "neutral"),
                unsafe_allow_html=True,
            )
            st.write(entry.plain_summary)
            for point in entry.key_points:
                st.markdown(f"- {point}")
            st.markdown(
                f'<div class="saakshya-citation">[{entry.id}] {entry.act} — '
                f"{t('reviewed', lang)} {entry.last_reviewed} · {t('verify_lawyer', lang)}</div>",
                unsafe_allow_html=True,
            )
            if entry.sources:
                st.caption(
                    f"{t('sources', lang)}: "
                    + " · ".join(f"{source.get('label')}" for source in entry.sources)
                )
                with st.expander(t("sources", lang)):
                    for source in entry.sources:
                        st.markdown(f"- [{source.get('label')}]({source.get('url')})")
    disclaimer(lang)


# ----------------------------------------------------------------- tab 5: plan
def render_plan_tab(ctx: UIContext) -> None:
    """Prioritised action plan."""
    lang = ctx.lang
    st.subheader(f"🧭 {t('tab_plan', lang)}")
    if not _require_case(ctx):
        return
    steps = sorted(
        ctx.state.get("action_plan") or (ctx.case or {}).get("action_plan") or [],
        key=lambda step: step.get("priority", 99),
    )
    if not steps:
        st.info(t("plan_empty", lang))
        disclaimer(lang)
        return
    risk = str(ctx.state.get("risk_level") or (ctx.case or {}).get("risk_level") or "low")
    if risk == "high":
        st.warning(t("helplines", lang))
    for index, step in enumerate(steps, start=1):
        contact = f" · <b>{step.get('contact')}</b>" if step.get("contact") else ""
        st.markdown(
            f'<div class="saakshya-card"><div class="saakshya-step">'
            f'<div class="saakshya-step-num">{index}</div><div>'
            f"<b>{step.get('title')}</b><br/>{step.get('detail')}"
            f'<div class="saakshya-citation">{contact}</div>'
            f"</div></div></div>",
            unsafe_allow_html=True,
        )
    disclaimer(lang)


# --------------------------------------------------------------- tab 6: draft
def render_draft_tab(ctx: UIContext) -> None:
    """Editable complaint draft with the approval gate."""
    lang = ctx.lang
    st.subheader(f"✍️ {t('tab_draft', lang)}")
    if not _require_case(ctx):
        return
    assert ctx.case is not None
    state = ctx.state
    pending = pending_interrupt(state)
    draft_text = str(
        (pending or {}).get("draft_text")
        or state.get("approved_draft")
        or state.get("draft_text")
        or ctx.case.get("draft_text")
        or ""
    )
    verification = state.get("verification") or {}

    if pending:
        st.info(t("approve_hint", lang))
    if verification:
        if verification.get("passed"):
            st.success(f"✅ {t('verification_ok', lang)}")
        else:
            st.warning(f"⚠️ {t('verification_failed', lang)}: " + "; ".join(verification.get("problems") or []))

    if not draft_text:
        st.info(t("draft_empty", lang))
        disclaimer(lang)
        return

    edited = st.text_area(t("tab_draft", lang), value=draft_text, height=430, key="draft_editor")
    approver = st.text_input(t("approver", lang), key="approver_name")

    col_a, col_b = st.columns([1, 1])
    if col_a.button(f"✅ {t('approve', lang)}", type="primary", key="approve_btn"):
        if not edited.strip():
            st.warning("The draft is empty.")
        else:
            if pending:
                result = _resume_review(ctx, {"approved": True, "draft_text": edited, "approver": approver})
                if result:
                    st.session_state["run"]["state"] = result
            db.save_approval(
                ctx.case["id"],
                edited,
                approver or None,
                "passed" if verification.get("passed") else "flagged",
            )
            st.success(t("approved", lang))
            st.rerun()
    if col_b.button(t("regenerate", lang), key="reject_btn"):
        if pending:
            result = _resume_review(ctx, {"approved": False, "draft_text": edited, "approver": approver})
            if result:
                st.session_state["run"]["state"] = result
        st.warning("Not approved. Edit the text and approve, or re-run the analysis in tab 1.")
        st.rerun()

    if ctx.case.get("human_approved"):
        st.caption(f"{t('approved_by', lang)}: {ctx.case.get('approver') or 'the survivor'}")
    disclaimer(lang)


def _resume_review(ctx: UIContext, decision: dict[str, Any]) -> dict[str, Any] | None:
    """Resume the paused graph with the approval decision."""
    from src.ui.state import run_with_progress

    try:
        return run_with_progress(
            None,
            ctx.run_index,
            ctx.lang,
            resume=decision,
            case_id=str(ctx.case["id"]) if ctx.case else None,
        )
    except Exception as exc:
        st.error(f"Could not resume the review step: {type(exc).__name__}")
        return None


# -------------------------------------------------------------- tab 7: export
def render_export_tab(ctx: UIContext) -> None:
    """Build the PDF evidence packet (approval required) and delete the case."""
    lang = ctx.lang
    st.subheader(f"📦 {t('tab_export', lang)}")
    if not _require_case(ctx):
        return
    assert ctx.case is not None
    case = db.get_case(ctx.case["id"]) or ctx.case
    evidence = db.list_evidence(case["id"])
    counts = db.evidence_counts(case["id"])
    approved = bool(case.get("human_approved"))

    st.markdown(
        pill(f"{len(evidence)} {t('evidence_count', lang)}", "neutral")
        + pill(f"{counts.get('match', 0)} {t('integrity_ok', lang)}", "ok")
        + pill(
            f"{counts.get('unverified', 0)} {t('integrity_unchecked', lang)}",
            "warn" if counts.get("unverified") else "ok",
        ),
        unsafe_allow_html=True,
    )

    if not approved:
        st.warning(t("export_blocked", lang))
        st.markdown(
            "- Add evidence and verify its integrity in tab 2.\n"
            "- Run the analysis in tab 1.\n"
            "- Approve the draft in tab 6."
        )
    else:
        st.success(t("export_ready", lang))
        if st.button(t("build_packet", lang), type="primary", key="build_pdf"):
            with st.status("Building the PDF packet…", expanded=True) as status:
                try:
                    path = build_evidence_packet(
                        case,
                        evidence,
                        case.get("timeline") or ctx.state.get("timeline") or [],
                        case.get("draft_text") or ctx.state.get("approved_draft") or "",
                        case.get("legal_matches") or ctx.state.get("legal_matches") or [],
                        case.get("action_plan") or ctx.state.get("action_plan") or [],
                        storage=ctx.storage,
                    )
                    st.session_state["pdf_bytes"] = path.read_bytes()
                    st.session_state["pdf_name"] = path.name
                    st.write(f"✅ {path.name} · {human_size(path.stat().st_size)}")
                except Exception as exc:
                    st.error(f"PDF build failed: {type(exc).__name__}")
                status.update(label=t("agent_finished", lang), state="complete", expanded=False)
        if st.session_state.get("pdf_bytes"):
            st.download_button(
                f"⬇️ {t('download', lang)}",
                data=st.session_state["pdf_bytes"],
                file_name=st.session_state.get("pdf_name", "saakshya_packet.pdf"),
                mime="application/pdf",
                type="primary",
            )
            st.caption(
                "The packet embeds thumbnails fetched through short-lived signed URLs and notes that "
                "electronic evidence may need a certificate for court."
            )

    with st.expander("🧾 Activity log (metadata only)"):
        events = db.list_events(case["id"])[:12]
        if not events:
            st.caption("No activity recorded yet.")
        for event in events:
            st.caption(
                f"{str(event['created_at'])[:16].replace('T', ' ')} · {event['action']}"
                + (f" · {event['detail']}" if event.get("detail") else "")
            )
        st.caption(
            "Only action names and evidence labels are logged - never your story or the content of a file."
        )

    st.divider()
    with st.expander(f"🗑️ {t('delete_case', lang)}"):
        st.caption(t("delete_case_warning", lang))
        confirm = st.text_input(t("confirm_delete", lang), key="delete_case_confirm")
        if st.button(
            f"🗑️ {t('delete_case', lang)}",
            key="delete_case_btn",
            disabled=confirm.strip().upper() != "DELETE",
        ):
            delete_case(case["id"], storage=ctx.storage)
            for key in ("case_id", "run", "pdf_bytes", "pdf_name"):
                st.session_state.pop(key, None)
            st.success("Case deleted from this device and from Cloudinary.")
            st.rerun()
    disclaimer(lang)
