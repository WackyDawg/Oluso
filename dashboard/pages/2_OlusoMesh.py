from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import streamlit as st
from dotenv import load_dotenv

# Make dashboard/theme.py importable when Streamlit executes this page directly.
DASHBOARD_DIR = Path(__file__).resolve().parents[1]
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

import theme  # noqa: E402
from oluso.fraud_sketch import sign_report, sign_revocation  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

st.set_page_config(page_title="OlusoMesh · Oluso ATO Lab", page_icon="🔗", layout="wide")
theme.inject()

API_URL = st.sidebar.text_input(
    "API URL",
    os.getenv("ATO_DASHBOARD_API_URL", "http://localhost:8000"),
    key="mesh_api_url",
)
ANALYST_KEY = st.sidebar.text_input(
    "Analyst key",
    os.getenv("ATO_ANALYST_API_KEY", "analyst-dev-only-change-me"),
    type="password",
    key="mesh_analyst_key",
)
INTEGRATION_KEY = st.sidebar.text_input(
    "Integration key",
    os.getenv("ATO_API_KEY", "dev-only-change-me"),
    type="password",
    key="mesh_integration_key",
)
TENANT_ID = st.sidebar.selectbox(
    "Tenant",
    ["default", "demo-bank", "partner-bank"],
    key="mesh_tenant",
)

DEFAULT_INSTITUTION_KEYS = {
    "bank-a": "bank-a-sketch-signing-dev-only-change-me",
    "bank-b": "bank-b-sketch-signing-dev-only-change-me",
    "bank-c": "bank-c-sketch-signing-dev-only-change-me",
}


def institution_keys() -> dict[str, str]:
    raw = os.getenv("ATO_FRAUD_SKETCH_INSTITUTION_KEYS", "")
    if not raw:
        return DEFAULT_INSTITUTION_KEYS
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return DEFAULT_INSTITUTION_KEYS
    return {str(k): str(v) for k, v in parsed.items()}


INSTITUTION_KEYS = institution_keys()


def headers(role: str = "analyst") -> dict[str, str]:
    key = ANALYST_KEY if role == "analyst" else INTEGRATION_KEY
    return {
        "X-API-Key": key,
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json",
    }


def api(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    role: str = "analyst",
) -> Any:
    response = requests.request(
        method,
        f"{API_URL.rstrip('/')}{path}",
        headers=headers(role),
        json=payload,
        timeout=30,
    )
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"API {response.status_code}: {detail}")
    return response.json()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def current_indicator() -> str:
    if "mesh_indicator" not in st.session_state:
        st.session_state["mesh_indicator"] = f"icsc-mule-{uuid.uuid4().hex[:8]}"
    return str(st.session_state["mesh_indicator"])


def reset_demo() -> None:
    st.session_state["mesh_indicator"] = f"icsc-mule-{uuid.uuid4().hex[:8]}"
    for key in (
        "mesh_bank_a_report",
        "mesh_bank_b_report",
        "mesh_last_status",
        "mesh_local_decision",
        "mesh_seeded_account",
        "mesh_revocation",
    ):
        st.session_state.pop(key, None)


def fraud_sketch_status(indicator: str) -> dict[str, Any]:
    path = (
        "/v1/fraud-sketch/status?indicator_type=recipient&indicator_value="
        + quote(indicator, safe="")
    )
    return api("GET", path, role="analyst")


def submit_report(institution_id: str, indicator: str) -> dict[str, Any]:
    if institution_id not in INSTITUTION_KEYS:
        raise RuntimeError(f"No signing key configured for {institution_id}")
    observed_at = datetime.now(UTC)
    payload_for_signature: dict[str, Any] = {
        "report_id": new_id(f"mesh-{institution_id}"),
        "institution_id": institution_id,
        "indicator_type": "recipient",
        "indicator_value": indicator,
        "confidence": 0.91,
        "evidence_class": "verified_account_takeover",
        "observed_at": observed_at,
        "ttl_hours": 168,
        "nonce": new_id(f"nonce-{institution_id}"),
    }
    signature = sign_report(payload_for_signature, INSTITUTION_KEYS[institution_id])
    outgoing = {
        **payload_for_signature,
        "observed_at": observed_at.isoformat(),
        "signature": signature,
    }
    result = api("POST", "/v1/fraud-sketch/reports", outgoing, role="analyst")
    return {"request": outgoing, "result": result}


