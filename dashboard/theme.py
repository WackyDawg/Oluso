"""Dark console styling for the Oluso dashboard.

The dashboard is a demonstration surface shown to judges and analysts, so it is styled as a
single dark console rather than default Streamlit widgets. Everything here is presentation
only: no call in this module talks to the API or changes a decision.

Risk colour is the one piece of styling that carries meaning. `RISK_COLOURS` maps the API's
risk levels onto the palette, and nothing else in the UI is allowed to use those hues.
"""

from __future__ import annotations

import html

import streamlit as st

INK = "#0B0C0E"
SURFACE = "#15171A"
SURFACE_RAISED = "#1B1E22"
BORDER = "#26292E"
TEXT = "#F3F5F6"
MUTED = "#878E97"
LIME = "#D2F34C"
CORAL = "#F58A94"
AMBER = "#FFC46B"

RISK_COLOURS = {
    "low": LIME,
    "guarded": "#B6E85F",
    "elevated": AMBER,
    "high": "#FF9E6C",
    "critical": CORAL,
}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stApp {{
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
}}
.stApp {{ background: {INK}; }}
#MainMenu, footer, header [data-testid="stDecoration"] {{ visibility: hidden; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 4rem; max-width: 1500px; }}

h1, h2, h3, h4, h5 {{ color: {TEXT}; font-weight: 600; letter-spacing: -0.015em; }}
p, li, span, label {{ color: {TEXT}; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
    color: {MUTED}; font-size: 0.82rem;
}}
hr, [data-testid="stDivider"] {{ border-color: {BORDER}; }}

/* Cards: st.container(border=True) and metrics share one surface treatment. */
[data-testid="stVerticalBlockBorderWrapper"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 20px;
    padding: 4px 6px;
}}
[data-testid="stMetric"] {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 18px;
    padding: 18px 20px;
}}
[data-testid="stMetricLabel"] p {{
    color: {MUTED}; font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.09em; text-transform: uppercase;
}}
[data-testid="stMetricValue"] {{
    color: {TEXT}; font-size: 1.55rem; font-weight: 600; letter-spacing: -0.02em;
}}

