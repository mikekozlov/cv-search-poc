from __future__ import annotations

from contextlib import contextmanager
import html
from typing import Iterator

import streamlit as st

_THEME_CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&family=Space+Grotesk:wght@500;600;700&display=swap");

:root {
  --tt-bg: #f3f6fb;
  --tt-bg-strong: #e9edf6;
  --tt-card-bg: #ffffff;
  --tt-card-border: #e1e7f2;
  --tt-shadow: rgba(24, 38, 68, 0.08);
  --tt-shadow-strong: rgba(24, 38, 68, 0.12);
  --tt-accent: #2b6fe6;
  --tt-accent-strong: #1f58c6;
  --tt-accent-soft: #e7f0ff;
  --tt-text: #1f2a44;
  --tt-muted: #6a7b95;
  --tt-chip-bg: #eef2f9;
  --tt-chip-border: #d6deed;
  --tt-nav-bg: #0f2e5a;
  --tt-nav-text: #dbe6f7;
  --tt-nav-active: #ffffff;
  --tt-nav-pill: rgba(255, 255, 255, 0.14);
}

html, body, .stApp {
  font-family: "IBM Plex Sans", sans-serif;
  color: var(--tt-text);
  background: linear-gradient(180deg, #ffffff 0%, var(--tt-bg) 40%, var(--tt-bg-strong) 100%);
}

.stApp {
  background-attachment: fixed;
}

h1, h2, h3, h4, h5, h6 {
  font-family: "Space Grotesk", sans-serif;
  letter-spacing: 0.2px;
}

.block-container {
  padding-top: 1.4rem;
  padding-bottom: 3rem;
  max-width: min(96vw, 1680px);
  padding-left: 15px;
  padding-right: 2rem;
}

footer {
  visibility: hidden;
  height: 0;
}

header[data-testid="stHeader"] {
  background: transparent;
  box-shadow: none;
}

section[data-testid="stSidebar"] {
  background: var(--tt-nav-bg);
  border-right: 0;
  width: 200px;
}

section[data-testid="stSidebar"] > div {
  width: 200px;
}

section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] a {
  color: var(--tt-nav-text);
}

section[data-testid="stSidebar"] [data-testid="stNavSection"] a {
  border-radius: 12px;
  padding: 0.4rem 0.6rem;
  margin-bottom: 0.25rem;
  display: block;
}

section[data-testid="stSidebar"] [data-testid="stNavSection"] a:hover {
  background: var(--tt-nav-pill);
  color: var(--tt-nav-active);
}