def ensure_mesh_account(indicator: str) -> str:
    suffix = "".join(ch for ch in indicator if ch.isalnum())[-14:]
    account_id = f"mesh_demo_{suffix}"
    if st.session_state.get("mesh_seeded_account") == account_id:
        return account_id

    try:
        api(
            "POST",
            "/v1/accounts",
            {
                "account_id": account_id,
                "display_name": "OlusoMesh Demo Customer",
                "shared_device_allowed": False,
                "regret_limit_30d": 3,
                "trusted_contact_masked": "+234 *** *** 104",
            },
            role="integration",
        )
    except RuntimeError as exc:
        if "already exists" not in str(exc).lower():
            raise

    now = datetime.now(UTC)
    for index in range(10):
        api(
            "POST",
            "/v1/events/score",
            {
                "event_id": new_id("mesh-history"),
                "account_id": account_id,
                "occurred_at": (now - timedelta(days=12 - index)).isoformat(),
                "event_type": "purchase",
                "channel": "app",
                "amount": 2200,
                "available_balance_before": 120000,
                "recipient_id": "ordinary-market-merchant",
                "device_id": "trusted-device",
                "sim_id": "trusted-sim",
                "ip_prefix": "102.88.10.0/24",
                "latitude": 6.5244,
                "longitude": 3.3792,
                "interaction_ms": 9000,
                "menu_depth": 5,
                "input_method": "typed",
                "keystroke_interval_ms": 185,
                "device_tilt_variance": 2.2,
                "navigation_signature": "app_home_pay",
                "success": True,
            },
            role="integration",
        )
    st.session_state["mesh_seeded_account"] = account_id
    return account_id


def score_local_corroboration(indicator: str) -> dict[str, Any]:
    account_id = ensure_mesh_account(indicator)
    now = datetime.now(UTC)
    return api(
        "POST",
        "/v1/events/score",
        {
            "event_id": new_id("mesh-corroborated"),
            "account_id": account_id,
            "occurred_at": now.isoformat(),
            "event_type": "transfer",
            "channel": "app",
            "amount": 48000,
            "available_balance_before": 100000,
            "recipient_id": indicator,
            "device_id": "new-remote-device",
            "sim_id": "trusted-sim",
            "ip_prefix": "197.210.44.0/24",
            "latitude": 6.5244,
            "longitude": 3.3792,
            "interaction_ms": 2400,
            "menu_depth": 7,
            "input_method": "pasted",
            "keystroke_interval_ms": 42,
            "device_tilt_variance": 0.05,
            "navigation_signature": "app_deeplink_transfer",
            "success": True,
        },
        role="integration",
    )


def revoke_bank_b() -> dict[str, Any]:
    stored = st.session_state.get("mesh_bank_b_report")
    if not stored:
        raise RuntimeError("Create the Bank B report first.")
    request = stored["request"]
    report_id = str(request["report_id"])
    revoked_at = datetime.now(UTC)
    material: dict[str, Any] = {
        "report_id": report_id,
        "institution_id": "bank-b",
        "reason": "Competition demo correction after analyst review",
        "revoked_at": revoked_at,
        "nonce": new_id("mesh-revoke-bank-b"),
    }
    signature = sign_revocation(material, INSTITUTION_KEYS["bank-b"])
    body = {
        "institution_id": "bank-b",
        "reason": material["reason"],
        "revoked_at": revoked_at.isoformat(),
        "nonce": material["nonce"],
        "signature": signature,
    }
    return api(
        "POST",
        f"/v1/fraud-sketch/reports/{quote(report_id, safe='')}/revoke",
        body,
        role="analyst",
    )


