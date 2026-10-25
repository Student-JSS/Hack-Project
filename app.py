"""Saakshya - private evidence vault and rights navigator.

Run with::

    streamlit run app.py

Everything sensitive lives in SQLite + Cloudinary; the streamlit session only
holds the id of the current case and the latest pipeline result.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Saakshya - evidence vault and rights navigator",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src import db  # noqa: E402  (imported after set_page_config by design)
from src.cloudinary_client import get_storage, storage_status  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.graph.state import empty_state  # noqa: E402
from src.i18n import LANGUAGES, t  # noqa: E402
from src.ingest import delete_case  # noqa: E402
from src.samples import create_demo_case  # noqa: E402
from src.ui.components import (  # noqa: E402
    demo_banner,
    disclaimer,
    pin_controls,
    pin_gate,
    quick_exit,
    safety_banner,
    storage_badge,
)
from src.ui.state import (  # noqa: E402
    app_status,
    build_initial_state,
    current_run,
    next_run_index,
    run_with_progress,
    store_run,
)
from src.ui.styles import inject_css  # noqa: E402
from src.ui.tabs import (  # noqa: E402
    UIContext,
    render_case_tab,
    render_draft_tab,
    render_export_tab,
    render_plan_tab,
    render_rights_tab,
    render_timeline_tab,
    render_vault_tab,
)


def _init() -> None:
    """One-time setup: settings, database, session defaults."""
    settings = get_settings()
    db.init_db()
    inject_css()
    st.session_state.setdefault("language", "en")
    st.session_state.setdefault("demo_mode", settings.demo_mode)


def _consent_gate(lang: str) -> None:
    """First-run consent notice (stored as a flag, no personal data)."""
    if db.get_setting("consent_accepted") == "1" or st.session_state.get("consent_ok"):
        return
    st.markdown(
        f"""
        <div class="saakshya-hero" style="max-width: 760px; margin: 30px auto 20px auto;">
            <div class="saakshya-hero-title">
                <span>🛡️</span>
                <span>{t('app_title', lang)} · <span style="font-weight: 500; font-size: 1.6rem; color: #4F46E5;">साक्ष्य</span></span>
            </div>
            <div class="saakshya-hero-tagline">{t('app_tagline', lang)}</div>
            <div style="background: #FFFFFF; border-radius: 14px; padding: 22px 24px; border: 1px solid #E2E8F0; margin-top: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                <h3 style="margin-top: 0; font-size: 1.25rem; color: #0F172A;">{t('consent_title', lang)}</h3>
                <p style="color: #334155; line-height: 1.6; font-size: 0.95rem;">{t('consent_body', lang)}</p>
                <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px;">
                    <span class="saakshya-pill saakshya-pill-brand">🔒 100% Device-Local</span>
                    <span class="saakshya-pill saakshya-pill-ok">🛡️ No Cloud Sharing Without Link</span>
                    <span class="saakshya-pill saakshya-pill-neutral">🗑️ Instant Complete Erasure</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 4, 1])
    with col2:
        agreed = st.checkbox(t("consent_checkbox", lang), key="consent_checkbox")
        if st.button(t("consent_continue", lang), type="primary", disabled=not agreed, width="stretch"):
            db.set_setting("consent_accepted", "1")
            st.session_state["consent_ok"] = True
            st.rerun()
        st.caption(f"⚖️ {t('disclaimer', lang)}")
    st.stop()