section[data-testid="stSidebar"] button[title="Collapse sidebar"],
section[data-testid="stSidebar"] button[aria-label="Collapse sidebar"],
section[data-testid="stSidebar"] button[title="Close sidebar"],
section[data-testid="stSidebar"] button[aria-label="Close sidebar"],
header[data-testid="stHeader"] button[title="Expand sidebar"],
header[data-testid="stHeader"] button[aria-label="Expand sidebar"],
header[data-testid="stHeader"] button[title="Open sidebar"],
header[data-testid="stHeader"] button[aria-label="Open sidebar"] {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

section[data-testid="stSidebar"] button[title="Collapse sidebar"],
section[data-testid="stSidebar"] button[aria-label="Collapse sidebar"],
section[data-testid="stSidebar"] button[title="Close sidebar"],
section[data-testid="stSidebar"] button[aria-label="Close sidebar"] {
  color: var(--tt-nav-text);
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 10px;
}

header[data-testid="stHeader"] button[title="Expand sidebar"],
header[data-testid="stHeader"] button[aria-label="Expand sidebar"],
header[data-testid="stHeader"] button[title="Open sidebar"],
header[data-testid="stHeader"] button[aria-label="Open sidebar"] {
  color: var(--tt-nav-text);
  background: var(--tt-nav-bg);
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 10px;
  box-shadow: 0 10px 20px rgba(15, 46, 90, 0.25);
}

section[data-testid="stSidebar"] button[title="Collapse sidebar"]:hover,
section[data-testid="stSidebar"] button[aria-label="Collapse sidebar"]:hover,
section[data-testid="stSidebar"] button[title="Close sidebar"]:hover,
section[data-testid="stSidebar"] button[aria-label="Close sidebar"]:hover,
header[data-testid="stHeader"] button[title="Expand sidebar"]:hover,
header[data-testid="stHeader"] button[aria-label="Expand sidebar"]:hover,
header[data-testid="stHeader"] button[title="Open sidebar"]:hover,
header[data-testid="stHeader"] button[aria-label="Open sidebar"]:hover {
  transform: translateY(-1px);
}

.tt-header {
  margin-bottom: 1.25rem;
}

.tt-title {
  font-size: 2rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.tt-subtitle {
  color: var(--tt-muted);
  font-size: 1rem;
}

.tt-card {
  background: var(--tt-card-bg);
  border: 1px solid var(--tt-card-border);
  border-radius: 20px;
  box-shadow: 0 16px 28px var(--tt-shadow);
  padding: 24px;
  margin-bottom: 16px;
  animation: tt-fade-up 0.6s ease both;
}

.tt-card--tall {
  min-height: 0;
}

.tt-empty-state {
  border: 1px dashed var(--tt-card-border);
  border-radius: 16px;
  padding: 24px;
  background: #f9fbff;
  text-align: center;
  color: var(--tt-muted);
}

.tt-empty-state strong {
  display: block;
  color: var(--tt-text);
  font-size: 1.05rem;
  margin-bottom: 0.35rem;
}

.tt-card .stMarkdown p {
  color: var(--tt-muted);
}

.tt-section {
  margin-top: 18px;
}

@keyframes tt-fade-up {
  0% { opacity: 0; transform: translateY(10px); }
  100% { opacity: 1; transform: translateY(0); }
}

.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button {
  border-radius: 999px;
  border: 1px solid var(--tt-accent);
  background: var(--tt-accent);
  color: #ffffff;
  font-weight: 600;
  padding: 0.55rem 1.35rem;
  transition: all 0.2s ease;
  white-space: normal;
  word-break: break-word;
  text-align: center;
  line-height: 1.2;
  box-shadow: 0 8px 18px rgba(43, 111, 230, 0.25);
}

.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {
  background: var(--tt-accent-strong);
  border-color: var(--tt-accent-strong);
  color: #ffffff;
}

.stButton > button:disabled,
.stDownloadButton > button:disabled,
.stFormSubmitButton > button:disabled {
  background: var(--tt-accent-soft);
  border-color: var(--tt-accent-soft);
  color: var(--tt-muted);
  box-shadow: none;
}

/* Searching button state - animated gradient */
.stButton > button.searching-btn,
.stButton > button:disabled[data-searching="true"] {
  background: linear-gradient(90deg, #10b981, #34d399, #6ee7b7, #34d399, #10b981);
  background-size: 200% 100%;
  animation: tt-searching-pulse 1.5s ease-in-out infinite;
  border-color: #10b981;
  color: #ffffff !important;
  box-shadow: 0 8px 20px rgba(16, 185, 129, 0.35);
}

@keyframes tt-searching-pulse {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

div[data-baseweb="input"],
div[data-baseweb="textarea"],
div[data-baseweb="select"] {
  background: #f9fbff;
  border-radius: 12px;
  border: 1px solid var(--tt-card-border);
  box-shadow: none;
}

div[data-baseweb="input"]:focus-within,
div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"]:focus-within {
  border-color: var(--tt-accent);
  box-shadow: 0 0 0 2px rgba(41, 121, 255, 0.15);
}

div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea {
  font-family: "IBM Plex Sans", sans-serif;
  color: var(--tt-text);
}

/* Textarea with better contrast */
div[data-baseweb="textarea"] {
  background: #ffffff !important;
  border: 1.5px solid #c4cfe0 !important;
}

div[data-baseweb="textarea"]:focus-within {
  border-color: var(--tt-accent) !important;
  box-shadow: 0 0 0 3px rgba(43, 111, 230, 0.15) !important;
}

/* Placeholder text with better visibility */
div[data-baseweb="textarea"] textarea::placeholder,
div[data-baseweb="input"] input::placeholder {
  color: #6a7b95 !important;
  opacity: 1 !important;
}

/* Force label colors for all Streamlit widgets to prevent dark-mode override */
.stTextInput label,
.stSelectbox label,
.stMultiSelect label,
.stSlider label,
.stRadio label,
.stCheckbox label,
.stNumberInput label,
.stTextArea label,
.stDateInput label,
.stTimeInput label,
.stFileUploader label,
[data-testid="stWidgetLabel"],
[data-testid="stMarkdownContainer"] p,
.stRadio > label,
.stCheckbox > label,
.stSlider > label > div,
div[data-testid="stSliderTickBarMin"],
div[data-testid="stSliderTickBarMax"] {
  color: var(--tt-text) !important;
}

/* Radio and checkbox option labels */
.stRadio [role="radiogroup"] label,
.stCheckbox span {
  color: var(--tt-text) !important;
}

/* Help text / captions */
.stCaption,
[data-testid="stCaptionContainer"],
small {
  color: var(--tt-muted) !important;
}

/* Expander summary text */
details[data-testid="stExpander"] summary,
details[data-testid="stExpander"] summary span {
  color: var(--tt-text) !important;
}

/* Tabs text */
div[data-baseweb="tab-list"] button,
div[data-baseweb="tab"] {
  color: var(--tt-text) !important;
}

/* General paragraph and span text in main content */
.stApp p,
.stApp span:not([data-testid="stHeaderNoPadding"] span):not(section[data-testid="stSidebar"] span) {
  color: var(--tt-text);
}

div[data-baseweb="select"] > div {
  background: transparent;
}

.stSlider [data-baseweb="slider"] > div {
  color: var(--tt-accent);
}

details[data-testid="stExpander"] {
  background: var(--tt-card-bg);
  border: 1px solid var(--tt-card-border);
  border-radius: 16px;
  box-shadow: 0 12px 22px var(--tt-shadow);
  padding: 4px 12px;
  margin-bottom: 12px;
}

details[data-testid="stExpander"] summary {
  font-weight: 600;
}

div[data-testid="stMetric"] {
  background: var(--tt-card-bg);
  border: 1px solid var(--tt-card-border);
  border-radius: 14px;
  box-shadow: 0 10px 18px var(--tt-shadow);
  padding: 12px 14px;
}

.stAlert {
  border-radius: 14px;
  box-shadow: 0 8px 18px var(--tt-shadow);
}

/* Warning alert - orange/amber */
.stAlert[data-baseweb="notification"][kind="warning"],
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentWarning"]) {
  background: #FFF7ED !important;
  border: 1px solid #FDBA74 !important;
}

.stAlert[data-baseweb="notification"][kind="warning"] svg,
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentWarning"]) svg {
  color: #EA580C !important;
  fill: #EA580C !important;
}

/* Info alert - light blue */
.stAlert[data-baseweb="notification"][kind="info"],
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentInfo"]) {
  background: #EFF6FF !important;
  border: 1px solid #93C5FD !important;
}