st.markdown(
    """
<style>
.mesh-hero {background:linear-gradient(135deg,#15171A,#1B1E22);border:1px solid #333740;border-radius:22px;padding:24px 26px;margin-bottom:18px}
.mesh-kicker {font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:#D2F34C;font-weight:700}
.mesh-title {font-size:2rem;font-weight:700;color:#F3F5F6;letter-spacing:-.03em;margin:.25rem 0 .4rem}
.mesh-sub {color:#9AA0AA;max-width:920px;line-height:1.6;font-size:.92rem}
.mesh-flow {display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0 18px}
.mesh-step {background:#1B1E22;border:1px solid #30343B;border-radius:16px;padding:14px}
.mesh-step .n {color:#D2F34C;font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;font-weight:700}
.mesh-step .t {color:#F3F5F6;font-size:.88rem;font-weight:600;margin-top:5px}
.mesh-step .s {color:#878E97;font-size:.72rem;margin-top:4px;line-height:1.35}
.mesh-privacy {background:#121416;border:1px solid #30343B;border-radius:16px;padding:14px 16px;color:#A3A9B2;font-size:.8rem;line-height:1.55;margin-bottom:14px}
.mesh-privacy strong {color:#F3F5F6}
.mesh-result {background:#15171A;border:1px solid #30343B;border-radius:18px;padding:16px 18px;margin-top:12px}
.mesh-result .headline {color:#F3F5F6;font-weight:600;font-size:1rem}
.mesh-result .detail {color:#9299A3;font-size:.8rem;line-height:1.55;margin-top:4px}
.mesh-good {color:#D2F34C!important}.mesh-warn {color:#FFC46B!important}
@media (max-width:900px){.mesh-flow{grid-template-columns:1fr 1fr}}
</style>
<div class="mesh-hero">
  <div class="mesh-kicker">Interbank Twin · OlusoMesh</div>
  <div class="mesh-title">Private fraud intelligence across institutions</div>
  <div class="mesh-sub">Each bank keeps its customer behavioural twin locally. OlusoMesh exchanges rotating, signed fraud sketches for shared attacker infrastructure — such as mule recipients — and deliberately caps shared evidence until the receiving bank sees local corroboration.</div>
</div>
<div class="mesh-flow">
  <div class="mesh-step"><div class="n">01 · Bank A</div><div class="t">Signed prior report</div><div class="s">One institution remains observe-only.</div></div>
  <div class="mesh-step"><div class="n">02 · Bank B</div><div class="t">Independent corroboration</div><div class="s">Institution diversity raises shared confidence.</div></div>
  <div class="mesh-step"><div class="n">03 · Local twin</div><div class="t">Customer-side evidence</div><div class="s">Suspicious local behaviour corroborates the shared signal.</div></div>
  <div class="mesh-step"><div class="n">04 · Reversible action</div><div class="t">Delay, not blacklist</div><div class="s">Shared evidence cannot silently become a permanent block.</div></div>
</div>
<div class="mesh-privacy"><strong>Privacy boundary:</strong> the exchange does not pool customer names, BVNs, phone numbers, account histories, device IDs, SIM IDs or transaction histories. The prototype stores rotating indicator tokens, tokenised institutions, bounded confidence/evidence class, timestamps, expiry and revocation state.</div>
""",
    unsafe_allow_html=True,
)

indicator = current_indicator()
indicator_col, reset_col = st.columns([4, 1], vertical_alignment="bottom")
indicator_col.text_input(
    "Demo recipient indicator",
    indicator,
    disabled=True,
    help="A fresh synthetic mule-recipient identifier used only for this demonstration.",
)
if reset_col.button("Start fresh demo", use_container_width=True):
    reset_demo()
    st.rerun()

# Always fetch the live aggregate, including the initial clear state.
try:
    live_status = fraud_sketch_status(indicator)
    st.session_state["mesh_last_status"] = live_status
except (requests.RequestException, RuntimeError) as exc:
    live_status = st.session_state.get("mesh_last_status") or {
        "score": 0.0,
        "confidence": 0.0,
        "independent_institutions": 0,
        "active_reports": 0,
        "status": "unavailable",
        "expires_at": None,
    }
    st.warning(f"OlusoMesh status unavailable: {exc}")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Shared score", f"{float(live_status.get('score') or 0):.1%}")
m2.metric("Independent banks", int(live_status.get("independent_institutions") or 0))
m3.metric("Active reports", int(live_status.get("active_reports") or 0))
m4.metric("Exchange state", str(live_status.get("status") or "clear").replace("_", " ").title())

st.caption(
    "Competition flow: submit Bank A, then Bank B, then score the local corroboration. "
    "Use revocation last to demonstrate correction rather than a permanent blacklist."
)

bank_a_col, bank_b_col, local_col, revoke_col = st.columns(4)
if bank_a_col.button(
    "1 · Submit Bank A report",
    use_container_width=True,
    disabled=bool(st.session_state.get("mesh_bank_a_report")),
):
    try:
        st.session_state["mesh_bank_a_report"] = submit_report("bank-a", indicator)
        st.session_state["mesh_last_status"] = fraud_sketch_status(indicator)
        st.rerun()
    except (requests.RequestException, RuntimeError) as exc:
        st.error(str(exc))

if bank_b_col.button(
    "2 · Submit Bank B report",
    use_container_width=True,
    disabled=bool(st.session_state.get("mesh_bank_b_report")),
):
    try:
        st.session_state["mesh_bank_b_report"] = submit_report("bank-b", indicator)
        st.session_state["mesh_last_status"] = fraud_sketch_status(indicator)
        st.rerun()
    except (requests.RequestException, RuntimeError) as exc:
        st.error(str(exc))

