"""Modern, trustworthy, highly-accessible visual theme for Saakshya.

Guarantees 100% text visibility regardless of browser/OS color scheme,
with an empathetic, state-of-the-art interface tailored for private evidence and legal aid.
"""

from __future__ import annotations

import streamlit as st

PALETTE = {
    "bg": "#F8FAFC",
    "surface": "#FFFFFF",
    "surface_secondary": "#F1F5F9",
    "ink": "#0F172A",
    "ink_secondary": "#334155",
    "muted": "#64748B",
    "line": "#E2E8F0",
    "line_strong": "#CBD5E1",
    "primary": "#4F46E5",
    "primary_hover": "#4338CA",
    "primary_light": "#EEF2FF",
    "accent": "#818CF8",
    "success": "#059669",
    "success_bg": "#ECFDF5",
    "success_border": "#A7F3D0",
    "warn": "#D97706",
    "warn_bg": "#FFFBEB",
    "warn_border": "#FDE68A",
    "danger": "#DC2626",
    "danger_bg": "#FEF2F2",
    "danger_border": "#FECACA",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --saakshya-bg: #F8FAFC;
  --saakshya-surface: #FFFFFF;
  --saakshya-surface-secondary: #F1F5F9;
  --saakshya-card: #FFFFFF;
  --saakshya-ink: #0F172A;
  --saakshya-ink-secondary: #334155;
  --saakshya-muted: #64748B;
  --saakshya-line: #E2E8F0;
  --saakshya-line-strong: #CBD5E1;
  --saakshya-primary: #4F46E5;
  --saakshya-primary-hover: #4338CA;
  --saakshya-primary-light: #EEF2FF;
  --saakshya-accent: #818CF8;
  --saakshya-success: #059669;
  --saakshya-success-bg: #ECFDF5;
  --saakshya-success-border: #A7F3D0;
  --saakshya-warn: #D97706;
  --saakshya-warn-bg: #FFFBEB;
  --saakshya-warn-border: #FDE68A;
  --saakshya-danger: #DC2626;
  --saakshya-danger-bg: #FEF2F2;
  --saakshya-danger-border: #FECACA;
  --saakshya-shadow-sm: 0 1px 3px 0 rgba(15, 23, 42, 0.06);
  --saakshya-shadow-md: 0 4px 8px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.04);
  --saakshya-shadow-lg: 0 12px 24px -4px rgba(79, 70, 229, 0.1), 0 4px 8px -2px rgba(15, 23, 42, 0.04);
  --saakshya-font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --saakshya-font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}

/* Base App Canvas */
html, body, [data-testid="stAppViewContainer"], .stApp {
  background-color: var(--saakshya-bg) !important;
  color: var(--saakshya-ink) !important;
  font-family: var(--saakshya-font-sans) !important;
}

/* Header Bar - seamless glass instead of dark strip */
[data-testid="stHeader"] {
  background: rgba(248, 250, 252, 0.9) !important;
  backdrop-filter: blur(12px) !important;
  -webkit-backdrop-filter: blur(12px) !important;
  border-bottom: 1px solid var(--saakshya-line) !important;
  color: var(--saakshya-ink) !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #F8FAFC 0%, #EEF2F6 100%) !important;
  border-right: 1px solid var(--saakshya-line) !important;
  box-shadow: 2px 0 12px rgba(0, 0, 0, 0.02) !important;
}
[data-testid="stSidebar"] * {
  color: var(--saakshya-ink);
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  color: var(--saakshya-primary) !important;
  font-weight: 700 !important;
  letter-spacing: -0.02em !important;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
  color: var(--saakshya-muted) !important;
  font-size: 0.85rem !important;
}

/* Headings & Text Legibility */
h1, h2, h3, h4, h5, h6 {
  color: var(--saakshya-ink) !important;
  font-family: var(--saakshya-font-sans) !important;
  font-weight: 700 !important;
  letter-spacing: -0.02em !important;
}
p, span, div, li {
  color: var(--saakshya-ink-secondary);
  font-family: var(--saakshya-font-sans);
}

/* Streamlit Markdown Container */
.stMarkdown p {
  color: var(--saakshya-ink-secondary) !important;
  line-height: 1.6 !important;
}
.stMarkdown strong {
  color: var(--saakshya-ink) !important;
  font-weight: 600 !important;
}

/* Form Labels & Captions - Absolute Visibility Guarantee */
label,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] label,
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] span {
  color: var(--saakshya-ink) !important;
  font-weight: 600 !important;
  font-size: 0.93rem !important;
  font-family: var(--saakshya-font-sans) !important;
  margin-bottom: 6px !important;
  display: block !important;
}

