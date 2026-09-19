"""Competition dashboard presentation layer for Oluso ATO Lab.

All HTML generated here is presentational. Decision state still comes from the API.
The module is intentionally dependency-free: icons are inline SVG so the demo works offline.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Iterable

import streamlit as st

from icons import icon

INK = "#0A0A0D"
PANEL = "#101116"
PANEL_2 = "#151720"
PANEL_3 = "#1A1C27"
BORDER = "#262938"
TEXT = "#F7F7FB"
MUTED = "#9297A8"
PURPLE = "#8B5CF6"
PURPLE_2 = "#A855F7"
PINK = "#FF4F78"
GREEN = "#16E98A"
GOLD = "#F4B548"
BLUE = "#6476FF"

RISK_COLOURS = {
    "low": GREEN,
    "guarded": "#A8E063",
    "elevated": GOLD,
    "high": "#FF875E",
    "critical": PINK,
}

CSS = f"""
<style>
:root {{ color-scheme: dark; }}
html, body, [class*="css"], .stApp {{
  font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}
.stApp {{
  background:
    radial-gradient(circle at 72% -12%, rgba(139,92,246,.08), transparent 32%),
    radial-gradient(circle at 12% 0%, rgba(168,85,247,.05), transparent 24%),
    {INK};
  color: {TEXT};
}}
#MainMenu, footer, [data-testid="stHeader"] {{ visibility: hidden; height: 0; }}
.block-container {{ max-width: 1700px; padding: .75rem 1.05rem 2.4rem 1.05rem; }}
[data-testid="stAppViewContainer"] > .main {{ background: transparent; }}

[data-testid="stSidebar"] {{
  background: linear-gradient(180deg,#0B0C10 0%,#0D0E13 100%);
  border-right: 1px solid #1F2230;
}}
[data-testid="stSidebarContent"] {{ padding-top: .6rem; }}
[data-testid="stSidebar"] .block-container {{ padding: .6rem .75rem 1.5rem .75rem; }}
[data-testid="stSidebar"] [data-testid="stExpander"] {{
  background:#101116; border:1px solid #242735; border-radius:14px;
}}
[data-testid="stSidebar"] .stTextInput label,
[data-testid="stSidebar"] .stSelectbox label {{
  color:{MUTED}!important; font-size:.68rem!important; text-transform:uppercase; letter-spacing:.08em;
}}

[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
  min-height: 44px; background: #11131A !important; color:{TEXT}!important;
  border:1px solid #2A2D3C !important; border-radius:11px !important;
  box-shadow:none!important;
}}
[data-baseweb="select"] > div:hover, .stTextInput input:hover {{ border-color:#4A3B73!important; }}
[data-baseweb="select"] svg {{ color:#A78BFA; }}
.stButton > button {{
  width:100%; min-height:44px; border-radius:11px; background:#12141B;
  border:1px solid #2A2D3C; color:{TEXT}; font-size:.82rem; font-weight:600;
  transition: all .15s ease;
}}
.stButton > button p {{ color:{TEXT}!important; }}
.stButton > button:hover {{
  border-color:#6D4FD3; background:#171522; color:white; transform:translateY(-1px);
}}
.stButton > button[kind="primary"] {{
  background: linear-gradient(100deg,#6246FF 0%,#8C4FFF 55%,#FF668A 115%);
  border-color:#8C5CFF; box-shadow:0 0 22px rgba(124,74,255,.26);
}}
.stButton > button[kind="primary"]:hover {{
  background: linear-gradient(100deg,#755BFF 0%,#9C5EFF 55%,#FF7898 115%);
  border-color:#A37AFF;
}}
[data-testid="stVerticalBlockBorderWrapper"] {{
  background:#0E0F14; border:1px solid #232633; border-radius:14px;
  padding:4px 6px;
}}
[data-testid="stAlert"] {{ border-radius:12px; background:#12141B; border:1px solid #292C3B; }}
[data-testid="stExpander"] {{ background:#0E0F14; border:1px solid #232633; border-radius:14px; }}
[data-testid="stExpander"] summary p {{ color:#DADCE6; font-weight:600; }}
[data-testid="stJson"], pre {{
  background:#0A0B0F!important; border:1px solid #232633!important; border-radius:12px!important;
}}
[data-testid="stProgress"] > div > div > div > div {{
  background:linear-gradient(90deg,{PURPLE},{PINK});
}}

.ol-icon {{ display:inline-block; vertical-align:middle; flex:none; }}
.ol-shell {{ color:{TEXT}; }}

.ol-side-brand {{ display:flex; align-items:center; gap:11px; padding:5px 6px 13px; }}
.ol-side-brand .mark {{ color:#A967FF; filter:drop-shadow(0 0 8px rgba(169,103,255,.55)); }}
.ol-side-title {{ font-size:1.18rem; font-weight:800; letter-spacing:-.025em; line-height:1.05; }}
.ol-side-sub {{ font-size:.76rem; color:#E7E4EE; margin-top:3px; font-weight:600; }}
.ol-tenant {{
  display:flex; align-items:center; gap:10px; border:1px solid #3B275D;
  background:linear-gradient(180deg,#16121F,#111117); border-radius:11px;
  padding:10px 11px; margin:0 3px 14px;
}}
.ol-tenant .badge {{
  width:31px;height:31px;border-radius:8px;background:#10382D;color:#62E9B3;
  display:grid;place-items:center;font-weight:800;font-size:.79rem;
}}
.ol-tenant .name {{ font-size:.78rem;font-weight:700; }}
.ol-tenant .sub {{ color:{MUTED};font-size:.65rem;margin-top:2px; }}
.ol-nav {{ margin:0 0 18px; }}
.ol-nav-item {{
  display:flex; align-items:center; gap:11px; color:#B7BCD0; padding:10px 11px;
  border-radius:10px; margin:3px 2px; font-size:.78rem; font-weight:600;
}}
.ol-nav-item.active {{
  color:white;background:linear-gradient(90deg,rgba(118,67,255,.95),rgba(140,59,214,.68));
  box-shadow:0 0 16px rgba(123,68,255,.35);
}}
.ol-nav-item.mesh {{ color:#D5D8E6; }}
.ol-nav-item.mesh .ol-icon {{ color:#F7C644; }}
.ol-side-promo {{
  border:1px solid #4B2D72;
  background:radial-gradient(circle at 90% 30%,rgba(100,70,255,.18),transparent 35%),#111018;
  border-radius:12px; padding:17px 14px; margin:20px 3px 16px;
}}
.ol-side-promo .big {{ color:#A773FF; font-size:.98rem; line-height:1.25; font-weight:800; }}
.ol-side-promo .small {{ color:#A8ACBA; font-size:.68rem; line-height:1.55; margin-top:13px; }}
.ol-user {{ display:flex;align-items:center;gap:9px;border-top:1px solid #222531;padding:13px 5px 3px; }}
.ol-user .avatar {{
  width:31px;height:31px;border-radius:50%;display:grid;place-items:center;
  background:linear-gradient(135deg,#7151FF,#A05AFF);font-size:.68rem;font-weight:800;
}}
.ol-user .n {{ font-size:.72rem;font-weight:700; }}
.ol-user .e {{ font-size:.61rem;color:{MUTED};margin-top:1px; }}

.ol-topbar {{
  min-height:58px; display:flex; align-items:center; justify-content:space-between; gap:16px;
  padding:3px 2px 10px; border-bottom:1px solid #20232E; margin-bottom:10px;
}}
.ol-heading {{ min-width:290px; }}
.ol-heading .title {{ font-size:1.35rem;font-weight:800;letter-spacing:-.03em; }}
.ol-heading .sub {{ color:#B3B8C9;font-size:.72rem;margin-top:1px; }}
.ol-top-right {{ display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap; }}
.ol-chip {{
  height:35px; display:flex;align-items:center;gap:7px;padding:0 11px;border:1px solid #2B3040;
  border-radius:9px; background:#10131A;color:#C9CDDA;font-size:.66rem;line-height:1.02;
}}
.ol-chip strong {{ display:block;color:white;font-size:.68rem;margin-top:2px; }}
.ol-chip.live {{ border-color:#135F45;background:linear-gradient(180deg,#0D221B,#0D1715); }}
.ol-chip.live .ol-icon,.ol-chip.live strong {{ color:#41EFA0; }}
.ol-chip.purple .ol-icon {{ color:#A67BFF; }}
.ol-search {{
  width:260px;height:35px;border:1px solid #2B3040;border-radius:9px;background:#0E1117;
  color:#7F8597;display:flex;align-items:center;gap:7px;padding:0 11px;font-size:.65rem;
}}
.ol-time {{ color:#B7BCCB;font-size:.61rem;line-height:1.42;text-align:right;min-width:80px; }}

.ol-panel {{
  background:linear-gradient(180deg,#111218,#0E0F13); border:1px solid #252835; border-radius:12px;
}}
.ol-section-title {{ display:flex;align-items:center;justify-content:space-between;margin-bottom:8px; }}
.ol-section-title .left {{ display:flex;align-items:center;gap:8px;font-size:.78rem;font-weight:750; }}
.ol-section-title .link {{ color:#7B83FF;font-size:.62rem; }}

.ol-hero-grid {{
  display:grid;grid-template-columns:1.15fr .9fr 1.15fr 1fr 1.65fr;gap:10px;margin-top:7px;
}}
.ol-hero-card {{ min-height:137px; padding:15px 18px; position:relative;overflow:hidden; }}
.ol-hero-card::after {{
  content:"";position:absolute;inset:auto -35px -55px auto;width:120px;height:120px;
  border-radius:50%;filter:blur(18px);opacity:.16;
}}
.ol-risk {{ background:linear-gradient(135deg,rgba(112,17,46,.55),rgba(22,13,24,.95));border-color:#6E233F; }}
.ol-risk::after {{ background:{PINK}; }}
.ol-action {{ background:linear-gradient(135deg,rgba(78,53,16,.63),rgba(22,18,13,.95));border-color:#7A5B26; }}
.ol-action::after {{ background:{GOLD}; }}
.ol-confidence {{ background:linear-gradient(135deg,rgba(8,70,44,.65),rgba(11,26,20,.95));border-color:#176745; }}
.ol-confidence::after {{ background:{GREEN}; }}
.ol-label {{
  color:#D7DAE5;font-size:.63rem;text-transform:uppercase;letter-spacing:.025em;
  font-weight:700;display:flex;align-items:center;gap:6px;
}}
.ol-risk .ol-label {{ color:#FF6685; }}
.ol-big {{ margin-top:13px;font-size:2rem;font-weight:850;letter-spacing:-.045em;line-height:.95; }}
.ol-subtext {{ margin-top:9px;color:#C3C6D1;font-size:.68rem; }}
.ol-gauge-wrap {{ display:flex;justify-content:center;align-items:center;height:100px;margin-top:4px; }}
.ol-gauge {{ width:90px;height:90px;border-radius:50%;display:grid;place-items:center; }}
.ol-gauge-inner {{
  width:66px;height:66px;border-radius:50%;background:#111217;display:grid;place-items:center;text-align:center;
}}
.ol-gauge-inner .v {{ font-size:1.55rem;font-weight:800;letter-spacing:-.04em;line-height:1; }}
.ol-gauge-inner .u {{ color:#AEB2C0;font-size:.55rem;margin-top:3px; }}
.ol-action-main,.ol-conf-main {{ display:flex;align-items:center;gap:10px;margin-top:13px; }}
.ol-action-icon,.ol-conf-icon {{ width:36px;height:36px;border-radius:50%;display:grid;place-items:center; }}
.ol-action-icon {{ color:#FFC37A;background:#6E4420; }}
.ol-conf-icon {{ color:#32E99C;background:#0D5A3B; }}
.ol-action-name,.ol-conf-name {{ font-size:1.1rem;font-weight:800;letter-spacing:-.025em; }}
.ol-policy-pill {{
  display:inline-flex;margin-top:9px;padding:5px 10px;border-radius:999px;background:#25231F;
  border:1px solid #3C3930;color:#E8E4D9;font-size:.58rem;
}}
.ol-trend {{ padding:13px 15px; }}
.ol-trend-head {{
  display:flex;justify-content:space-between;align-items:center;font-size:.72rem;font-weight:700;
}}
.ol-trend-head span {{ color:{PINK};font-size:.78rem; }}
.ol-trend svg {{ width:100%;height:85px;margin-top:7px;overflow:visible; }}

.ol-metrics {{ display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px;margin-top:10px; }}
.ol-metric {{ min-height:75px;padding:12px 13px;display:flex;gap:10px;align-items:flex-start; }}
.ol-metric-icon {{
  width:30px;height:30px;border-radius:8px;display:grid;place-items:center;color:#A86DFF;
  background:linear-gradient(135deg,#24153D,#151325);box-shadow:0 0 14px rgba(139,92,246,.13);
}}
.ol-metric .name {{ color:#D6D8E2;font-size:.62rem; }}
.ol-metric .value {{ font-size:1.03rem;font-weight:800;margin-top:5px;letter-spacing:-.025em; }}
.ol-metric .hint {{ color:#A8ADBB;font-size:.55rem;margin-top:3px; }}
.ol-metric .hint.good {{ color:#21DE8D; }}
.ol-metric .hint.bad {{ color:#FF5678; }}

.ol-content-grid {{ display:grid;grid-template-columns:2.25fr 1fr;gap:10px;margin-top:10px; }}
.ol-reason-panel,.ol-channel-panel {{ padding:12px 13px; }}
.ol-reasons {{ display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:7px; }}
.ol-reason {{
  min-height:91px;padding:10px 9px;border:1px solid #2B2D39;border-radius:8px;
  background:linear-gradient(180deg,#1A1821,#14151B);
}}
.ol-reason-top {{
  display:flex;align-items:flex-start;gap:6px;color:#F3F4F8;font-size:.62rem;font-weight:700;line-height:1.18;
}}
.ol-reason-top .ol-icon {{ color:#FF536F; }}
.ol-reason-msg {{ color:#AEB2BF;font-size:.55rem;line-height:1.3;margin-top:6px;min-height:29px; }}
.ol-reason-code {{
  display:inline-block;margin-top:6px;padding:3px 7px;border-radius:6px;background:#6B2134;
  color:#FF8298;font-size:.52rem;font-weight:700;
}}
.ol-channel-chart {{ height:100px;display:flex;align-items:flex-end;gap:12px;padding:13px 5px 0; }}
.ol-channel-col {{
  flex:1;display:flex;justify-content:center;align-items:flex-end;gap:3px;height:76px;
  border-bottom:1px solid #2C2E38;position:relative;
}}
.ol-bar-current,.ol-bar-typical {{ width:11px;border-radius:3px 3px 0 0; }}
.ol-bar-current {{ background:linear-gradient(180deg,#FF6A85,#E73A62);box-shadow:0 0 8px rgba(255,79,120,.22); }}
.ol-bar-typical {{ background:linear-gradient(180deg,#7768FF,#5149D8); }}
.ol-channel-label {{
  position:absolute;bottom:-18px;color:#9BA0AF;font-size:.49rem;white-space:nowrap;
}}
.ol-chart-legend {{ display:flex;gap:12px;color:#9FA4B3;font-size:.52rem; }}
.ol-dot {{ width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:4px; }}

.ol-recourse-grid {{ display:grid;grid-template-columns:2.2fr 1.05fr;gap:10px;margin-top:10px; }}
.ol-recourse-panel,.ol-twin-panel {{ padding:12px 13px; }}
.ol-recourse-cards {{ display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px; }}
.ol-recourse {{ min-height:70px;padding:10px;border-radius:8px;border:1px solid #303244;background:#161821; }}
.ol-recourse.good {{ background:linear-gradient(135deg,#0B4E33,#11241D);border-color:#13895A; }}
.ol-recourse.gold {{ background:linear-gradient(135deg,#604213,#251C0E);border-color:#9E6D1D; }}
.ol-recourse-head {{ display:flex;gap:7px;align-items:center;font-size:.6rem;font-weight:750; }}
.ol-recourse.good .ol-icon {{ color:#2CF09C; }}
.ol-recourse.gold .ol-icon {{ color:#FFD06E; }}
.ol-recourse .ol-icon {{ color:#B475FF; }}
.ol-recourse-msg {{ color:#B4B8C4;font-size:.51rem;line-height:1.25;margin-top:6px; }}
.ol-recourse-time {{ color:#B7BBC9;font-size:.5rem;margin-top:5px; }}
.ol-twin-row {{ display:grid;grid-template-columns:1.15fr repeat(4,.75fr);gap:9px;align-items:stretch; }}
.ol-person-card {{
  display:flex;align-items:center;gap:9px;padding:8px;border:1px solid #1D6349;
  border-radius:8px;background:#10201A;
}}
.ol-person-avatar {{
  width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:#333650;color:#A9AFFF;
}}
.ol-person-id {{ font-size:.62rem;font-weight:700; }}
.ol-person-trust {{ color:#22E493;font-size:.55rem;margin-top:2px; }}
.ol-twin-stat {{ border-left:1px solid #242734;padding:6px 5px; }}
.ol-twin-stat .k {{ color:#9EA3B2;font-size:.49rem; }}
.ol-twin-stat .v {{ color:#F5F5F8;font-size:.59rem;font-weight:700;margin-top:4px; }}

.ol-mesh-panel {{ margin-top:10px;padding:11px 13px; }}
.ol-mesh-head {{ display:flex;align-items:center;gap:7px;font-size:.7rem;font-weight:750; }}
.ol-mesh-head .ol-icon {{ color:#9F6BFF; }}
.ol-mesh-sub {{ color:#A2A6B4;font-size:.52rem;margin:2px 0 8px 25px; }}
.ol-mesh-grid {{ display:grid;grid-template-columns:repeat(5,1fr) 1.42fr;gap:7px; }}
.ol-mesh-card {{
  min-height:58px;border:1px solid #292C39;border-radius:8px;background:#14161D;padding:8px 9px;
}}
.ol-mesh-card .k {{ color:#9FA4B2;font-size:.49rem; }}
.ol-mesh-card .v {{
  font-size:.7rem;font-weight:750;margin-top:5px;display:flex;align-items:center;gap:6px;
}}
.ol-mesh-card .s {{ color:#A3A7B5;font-size:.48rem;margin-top:3px; }}
.ol-mesh-card.good {{ background:#10231C;border-color:#1D5F47; }}
.ol-mesh-card.good .v {{ color:#22E493; }}
.ol-mesh-story {{ display:flex;align-items:center;justify-content:center;gap:10px;padding:6px 10px; }}
.ol-mesh-globe {{ color:#6757FF;filter:drop-shadow(0 0 8px rgba(103,87,255,.35)); }}
.ol-mesh-copy .a {{ color:#9A7BFF;font-size:.58rem;font-weight:750; }}
.ol-mesh-copy .b {{ color:#B2B6C3;font-size:.48rem;margin-top:3px; }}
.ol-mesh-copy .c {{ color:#39E79C;font-size:.48rem;margin-top:6px; }}

.ol-bottom-grid {{ display:grid;grid-template-columns:1.05fr 1fr;gap:10px;margin-top:10px; }}
.ol-bottom-panel {{ padding:10px 12px; }}
.ol-bottom-cards {{ display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;margin-top:7px; }}
.ol-mini {{ min-height:60px;border:1px solid #272A36;border-radius:8px;background:#14161C;padding:8px; }}
.ol-mini .k {{ color:#A0A5B3;font-size:.48rem; }}
.ol-mini .v {{
  color:#F2F3F7;font-size:.61rem;font-weight:700;margin-top:6px;display:flex;align-items:center;gap:5px;
}}
.ol-mini .s {{ color:#9196A5;font-size:.46rem;margin-top:4px; }}
.ol-mini .ok {{ color:#25E38F; }}

.ol-empty {{
  padding:34px;text-align:center;border:1px dashed #313444;border-radius:13px;
  background:#0E0F14;color:#959AA9;margin-top:10px;
}}
.ol-empty .title {{ color:#E6E7EC;font-size:1rem;font-weight:750;margin-top:9px; }}
.ol-empty .sub {{ font-size:.68rem;line-height:1.5;margin-top:6px; }}

@media (max-width: 1250px) {{
  .ol-hero-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  .ol-trend {{ grid-column:1/-1; }}
  .ol-metrics {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
  .ol-reasons {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
  .ol-content-grid,.ol-recourse-grid,.ol-bottom-grid {{ grid-template-columns:1fr; }}
  .ol-mesh-grid {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
}}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _e(value: object) -> str:
    return html.escape(str(value))


def sidebar(tenant: str) -> None:
    nav = [
        ("home", "Overview", "active"),
        ("activity", "Live Scoring", ""),
        ("user", "Customer Twin", ""),
        ("mesh", "OlusoMesh", "mesh"),
        ("terminal", "Agent Terminal", ""),
        ("shield", "Governance", ""),
        ("bolt", "Resilience", ""),
        ("file", "Audit", ""),
    ]
    nav_html = "".join(
        f'<div class="ol-nav-item {css}">{icon(name,17)}<span>{_e(label)}</span></div>'
        for name, label, css in nav
    )
    st.sidebar.markdown(
        f"""
        <div class="ol-side-brand">
          <div class="mark">{icon('logo',35)}</div>
          <div><div class="ol-side-title">Oluso</div><div class="ol-side-sub">ATO Lab</div></div>
        </div>
        <div class="ol-tenant">
          <div class="badge">OB</div>
          <div><div class="name">Oluso Demo Bank</div><div class="sub">{_e(tenant)} · Competition demo</div></div>
        </div>
        <div class="ol-nav">{nav_html}</div>
        <div class="ol-side-promo">
          <div class="big">Stronger<br>banks.<br>Safer people.</div>
          <div class="small">Explain.<br>Prevent.<br>Keep trust.</div>
        </div>
        <div class="ol-user">
          <div class="avatar">DA</div>
          <div><div class="n">Demo Analyst</div><div class="e">competition workspace</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def topbar(health: dict | None) -> None:
    health = health or {}
    online = str(health.get("resilience_mode", "unknown")) == "online"
    model_loaded = bool(health.get("model_available"))
    audit_valid = bool(health.get("audit_chain_valid"))
    now = datetime.utcnow()
    chips = f"""
      <div class="ol-chip {'live' if online else ''}">{icon('activity',15)}<div>Mode<strong>{_e(str(health.get('resilience_mode','unknown')).upper())}</strong></div></div>
      <div class="ol-chip purple">{icon('brain',15)}<div>Model<strong>{'Loaded' if model_loaded else 'Missing'}</strong></div></div>
      <div class="ol-chip {'live' if audit_valid else ''}">{icon('shield',15)}<div>Audit Chain<strong>{'Valid' if audit_valid else 'Check'}</strong></div></div>
      <div class="ol-chip purple">{icon('database',15)}<div><strong>Synthetic Data Only</strong></div></div>
    """
    st.markdown(
        f"""
        <div class="ol-topbar">
          <div class="ol-heading">
            <div class="title">Oluso ATO Lab</div>
            <div class="sub">Explainable account-takeover defence for app, USSD and agency banking</div>
          </div>
          <div class="ol-top-right">{chips}
            <div class="ol-search">{icon('search',14)} Search events, accounts, or indicators…</div>
            <div class="ol-chip purple">{icon('bell',15)}</div>
            <div class="ol-time">{now.strftime('%d %b %Y')}<br>{now.strftime('%H:%M')} UTC</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _sparkline(values: Iterable[float], colour: str = PINK) -> str:
    vals = [max(0.0, min(1.0, float(v))) for v in values]
    if not vals:
        vals = [0.0]
    w, h = 300, 72
    if len(vals) == 1:
        pts = [(0, h - vals[0] * h)]
    else:
        pts = [(i * w / (len(vals) - 1), h - (v * (h - 8) + 4)) for i, v in enumerate(vals)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    circles = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="{colour}"/>'
        for x, y in pts[-5:]
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f'<line x1="0" y1="{h-1}" x2="{w}" y2="{h-1}" stroke="#2A2D37"/>'
        f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="2"/>{circles}</svg>'
    )


def decision_hero(decision: dict, risk_history: list[float]) -> None:
    score = decision.get("score", {}) or {}
    policy = decision.get("policy", {}) or {}
    confidence = decision.get("decision_confidence", {}) or {}
    risk = str(decision.get("risk_level", "unknown"))
    fused = float(score.get("fused_score") or 0)
    colour = RISK_COLOURS.get(risk.lower(), PURPLE)
    sweep = fused * 360
    action = str(policy.get("action", "monitor")).replace("_", " ").title()
    hold_seconds = int(policy.get("hold_seconds") or 0)
    hold_note = "Reversible intervention" if hold_seconds else "Proportional response"
    conf_value = float(confidence.get("score") or 0)
    conf_level = str(confidence.get("level", "unknown")).title()
    st.markdown(
        f"""
        <div class="ol-hero-grid">
          <div class="ol-panel ol-hero-card ol-risk">
            <div class="ol-label">{icon('warning',16)} Risk Level</div>
            <div class="ol-big" style="color:{colour}">{_e(risk.title())}</div>
            <div class="ol-subtext">{_e(decision.get('customer_explanation','Account activity evaluated.'))}</div>
          </div>
          <div class="ol-panel ol-hero-card">
            <div class="ol-label">Fused Score</div>
            <div class="ol-gauge-wrap"><div class="ol-gauge" style="background:conic-gradient({colour} {sweep:.0f}deg,#252731 {sweep:.0f}deg)">
              <div class="ol-gauge-inner"><div><div class="v">{fused:.2f}</div><div class="u">/ 1.00</div></div></div>
            </div></div>
          </div>
          <div class="ol-panel ol-hero-card ol-action">
            <div class="ol-label">Recommended Action</div>
            <div class="ol-action-main"><div class="ol-action-icon">{icon('shield',20)}</div><div>
              <div class="ol-action-name">{_e(action)}</div>
              <div class="ol-subtext" style="margin-top:2px">{_e(hold_note)}</div>
            </div></div>
            <div class="ol-policy-pill">Policy · {_e(str(policy.get('policy_version','live')))}</div>
          </div>
          <div class="ol-panel ol-hero-card ol-confidence">
            <div class="ol-label">Decision Confidence</div>
            <div class="ol-conf-main"><div class="ol-conf-icon">{icon('check',20)}</div><div>
              <div class="ol-conf-name">{_e(conf_level)}</div>
              <div class="ol-subtext" style="margin-top:2px">{conf_value:.0%} evidence support</div>
            </div></div>
          </div>
          <div class="ol-panel ol-trend">
            <div class="ol-trend-head">Risk Trend <span>Current {fused:.2f}</span></div>
            {_sparkline(risk_history or [fused], colour)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metrics(decision: dict) -> None:
    score = decision.get("score", {}) or {}
    policy = decision.get("policy", {}) or {}
    evidence = decision.get("evidence", {}) or {}
    risk_window = decision.get("risk_window", {}) or {}
    hold_seconds = int(policy.get("hold_seconds") or 0)
    items = [
        ("brain", "Model Score", "n/a" if score.get("model_score") is None else f"{float(score['model_score']):.2f}", "Population model", ""),
        ("wave", "Anomaly Score", f"{float(score.get('anomaly_score') or 0):.2f}", "Personal deviation", "bad"),
        ("user", "Profile Confidence", f"{float(score.get('profile_confidence') or 0):.2f}", "Behavioural history", "good"),
        ("clock", "Hold Time", f"{hold_seconds // 60} min" if hold_seconds else "None", "Reassesses automatically", ""),
        ("coverage", "Evidence Coverage", f"{float(evidence.get('coverage') or 0):.0%}", _e(evidence.get('mode','live')), ""),
        ("calendar", "Account Risk Window", _e(str(risk_window.get('state','clear')).title()), f"{float(risk_window.get('hours_remaining') or 0):.1f}h remaining", "bad" if str(risk_window.get('state')) != 'clear' else 'good'),
    ]
    cards = "".join(
        f'<div class="ol-panel ol-metric"><div class="ol-metric-icon">{icon(ic,16)}</div><div><div class="name">{name}</div><div class="value">{value}</div><div class="hint {tone}">{hint}</div></div></div>'
        for ic, name, value, hint, tone in items
    )
    st.markdown(f'<div class="ol-metrics">{cards}</div>', unsafe_allow_html=True)


def _reason_icon(code: str, message: str) -> str:
    text = f"{code} {message}".lower()
    if "recipient" in text or "mule" in text:
        return "recipient"
    if "sim" in text or "device" in text:
        return "sim"
    if "recover" in text or "reset" in text or "failed" in text:
        return "recovery"
    if "drain" in text or "amount" in text or "balance" in text:
        return "drain"
    if "ussd" in text or "interaction" in text or "navigation" in text:
        return "grid"
    if "floor" in text or "security" in text:
        return "shield"
    return "warning"


def _short_reason_title(code: str, message: str) -> str:
    msg = message.strip().rstrip(".")
    return msg if len(msg) <= 30 else msg[:27].rstrip() + "…"


def reasons_and_channels(decision: dict, current_channel: str = "app") -> None:
    reasons = list(decision.get("reasons") or [])[:6]
    if not reasons:
        reasons = [{"code": "CLEAR", "message": "No material takeover indicators"}]
    reason_html = "".join(
        f'<div class="ol-reason"><div class="ol-reason-top">{icon(_reason_icon(str(r.get("code","")),str(r.get("message",""))),15)}<span>{_e(_short_reason_title(str(r.get("code","")),str(r.get("message",""))))}</span></div><div class="ol-reason-msg">{_e(r.get("message",""))}</div><div class="ol-reason-code">{_e(str(r.get("code","signal")))}</div></div>'
        for r in reasons
    )
    channels = ["App", "USSD", "Web", "ATM", "Agent"]
    typical = {"App":42,"USSD":31,"Web":7,"ATM":8,"Agent":12}
    current = {c:4 for c in channels}
    selected = "Agent" if current_channel == "agent" else "USSD" if current_channel == "ussd" else "Web" if current_channel == "web" else "App"
    current[selected] = 56
    chart = "".join(
        f'<div class="ol-channel-col"><div class="ol-bar-current" style="height:{current[c]}%"></div><div class="ol-bar-typical" style="height:{typical[c]}%"></div><div class="ol-channel-label">{c}</div></div>'
        for c in channels
    )
    st.markdown(
        f"""
        <div class="ol-content-grid">
          <div class="ol-panel ol-reason-panel">
            <div class="ol-section-title"><div class="left">Why the event was scored this way</div><div class="link">View full evidence →</div></div>
            <div class="ol-reasons">{reason_html}</div>
          </div>
          <div class="ol-panel ol-channel-panel">
            <div class="ol-section-title"><div class="left">Channel Mix</div><div class="ol-chart-legend"><span><i class="ol-dot" style="background:{PINK}"></i>Current</span><span><i class="ol-dot" style="background:{BLUE}"></i>Typical</span></div></div>
            <div class="ol-channel-chart">{chart}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def recourse_and_twin(decision: dict, account_id: str, seeded_events: int = 0) -> None:
    options = list(decision.get("recourse_options") or [])[:4]
    icon_names = ["lock", "user", "phone", "clock"]
    option_html = []
    for i in range(4):
        if i < len(options):
            opt = options[i]
            action = str(opt.get("action", "clear")).replace("_", " ").title()
            msg = str(opt.get("description", "Safe verification option"))
            tm = str(opt.get("estimated_clearance", "Review"))
        else:
            defaults = [
                ("Trusted-channel confirmation", "Confirm through an official trusted channel", "~ 5 minutes"),
                ("Analyst review", "Investigate with full decision context", "~ 15–30 minutes"),
                ("Customer callback", "Verify identity out-of-band", "~ 10 minutes"),
                ("Estimated clearance", "Depends on the verification path", "5–30 minutes"),
            ]
            action, msg, tm = defaults[i]
        cls = "good" if i == 0 else "gold" if i == 3 else ""
        option_html.append(
            f'<div class="ol-recourse {cls}"><div class="ol-recourse-head">{icon(icon_names[i],15)}<span>{_e(action)}</span></div><div class="ol-recourse-msg">{_e(msg)}</div><div class="ol-recourse-time">{_e(tm)}</div></div>'
        )
    learning = decision.get("learning", {}) or {}
    score = decision.get("score", {}) or {}
    evidence = decision.get("evidence", {}) or {}
    st.markdown(
        f"""
        <div class="ol-recourse-grid">
          <div class="ol-panel ol-recourse-panel">
            <div class="ol-section-title"><div class="left">Safe ways to clear this</div></div>
            <div class="ol-recourse-cards">{''.join(option_html)}</div>
          </div>
          <div class="ol-panel ol-twin-panel">
            <div class="ol-section-title"><div class="left">Customer Twin <span style="color:#9095A4;font-size:.55rem">(partial view)</span></div><div class="link">View full twin →</div></div>
            <div class="ol-twin-row">
              <div class="ol-person-card"><div class="ol-person-avatar">{icon('user',17)}</div><div><div class="ol-person-id">{_e(account_id)}</div><div class="ol-person-trust">{_e(str(learning.get('trust_state','observed')).title())}</div></div></div>
              <div class="ol-twin-stat"><div class="k">History</div><div class="v">{seeded_events} seeded events</div></div>
              <div class="ol-twin-stat"><div class="k">Profile confidence</div><div class="v">{float(score.get('profile_confidence') or 0):.0%}</div></div>
              <div class="ol-twin-stat"><div class="k">Evidence mode</div><div class="v">{_e(str(evidence.get('mode','live')).title())}</div></div>
              <div class="ol-twin-stat"><div class="k">Coverage</div><div class="v">{float(evidence.get('coverage') or 0):.0%}</div></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mesh(decision: dict) -> None:
    fs = decision.get("fraud_sketch_exchange", {}) or {}
    count = int(fs.get("independent_institutions") or 0)
    score = float(fs.get("score") or 0)
    status = str(fs.get("status") or "clear").replace("_", " ").title()
    ceiling = str(fs.get("action_ceiling") or "monitor").replace("_", " ").title()
    source = str(fs.get("source_mode") or "live").replace("_", " ").title()
    matched = fs.get("matched_indicators") or []
    matched_label = ", ".join(str(x).replace("_", " ").title() for x in matched) if matched else "None"
    status_cls = "good" if score > 0 else ""
    st.markdown(
        f"""
        <div class="ol-panel ol-mesh-panel">
          <div class="ol-mesh-head">{icon('mesh',17)} Interbank Twin / OlusoMesh</div>
          <div class="ol-mesh-sub">Privacy-reduced shared fraud intelligence that supports — but never replaces — the local decision.</div>
          <div class="ol-mesh-grid">
            <div class="ol-mesh-card"><div class="k">Independent institutions</div><div class="v">{icon('bank',15)} {count}</div><div class="s">Contributing prior reports</div></div>
            <div class="ol-mesh-card {status_cls}"><div class="k">Shared signal status</div><div class="v">{icon('mesh',15)} {_e(status)}</div><div class="s">Aggregate score {score:.0%}</div></div>
            <div class="ol-mesh-card"><div class="k">Action ceiling</div><div class="v">{icon('shield',15)} {_e(ceiling)}</div><div class="s">Local corroboration governs escalation</div></div>
            <div class="ol-mesh-card"><div class="k">Source mode</div><div class="v">{icon('database',15)} {_e(source)}</div><div class="s">Rotating HMAC fraud sketches</div></div>
            <div class="ol-mesh-card"><div class="k">Matched indicator</div><div class="v">{icon('link',15)} {_e(matched_label)}</div><div class="s">No raw customer history is pooled</div></div>
            <div class="ol-mesh-story"><div class="ol-mesh-globe">{icon('globe',46)}</div><div class="ol-mesh-copy"><div class="a">Stronger together</div><div class="b">for a safer financial ecosystem.</div><div class="c">● OlusoMesh privacy-reduced exchange</div></div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def bottom_status(resilience: dict | None, review_count: int | None = None) -> None:
    resilience = resilience or {}
    mode = str(resilience.get("mode", "unknown")).title()
    mult = float(resilience.get("confidence_multiplier") or 1.0)
    queued = int(resilience.get("pending_journal_events") or 0)
    journal = resilience.get("journal_integrity", {}) or {}
    journal_valid = bool(journal.get("valid"))
    capsule = bool(resilience.get("capsule_valid"))
    ops = [
        ("queue", "Review Queue", str(review_count if review_count is not None else "—"), "Risk-prioritised cases", ""),
        ("trend", "Drift Report", "Available", "Reference-window monitoring", "ok"),
        ("equity", "Equity Report", "Available", "Current scope & limits", ""),
        ("sliders", "Policy What-If", "Ready", "Non-mutating simulation", ""),
        ("terminal", "Agent Terminal", "Online", "Integrity twin ready", "ok"),
    ]
    res = [
        ("activity", "Operating Mode", mode, "Services state", "ok" if mode.lower()=="online" else ""),
        ("bolt", "Decision Confidence", f"{mult:.2f}×", "Outage multiplier", ""),
        ("queue", "Queued Events", str(queued), "Store-and-forward journal", ""),
        ("database", "Journal Integrity", "Valid" if journal_valid else "Check", "Tamper-evident queue", "ok" if journal_valid else ""),
        ("shield", "Signed Capsule", "Intact" if capsule else "Unavailable", "Edge / shared cache", "ok" if capsule else ""),
    ]

    def render(items: list[tuple[str, str, str, str, str]]) -> str:
        return "".join(
            f'<div class="ol-mini"><div class="k">{_e(k)}</div><div class="v {tone}">{icon(ic,13)} {_e(v)}</div><div class="s">{_e(s)}</div></div>'
            for ic, k, v, s, tone in items
        )

    st.markdown(
        f"""
        <div class="ol-bottom-grid">
          <div class="ol-panel ol-bottom-panel">
            <div class="ol-section-title"><div class="left">Governance & Operations</div><div class="link">Open tools below →</div></div>
            <div class="ol-bottom-cards">{render(ops)}</div>
          </div>
          <div class="ol-panel ol-bottom-panel">
            <div class="ol-section-title"><div class="left">Resilience & Outage Management</div></div>
            <div class="ol-bottom-cards">{render(res)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state() -> None:
    st.markdown(
        f'<div class="ol-empty">{icon("shield",30)}<div class="title">Ready to score a scenario</div><div class="sub">Create the demo account, seed normal history, then score a scenario. The dashboard will populate from the real API response.</div></div>',
        unsafe_allow_html=True,
    )