if local_col.button(
    "3 · Score local corroboration",
    type="primary",
    use_container_width=True,
    disabled=not bool(st.session_state.get("mesh_bank_b_report")),
):
    try:
        st.session_state["mesh_local_decision"] = score_local_corroboration(indicator)
        st.rerun()
    except (requests.RequestException, RuntimeError) as exc:
        st.error(str(exc))

if revoke_col.button(
    "4 · Revoke Bank B report",
    use_container_width=True,
    disabled=not bool(st.session_state.get("mesh_bank_b_report"))
    or bool(st.session_state.get("mesh_revocation")),
):
    try:
        st.session_state["mesh_revocation"] = revoke_bank_b()
        st.session_state["mesh_last_status"] = fraud_sketch_status(indicator)
        st.rerun()
    except (requests.RequestException, RuntimeError) as exc:
        st.error(str(exc))

# Narrative evidence after each step.
a_report = st.session_state.get("mesh_bank_a_report")
b_report = st.session_state.get("mesh_bank_b_report")
local_decision = st.session_state.get("mesh_local_decision")
revocation = st.session_state.get("mesh_revocation")

if a_report and not b_report:
    result = a_report.get("result", {})
    st.markdown(
        f'<div class="mesh-result"><div class="headline">Bank A reported the recipient · <span class="mesh-warn">observe only</span></div><div class="detail">The exchange now has {int(result.get("independent_institutions") or 1)} independent institution. A single bank is deliberately insufficient for a disruptive customer action.</div></div>',
        unsafe_allow_html=True,
    )

if b_report:
    status = st.session_state.get("mesh_last_status", live_status)
    st.markdown(
        f'<div class="mesh-result"><div class="headline">Bank B independently corroborated the indicator</div><div class="detail">Shared score: {float(status.get("score") or 0):.1%} · independent institutions: {int(status.get("independent_institutions") or 0)}. Without suspicious local customer behaviour, the interbank evidence remains action-capped at monitoring.</div></div>',
        unsafe_allow_html=True,
    )

if local_decision:
    fs = local_decision.get("fraud_sketch_exchange", {}) or {}
    policy = local_decision.get("policy", {}) or {}
    score = local_decision.get("score", {}) or {}
    st.markdown(
        f'<div class="mesh-result"><div class="headline">Local twin corroboration · <span class="mesh-good">{str(policy.get("action") or "decision").replace("_", " ").title()}</span></div><div class="detail">Local fused risk: {float(score.get("fused_score") or 0):.1%} · exchange institutions: {int(fs.get("independent_institutions") or 0)} · exchange ceiling: {str(fs.get("action_ceiling") or "monitor").replace("_", " ").title()} · local corroboration: {"yes" if fs.get("local_corroboration") else "no"}. The interbank twin supports the local decision; it does not replace it.</div></div>',
        unsafe_allow_html=True,
    )
    with st.expander("Local decision evidence"):
        st.json(
            {
                "risk_level": local_decision.get("risk_level"),
                "score": local_decision.get("score"),
                "policy": local_decision.get("policy"),
                "fraud_sketch_exchange": fs,
                "reasons": local_decision.get("reasons"),
                "customer_explanation": local_decision.get("customer_explanation"),
            }
        )

if revocation:
    status = st.session_state.get("mesh_last_status", live_status)
    st.markdown(
        f'<div class="mesh-result"><div class="headline">Bank B correction accepted · <span class="mesh-good">revoked</span></div><div class="detail">Independent institutions remaining: {int(status.get("independent_institutions") or 0)} · shared score after correction: {float(status.get("score") or 0):.1%}. This demonstrates that OlusoMesh is a correctable decision-support exchange, not a permanent blacklist.</div></div>',
        unsafe_allow_html=True,
    )

with st.expander("Technical / privacy proof", expanded=False):
    st.write(
        "The API response never exposes rotating indicator tokens or institution tokens. "
        "Reports are institution-signed, replay-nonce protected, time-limited and revocable."
    )
    st.json(
        {
            "indicator_type": "recipient",
            "indicator_value": "hidden from shared storage after tokenisation",
            "current_exchange_status": st.session_state.get("mesh_last_status", live_status),
            "bank_a_report_id": (a_report or {}).get("request", {}).get("report_id"),
            "bank_b_report_id": (b_report or {}).get("request", {}).get("report_id"),
            "bank_b_revoked": bool(revocation),
        }
    )