[data-testid="stCaptionContainer"] p {
  color: var(--saakshya-muted) !important;
  font-size: 0.84rem !important;
}

/* Inputs, Textareas & Form Controls */
input[type="text"],
input[type="password"],
textarea,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea {
  background-color: #FFFFFF !important;
  color: var(--saakshya-ink) !important;
  border: 1.5px solid var(--saakshya-line-strong) !important;
  border-radius: 10px !important;
  font-family: var(--saakshya-font-sans) !important;
  font-size: 0.95rem !important;
  padding: 10px 14px !important;
  transition: all 0.2s ease !important;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.03) !important;
}

input[type="text"]:focus,
input[type="password"]:focus,
textarea:focus,
[data-baseweb="input"]:focus-within,
[data-baseweb="textarea"]:focus-within {
  border-color: var(--saakshya-primary) !important;
  background-color: #FFFFFF !important;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15), inset 0 1px 2px rgba(0, 0, 0, 0.03) !important;
  outline: none !important;
}

input::placeholder,
textarea::placeholder {
  color: var(--saakshya-muted) !important;
  opacity: 0.75 !important;
}

/* Selectboxes & Dropdowns */
[data-baseweb="select"] > div {
  background-color: #FFFFFF !important;
  color: var(--saakshya-ink) !important;
  border: 1.5px solid var(--saakshya-line-strong) !important;
  border-radius: 10px !important;
  font-family: var(--saakshya-font-sans) !important;
  min-height: 42px !important;
}
[data-baseweb="select"] * {
  color: var(--saakshya-ink) !important;
}
[data-baseweb="popover"],
[data-baseweb="menu"],
[data-baseweb="menu"] * {
  background-color: #FFFFFF !important;
  color: var(--saakshya-ink) !important;
  font-family: var(--saakshya-font-sans) !important;
}
li[role="option"] {
  padding: 10px 14px !important;
  transition: background 0.15s ease !important;
}
li[role="option"]:hover,
li[aria-selected="true"] {
  background-color: var(--saakshya-primary-light) !important;
  color: var(--saakshya-primary) !important;
  font-weight: 600 !important;
}

/* Segmented Modern Tab Bar - 100% High Contrast */
[data-baseweb="tab-list"] {
  background-color: #E2E8F0 !important;
  padding: 5px !important;
  border-radius: 12px !important;
  gap: 4px !important;
  border: none !important;
  margin-bottom: 22px !important;
  box-shadow: inset 0 1px 3px rgba(15, 23, 42, 0.08) !important;
  display: flex !important;
  flex-wrap: wrap !important;
}

[data-baseweb="tab"] {
  background-color: transparent !important;
  color: #475569 !important;
  border-radius: 8px !important;
  padding: 9px 18px !important;
  font-weight: 600 !important;
  font-size: 0.90rem !important;
  border: none !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
  cursor: pointer !important;
}

[data-baseweb="tab"]:hover {
  color: var(--saakshya-ink) !important;
  background-color: rgba(255, 255, 255, 0.65) !important;
}

[data-baseweb="tab"][aria-selected="true"] {
  background-color: #FFFFFF !important;
  color: var(--saakshya-primary) !important;
  font-weight: 700 !important;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.08), 0 1px 2px rgba(15, 23, 42, 0.04) !important;
  border-bottom: none !important;
}

[data-baseweb="tab-highlight"],
[data-baseweb="tab-border"] {
  display: none !important;
}

/* Radio Buttons */
[data-testid="stRadio"] label {
  color: var(--saakshya-ink) !important;
  font-weight: 500 !important;
  font-size: 0.93rem !important;
  cursor: pointer !important;
}
[data-testid="stRadio"] label span {
  color: var(--saakshya-ink) !important;
}
[data-testid="stRadio"] div[role="radiogroup"] {
  gap: 20px !important;
  padding: 6px 0 !important;
}

/* Checkboxes & Toggles */
[data-testid="stCheckbox"] label,
[data-testid="stToggle"] label {
  color: var(--saakshya-ink) !important;
  font-weight: 500 !important;
  font-size: 0.92rem !important;
  cursor: pointer !important;
}
[data-testid="stCheckbox"] label span,
[data-testid="stToggle"] label span {
  color: var(--saakshya-ink) !important;
}

/* Buttons */
button[kind="primary"],
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #4F46E5 0%, #4338CA 100%) !important;
  color: #FFFFFF !important;
  border: none !important;
  border-radius: 10px !important;
  font-weight: 600 !important;
  font-size: 0.93rem !important;
  padding: 10px 22px !important;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25) !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