.stAlert[data-baseweb="notification"][kind="info"] svg,
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentInfo"]) svg {
  color: #2563EB !important;
  fill: #2563EB !important;
}

/* Error alert - red */
.stAlert[data-baseweb="notification"][kind="error"],
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentError"]) {
  background: #FEF2F2 !important;
  border: 1px solid #FCA5A5 !important;
}

.stAlert[data-baseweb="notification"][kind="error"] svg,
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentError"]) svg {
  color: #DC2626 !important;
  fill: #DC2626 !important;
}

/* Success alert - green */
.stAlert[data-baseweb="notification"][kind="success"],
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentSuccess"]) {
  background: #F0FDF4 !important;
  border: 1px solid #86EFAC !important;
}

.stAlert[data-baseweb="notification"][kind="success"] svg,
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentSuccess"]) svg {
  color: #16A34A !important;
  fill: #16A34A !important;
}

div[data-baseweb="tab"] {
  font-weight: 500;
  border-radius: 999px;
  padding: 6px 14px;
}

div[data-baseweb="tab"][aria-selected="true"] {
  background: var(--tt-accent-soft);
  color: var(--tt-accent);
}

hr {
  border: 0;
  height: 1px;
  background: rgba(31, 42, 68, 0.16);
  margin: 0.9rem 0;
}

@media (max-width: 900px) {
  .block-container {
    padding-left: 1.25rem;
    padding-right: 1.25rem;
  }

  .tt-card {
    padding: 16px;
  }

  .tt-card--tall {
    min-height: 0;
  }
}
</style>
"""


def inject_streamlit_theme() -> None:
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def inject_searching_button_style() -> None:
    """Inject CSS to style buttons with 'Searching' text with animated green gradient."""
    st.markdown(
        """
        <style>
        /* Target disabled buttons containing 'Searching' text */
        .stButton > button:disabled p:first-child {
            color: inherit;
        }
        .stButton > button:disabled:has(p) {
            transition: all 0.3s ease;
        }
        </style>
        <script>
        // Apply searching style to buttons containing 'Searching'
        const observer = new MutationObserver(() => {
            document.querySelectorAll('.stButton button:disabled').forEach(btn => {
                const text = btn.textContent || '';
                if (text.includes('Searching') || text.includes('Generating') || text.includes('Processing')) {
                    btn.style.background = 'linear-gradient(90deg, #10b981, #34d399, #6ee7b7, #34d399, #10b981)';
                    btn.style.backgroundSize = '200% 100%';
                    btn.style.animation = 'tt-searching-pulse 1.5s ease-in-out infinite';
                    btn.style.borderColor = '#10b981';
                    btn.style.color = '#ffffff';
                    btn.style.boxShadow = '0 8px 20px rgba(16, 185, 129, 0.35)';
                }
            });
        });
        observer.observe(document.body, { childList: true, subtree: true, attributes: true });
        </script>
        """,
        unsafe_allow_html=True,
    )


@contextmanager
def card(class_name: str = "tt-card") -> Iterator[None]:
    st.markdown(f'<div class="{class_name}">', unsafe_allow_html=True)
    yield
    st.markdown("</div>", unsafe_allow_html=True)


def render_page_header(
    title: str,
    subtitle: str | None = None,
) -> None:
    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle) if subtitle else ""

    st.markdown('<div class="tt-header">', unsafe_allow_html=True)
    st.markdown(f'<div class="tt-title">{safe_title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="tt-subtitle">{safe_subtitle}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