/* Pill controls. */
.stButton > button {{
    background: {SURFACE_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 999px;
    padding: 0.55rem 1.15rem;
    font-weight: 500;
    font-size: 0.87rem;
    transition: border-color 120ms ease, background 120ms ease;
}}
.stButton > button:hover {{ border-color: {LIME}; color: {LIME}; background: {SURFACE_RAISED}; }}
.stButton > button:focus:not(:active) {{ border-color: {LIME}; color: {LIME}; }}
/* Streamlit wraps button labels in <p>, so the label needs the colour too or it
   inherits white and disappears against lime. */
.stButton > button[kind="primary"],
.stButton > button[kind="primary"] p,
.stButton > button[kind="primary"]:hover p,
.stButton > button[kind="primary"]:focus p {{
    background: {LIME}; color: {INK} !important; border-color: {LIME}; font-weight: 600;
}}
.stButton > button[kind="primary"] p {{ background: transparent; }}
.stButton > button[kind="primary"]:hover {{ background: #E2FF63; border-color: #E2FF63; }}
.stButton > button:hover p {{ color: {LIME}; }}
.stButton > button[kind="primary"]:hover p {{ color: {INK} !important; }}

/* Inputs. */
[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
    background: {SURFACE_RAISED} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 14px !important;
    color: {TEXT} !important;
}}
[data-baseweb="select"] svg {{ color: {MUTED}; }}
.stTextInput label, .stSelectbox label {{
    color: {MUTED} !important; font-size: 0.74rem; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase;
}}

/* Alerts as tinted cards with an accent edge. */
[data-testid="stAlert"] {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-left: 3px solid {MUTED};
    border-radius: 14px;
    color: {TEXT};
}}
[data-testid="stAlert"] p {{ color: {TEXT}; font-size: 0.88rem; }}
[data-testid="stAlertContentSuccess"] {{ border-left-color: {LIME}; }}
[data-testid="stAlertContentWarning"] {{ border-left-color: {AMBER}; }}
[data-testid="stAlertContentError"] {{ border-left-color: {CORAL}; }}
[data-testid="stAlertContentInfo"] {{ border-left-color: #6FB1FF; }}

/* JSON / code blocks. */
[data-testid="stJson"], .stCodeBlock, pre {{
    background: {INK} !important;
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
[data-testid="stExpander"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
[data-testid="stExpander"] summary {{ color: {MUTED}; font-size: 0.85rem; }}
[data-testid="stExpander"] summary:hover {{ color: {LIME}; }}

/* Sidebar. */
[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
[data-testid="stSidebar"] .stTextInput input {{ font-size: 0.82rem; }}

[data-testid="stProgress"] > div > div > div > div {{ background: {LIME}; }}

/* Bespoke components. */
.oluso-top {{
    display: flex; align-items: center; justify-content: space-between;
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 22px;
    padding: 16px 22px; margin-bottom: 18px;
}}
.oluso-brand {{ display: flex; align-items: center; gap: 14px; }}
.oluso-mark {{
    width: 40px; height: 40px; border-radius: 50%; background: {LIME};
    display: flex; align-items: center; justify-content: center;
    font-size: 17px; font-weight: 800; line-height: 1;
    color: {INK}; letter-spacing: -0.03em;
}}
.oluso-name {{ font-size: 1.22rem; font-weight: 700; color: {TEXT}; letter-spacing: -0.02em; }}
.oluso-sub {{ font-size: 0.75rem; color: {MUTED}; margin-top: 2px; }}
.oluso-chips {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.oluso-chip {{
    border: 1px solid {BORDER}; border-radius: 999px; padding: 6px 14px;
    font-size: 0.76rem; color: {MUTED}; background: {SURFACE_RAISED}; white-space: nowrap;
}}
.oluso-chip strong {{ color: {TEXT}; font-weight: 600; }}
.oluso-chip.live {{ border-color: {LIME}; color: {LIME}; }}
.oluso-chip.warn {{ border-color: {AMBER}; color: {AMBER}; }}

.oluso-section {{
    display: flex; align-items: center; gap: 10px;
    margin: 26px 0 12px 0;
}}
.oluso-section .bar {{ width: 6px; height: 18px; border-radius: 3px; background: {LIME}; }}
.oluso-section .label {{
    font-size: 0.78rem; font-weight: 600; color: {MUTED};
    letter-spacing: 0.12em; text-transform: uppercase;
}}

.oluso-hero {{
    display: flex; align-items: center; gap: 28px; flex-wrap: wrap;
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: 22px; padding: 26px 30px;
}}
.oluso-dial {{
    width: 132px; height: 132px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; flex: none;
}}
.oluso-dial-inner {{
    width: 106px; height: 106px; border-radius: 50%; background: {SURFACE};
    display: flex; flex-direction: column; align-items: center; justify-content: center;
}}
.oluso-dial-value {{ font-size: 1.85rem; font-weight: 700; letter-spacing: -0.03em; }}
.oluso-dial-unit {{ font-size: 0.68rem; color: {MUTED}; letter-spacing: 0.1em; text-transform: uppercase; }}
.oluso-hero-body {{ flex: 1 1 340px; min-width: 300px; }}
.oluso-hero-level {{ font-size: 0.74rem; letter-spacing: 0.14em; text-transform: uppercase; font-weight: 700; }}
.oluso-hero-action {{
    font-size: 1.55rem; font-weight: 600; color: {TEXT};
    letter-spacing: -0.02em; margin: 4px 0 10px 0;
}}
.oluso-hero-note {{ color: {MUTED}; font-size: 0.88rem; line-height: 1.5; }}

.oluso-bar {{ margin-top: 14px; }}
.oluso-bar-track {{
    height: 8px; border-radius: 999px; background: {SURFACE_RAISED};
    border: 1px solid {BORDER}; overflow: hidden;
}}
.oluso-bar-fill {{ height: 100%; border-radius: 999px; }}
.oluso-bar-legend {{
    display: flex; justify-content: space-between; margin-top: 6px;
    font-size: 0.7rem; color: {MUTED}; letter-spacing: 0.06em; text-transform: uppercase;
}}

.oluso-reason {{
    display: flex; gap: 12px; align-items: flex-start;
    background: {SURFACE_RAISED}; border: 1px solid {BORDER};
    border-radius: 14px; padding: 12px 16px; margin-bottom: 8px;
}}
.oluso-reason .code {{
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.07em;
    color: {INK}; background: {LIME}; border-radius: 6px;
    padding: 3px 8px; white-space: nowrap; flex: none; margin-top: 2px;
}}
.oluso-reason .text {{ color: {TEXT}; font-size: 0.88rem; line-height: 1.45; }}

.oluso-row {{
    display: flex; align-items: center; gap: 14px;
    border-bottom: 1px solid {BORDER}; padding: 11px 4px;
}}
.oluso-row:last-child {{ border-bottom: none; }}
.oluso-row .badge {{
    font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em;
    border-radius: 999px; padding: 4px 11px; flex: none; min-width: 86px; text-align: center;
}}
.oluso-row .score {{ font-weight: 600; color: {TEXT}; font-size: 0.92rem; min-width: 62px; }}
.oluso-row .action {{ color: {MUTED}; font-size: 0.85rem; }}
</style>
"""


def inject() -> None:
    """Apply the console styling. Call once, immediately after `set_page_config`."""

    st.markdown(CSS, unsafe_allow_html=True)


def _esc(value: object) -> str:
    return html.escape(str(value))


def topbar(chips: list[tuple[str, str]]) -> None:
    """Brand bar with status chips. Each chip is (text, style) where style is '', 'live' or 'warn'."""

    rendered = "".join(
        f'<div class="oluso-chip {_esc(style)}">{text}</div>' for text, style in chips
    )
    st.markdown(
        f"""
        <div class="oluso-top">
          <div class="oluso-brand">
            <div class="oluso-mark">OL</div>
            <div>
              <div class="oluso-name">Oluso</div>
              <div class="oluso-sub">Behavioural resilience platform · v1.4</div>
            </div>
          </div>
          <div class="oluso-chips">{rendered}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    st.markdown(
        f'<div class="oluso-section"><div class="bar"></div>'
        f'<div class="label">{_esc(label)}</div></div>',
        unsafe_allow_html=True,
    )


def hero(risk_level: str, fused_score: float, action: str, note: str, confidence: float) -> None:
    """The decision headline: score dial, chosen action, and the confidence bar beneath it.

    Confidence is drawn as a separate bar rather than folded into the dial, because the
    system reports how *well-supported* a score is separately from the score itself.
    """

    colour = RISK_COLOURS.get(risk_level.lower(), LIME)
    sweep = max(0.0, min(1.0, fused_score)) * 360
    st.markdown(
        f"""
        <div class="oluso-hero">
          <div class="oluso-dial" style="background: conic-gradient({colour} {sweep}deg, {SURFACE_RAISED} {sweep}deg);">
            <div class="oluso-dial-inner">
              <div class="oluso-dial-value" style="color:{colour};">{fused_score:.0%}</div>
              <div class="oluso-dial-unit">risk</div>
            </div>
          </div>
          <div class="oluso-hero-body">
            <div class="oluso-hero-level" style="color:{colour};">{_esc(risk_level).upper()}</div>
            <div class="oluso-hero-action">{_esc(action)}</div>
            <div class="oluso-hero-note">{_esc(note)}</div>
            <div class="oluso-bar">
              <div class="oluso-bar-track">
                <div class="oluso-bar-fill" style="width:{max(0.0, min(1.0, confidence)) * 100:.1f}%; background:{LIME};"></div>
              </div>
              <div class="oluso-bar-legend">
                <span>Decision confidence</span><span>{confidence:.0%}</span>
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def reason(code: str, message: str) -> None:
    st.markdown(
        f'<div class="oluso-reason"><div class="code">{_esc(code)}</div>'
        f'<div class="text">{_esc(message)}</div></div>',
        unsafe_allow_html=True,
    )


def decision_row(risk_level: str, score: float, action: str) -> None:
    colour = RISK_COLOURS.get(risk_level.lower(), LIME)
    st.markdown(
        f"""
        <div class="oluso-row">
          <div class="badge" style="color:{colour}; border:1px solid {colour}33; background:{colour}14;">
            {_esc(risk_level).upper()}
          </div>
          <div class="score">{score:.1%}</div>
          <div class="action">{_esc(action)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