button[kind="primary"]:hover,
.stButton > button[kind="primary"]:hover {
  background: linear-gradient(135deg, #4338CA 0%, #3730A3 100%) !important;
  box-shadow: 0 6px 18px rgba(79, 70, 229, 0.35) !important;
  transform: translateY(-1px) !important;
  color: #FFFFFF !important;
}

button[kind="secondary"],
.stButton > button[kind="secondary"] {
  background: #FFFFFF !important;
  color: var(--saakshya-ink) !important;
  border: 1.5px solid var(--saakshya-line-strong) !important;
  border-radius: 10px !important;
  font-weight: 600 !important;
  font-size: 0.93rem !important;
  padding: 9px 20px !important;
  box-shadow: var(--saakshya-shadow-sm) !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

button[kind="secondary"]:hover,
.stButton > button[kind="secondary"]:hover {
  background: #F8FAFC !important;
  border-color: var(--saakshya-muted) !important;
  color: var(--saakshya-ink) !important;
  transform: translateY(-1px) !important;
}

/* Quick Exit Button (Sidebar Emergency Safety) */
.saakshya-quick-exit button {
  background: linear-gradient(135deg, #EF4444 0%, #DC2626 100%) !important;
  color: #FFFFFF !important;
  font-weight: 700 !important;
  border: none !important;
  border-radius: 10px !important;
  box-shadow: 0 4px 12px rgba(220, 38, 38, 0.25) !important;
}
.saakshya-quick-exit button:hover {
  background: linear-gradient(135deg, #DC2626 0%, #B91C1C 100%) !important;
  box-shadow: 0 6px 16px rgba(220, 38, 38, 0.35) !important;
  transform: translateY(-1px) !important;
}

/* Expanders */
[data-testid="stExpander"] {
  background: #FFFFFF !important;
  border: 1px solid var(--saakshya-line) !important;
  border-radius: 12px !important;
  box-shadow: var(--saakshya-shadow-sm) !important;
  margin-bottom: 14px !important;
  transition: all 0.2s ease !important;
  overflow: hidden !important;
}
[data-testid="stExpander"]:hover {
  border-color: var(--saakshya-line-strong) !important;
  box-shadow: var(--saakshya-shadow-md) !important;
}
[data-testid="stExpander"] summary {
  padding: 14px 18px !important;
  font-weight: 600 !important;
  color: var(--saakshya-ink) !important;
  border-radius: 12px !important;
}
[data-testid="stExpander"] summary:hover {
  background-color: #F8FAFC !important;
  color: var(--saakshya-primary) !important;
}
[data-testid="stExpander"] summary svg {
  fill: var(--saakshya-primary) !important;
}
[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
  padding: 18px 22px !important;
  border-top: 1px solid var(--saakshya-line) !important;
  background: #FFFFFF !important;
  color: var(--saakshya-ink-secondary) !important;
}

/* Containers with Border (Cards) */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: #FFFFFF !important;
  border: 1px solid var(--saakshya-line) !important;
  border-radius: 16px !important;
  box-shadow: var(--saakshya-shadow-sm) !important;
  padding: 6px !important;
  margin-bottom: 16px !important;
}

/* Metrics Cards */
[data-testid="stMetric"] {
  background: #FFFFFF !important;
  padding: 18px 22px !important;
  border-radius: 14px !important;
  border: 1px solid var(--saakshya-line) !important;
  box-shadow: var(--saakshya-shadow-sm) !important;
}
[data-testid="stMetricLabel"] p {
  color: var(--saakshya-muted) !important;
  font-weight: 600 !important;
  font-size: 0.82rem !important;
  letter-spacing: 0.04em !important;
  text-transform: uppercase !important;
}
[data-testid="stMetricValue"] div {
  color: var(--saakshya-ink) !important;
  font-weight: 800 !important;
  font-size: 1.9rem !important;
}

/* Dataframe styling */
[data-testid="stDataFrame"] {
  border: 1px solid var(--saakshya-line) !important;
  border-radius: 12px !important;
  overflow: hidden !important;
  box-shadow: var(--saakshya-shadow-sm) !important;
}

/* Alerts and Banners */
[data-testid="stAlert"] {
  border-radius: 12px !important;
  font-family: var(--saakshya-font-sans) !important;
  padding: 14px 18px !important;
}

/* Custom Saakshya UI Components */
.saakshya-hero {
  background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 50%, #EEF2FF 100%);
  border: 1px solid var(--saakshya-line);
  border-radius: 18px;
  padding: 26px 32px;
  margin-bottom: 24px;
  box-shadow: var(--saakshya-shadow-md);
  position: relative;
  overflow: hidden;
}
.saakshya-hero::after {
  content: "";
  position: absolute;
  top: 0;
  right: 0;
  width: 280px;
  height: 100%;
  background: radial-gradient(circle at 100% 0%, rgba(99, 102, 241, 0.12) 0%, transparent 70%);
  pointer-events: none;
}
.saakshya-hero-title {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 2.1rem;
  font-weight: 800;
  color: var(--saakshya-ink);
  letter-spacing: -0.03em;
  margin-bottom: 6px;
}
.saakshya-hero-tagline {
  font-size: 1.05rem;
  color: var(--saakshya-muted);
  margin-bottom: 16px;
  font-weight: 500;
}
.saakshya-hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.saakshya-card {
  background: var(--saakshya-card);
  border: 1px solid var(--saakshya-line);
  border-radius: 14px;
  padding: 18px 20px;
  margin-bottom: 14px;
  box-shadow: var(--saakshya-shadow-sm);
  transition: all 0.2s ease;
}
.saakshya-card:hover {
  border-color: var(--saakshya-line-strong);
  box-shadow: var(--saakshya-shadow-md);
}

.saakshya-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 9999px;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  margin-right: 8px;
  margin-bottom: 6px;
  line-height: 1.3;
}
.saakshya-pill-ok {
  background: var(--saakshya-success-bg);
  color: var(--saakshya-success);
  border: 1px solid var(--saakshya-success-border);
}
.saakshya-pill-bad {
  background: var(--saakshya-danger-bg);
  color: var(--saakshya-danger);
  border: 1px solid var(--saakshya-danger-border);
}
.saakshya-pill-warn {
  background: var(--saakshya-warn-bg);
  color: var(--saakshya-warn);
  border: 1px solid var(--saakshya-warn-border);
}
.saakshya-pill-neutral {
  background: var(--saakshya-surface-secondary);
  color: var(--saakshya-ink-secondary);
  border: 1px solid var(--saakshya-line);
}
.saakshya-pill-brand {
  background: var(--saakshya-primary-light);
  color: var(--saakshya-primary);
  border: 1px solid #C7D2FE;
}

.saakshya-step {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 12px 0;
  border-bottom: 1px solid var(--saakshya-line);
}
.saakshya-step:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.saakshya-step-num {
  min-width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4F46E5 0%, #4338CA 100%);
  color: #FFFFFF;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  font-weight: 700;
  box-shadow: 0 2px 6px rgba(79, 70, 229, 0.3);
  flex-shrink: 0;
}

.saakshya-hash {
  font-family: var(--saakshya-font-mono);
  font-size: 0.74rem;
  word-break: break-all;
  background: #F1F5F9;
  color: #334155;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid #E2E8F0;
  display: inline-block;
  margin: 4px 0;
}

.saakshya-citation {
  font-size: 0.82rem;
  color: var(--saakshya-muted);
  margin-top: 6px;
  line-height: 1.4;
}

.saakshya-disclaimer {
  font-size: 0.82rem;
  color: var(--saakshya-muted);
  border-top: 1px dashed var(--saakshya-line);
  padding-top: 12px;
  margin-top: 24px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.saakshya-node {
  font-family: var(--saakshya-font-mono);
  font-size: 0.82rem;
  padding: 5px 0;
  color: var(--saakshya-muted);
  display: flex;
  align-items: center;
  gap: 8px;
}
.saakshya-node-done {
  color: var(--saakshya-success);
  font-weight: 600;
}
.saakshya-node-active {
  color: var(--saakshya-primary);
  font-weight: 700;
  background: var(--saakshya-primary-light);
  padding: 4px 8px;
  border-radius: 6px;
}

.saakshya-safety-box {
  background: linear-gradient(135deg, #FEF2F2 0%, #FFF1F2 100%);
  border: 1.5px solid var(--saakshya-danger-border);
  border-radius: 14px;
  padding: 18px 22px;
  margin-bottom: 20px;
  box-shadow: 0 4px 12px rgba(220, 38, 38, 0.08);
}
.saakshya-safety-title {
  color: var(--saakshya-danger);
  font-weight: 800;
  font-size: 1.15rem;
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.saakshya-safety-lines {
  color: #7F1D1D;
  font-size: 0.93rem;
  line-height: 1.5;
  margin-bottom: 12px;
}
.saakshya-helplines {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(220, 38, 38, 0.2);
}
.saakshya-helpline-chip {
  background: #FFFFFF;
  border: 1px solid var(--saakshya-danger-border);
  color: var(--saakshya-danger);
  font-weight: 700;
  font-size: 0.82rem;
  padding: 4px 10px;
  border-radius: 8px;
}

.saakshya-sidebar-header {
  padding-bottom: 14px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--saakshya-line);
}
.saakshya-sidebar-logo {
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--saakshya-primary);
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}
</style>
"""


def inject_css() -> None:
    """Inject the theme once per page render (cheap and idempotent)."""
    st.markdown(CSS, unsafe_allow_html=True)