def _sidebar(lang: str, settings) -> str:
    """Language, safety controls, demo mode, case picker and status."""
    with st.sidebar:
        st.markdown(
            f"""
            <div class="saakshya-sidebar-header">
                <div class="saakshya-sidebar-logo">🛡️ {t('app_title', lang)}</div>
                <div style="font-size: 0.84rem; color: #64748B; font-weight: 500; line-height: 1.4;">
                    {t('app_tagline', lang)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        chosen_language = st.selectbox(
            f"🌐 {t('language', lang)}",
            options=list(LANGUAGES),
            format_func=lambda code: LANGUAGES[code],
            index=list(LANGUAGES).index(lang),
            key="language_selector",
        )
        if chosen_language != lang:
            st.session_state["language"] = chosen_language
            st.rerun()
        lang = chosen_language

        quick_exit(lang)
        st.divider()

        with st.expander("🚨 Emergency Helplines (24/7)", expanded=False):
            st.markdown(
                """
                <div style="font-size: 0.86rem; line-height: 1.8; color: #0F172A;">
                    <strong>🚨 Police:</strong> <span style="color:#DC2626; font-weight:700;">112</span><br/>
                    <strong>👩 Women Helpline:</strong> <span style="color:#4F46E5; font-weight:700;">181</span><br/>
                    <strong>👮 Women in Distress:</strong> <span style="color:#4F46E5; font-weight:700;">1091</span><br/>
                    <strong>💻 Cyber Crime:</strong> <span style="color:#059669; font-weight:700;">1930</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        demo = st.toggle(
            t("demo_mode", lang),
            value=bool(st.session_state.get("demo_mode", settings.demo_mode)),
            help="Loads synthetic screenshots and a sample story to test all features with demo data.",
        )
        st.session_state["demo_mode"] = demo

        if st.button(f"🧪 {t('load_demo', lang)}", width="stretch"):
            with st.spinner("Creating a synthetic case…"):
                case = create_demo_case()
            st.session_state["case_id"] = case["id"]
            st.session_state["pending_run"] = True
            st.session_state["run"] = None
            st.rerun()

        st.divider()
        cases = db.list_cases()
        if cases:
            options = [case["id"] for case in cases]
            labels = {
                case["id"]: f"{case['title'][:34]}" + (" · demo" if case.get("is_demo") else "")
                for case in cases
            }
            current = st.session_state.get("case_id")
            index = options.index(current) if current in options else 0
            selected = st.selectbox(
                f"📁 {t('select_case', lang)}",
                options=options,
                index=index,
                format_func=lambda case_id: labels.get(case_id, case_id),
                key="case_selector",
            )
            if selected != current:
                st.session_state["case_id"] = selected
                st.session_state["pdf_bytes"] = None
                st.rerun()
        else:
            st.caption(f"📁 {t('no_case_selected', lang)}")

        pin_controls(lang)

        with st.expander("⚙️ Status"):
            status = app_status(lang)
            st.markdown(
                f"**{t('status_llm', lang)}:** `{status['llm']}`  \n"
                f"**{t('status_storage', lang)}:** {storage_badge(get_storage(), lang)}  \n"
                f"OCR: `{status['ocr']}`  \n{t('mock_badge', lang) if settings.use_mock_cloudinary else ''}",
                unsafe_allow_html=True,
            )
            if not settings.llm_ready:
                st.caption("No LLM key: the pipeline is using deterministic templates.")
            if not settings.cloudinary_configured and not settings.use_mock_cloudinary:
                st.warning(
                    "Cloudinary is not configured, so evidence is stored in the offline mock folder. "
                    "Add CLOUDINARY_URL to .env for real private uploads."
                )
            st.caption(storage_status()["root"])

        with st.expander(f"⚠️ {t('delete_everything', lang)}"):
            st.caption(t("delete_everything_help", lang))
            confirm = st.text_input(t("confirm_delete", lang), key="delete_all_confirm")
            if st.button(
                f"🗑️ {t('delete_everything', lang)}",
                key="delete_all_btn",
                disabled=confirm.strip().upper() != "DELETE",
            ):
                for case in db.list_cases():
                    delete_case(case["id"], storage=get_storage())
                db.delete_everything()
                st.session_state.clear()
                st.rerun()

        st.divider()
        st.caption(f"⚖️ {t('disclaimer', lang)}")
    return lang


def main() -> None:
    """Render the whole app."""
    _init()
    settings = get_settings()
    lang = str(st.session_state.get("language", "en"))
    _consent_gate(lang)
    lang = _sidebar(lang, settings)
    pin_gate()

    case_id = st.session_state.get("case_id")
    case = db.get_case(case_id) if case_id else None
    if case is None and case_id:
        st.session_state.pop("case_id", None)

    if case and st.session_state.pop("pending_run", False):
        run_index = next_run_index(case["id"])
        with st.spinner("Preparing your case…"):
            state = build_initial_state(case)
            result = run_with_progress(state, run_index, lang)
            store_run(case["id"], run_index, result)
        st.rerun()

    run = current_run(case["id"]) if case else {"case_id": "", "run_index": 0, "state": empty_state()}
    state = run.get("state") or empty_state()
    ctx = UIContext(
        lang=lang,
        case=db.get_case(case["id"]) if case else None,
        state=state,
        run_index=int(run.get("run_index", 0)),
        settings=settings,
        storage=get_storage(),
    )

    st.markdown(
        f"""
        <div class="saakshya-hero">
            <div class="saakshya-hero-title">
                <span style="display:inline-block; filter: drop-shadow(0 2px 8px rgba(79, 70, 229, 0.25));">🛡️</span>
                <span>{t('app_title', lang)} · <span style="font-weight: 500; font-size: 1.6rem; color: #4F46E5;">साक्ष्य</span></span>
            </div>
            <div class="saakshya-hero-tagline">{t('app_tagline', lang)}</div>
            <div class="saakshya-hero-badges">
                <span class="saakshya-pill saakshya-pill-brand">🔒 100% Client-Side Privacy</span>
                <span class="saakshya-pill saakshya-pill-ok">🛡️ SHA-256 Verifiable Vault</span>
                <span class="saakshya-pill saakshya-pill-neutral">⚖️ Curated Legal Frameworks</span>
                <span class="saakshya-pill saakshya-pill-warn">⏱️ Expiring Signed Links</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.get("demo_mode") or (ctx.case or {}).get("is_demo"):
        demo_banner(lang)
    safety_banner(state, lang)

    tab_case, tab_vault, tab_timeline, tab_rights, tab_plan, tab_draft, tab_export = st.tabs(
        [
            t("tab_case", lang),
            t("tab_vault", lang),
            t("tab_timeline", lang),
            t("tab_rights", lang),
            t("tab_plan", lang),
            t("tab_draft", lang),
            t("tab_export", lang),
        ]
    )
    with tab_case:
        render_case_tab(ctx)
    with tab_vault:
        render_vault_tab(ctx)
    with tab_timeline:
        render_timeline_tab(ctx)
    with tab_rights:
        render_rights_tab(ctx)
    with tab_plan:
        render_plan_tab(ctx)
    with tab_draft:
        render_draft_tab(ctx)
    with tab_export:
        render_export_tab(ctx)

    disclaimer(lang)


if __name__ == "__main__":
    main()
