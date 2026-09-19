from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
import streamlit as st
import theme
from dotenv import load_dotenv

# Share the API's keys from the repo-root .env; real environment variables still win.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

st.set_page_config(page_title="Oluso ATO Lab", page_icon="🛡️", layout="wide")
theme.inject()

API_URL = st.sidebar.text_input("API URL", os.getenv("ATO_DASHBOARD_API_URL", "http://localhost:8000"))
API_KEY = st.sidebar.text_input(
    "API key",
    os.getenv("ATO_API_KEY", "dev-only-change-me"),
    type="password",
)
ANALYST_KEY = st.sidebar.text_input("Analyst key", os.getenv("ATO_ANALYST_API_KEY", "analyst-dev-only-change-me"), type="password")
AUDITOR_KEY = st.sidebar.text_input("Auditor key", os.getenv("ATO_AUDITOR_API_KEY", "auditor-dev-only-change-me"), type="password")
ADMIN_KEY = st.sidebar.text_input("Admin key", os.getenv("ATO_ADMIN_API_KEY", "admin-dev-only-change-me"), type="password")
TENANT_ID = st.sidebar.selectbox("Tenant", ["default", "demo-bank", "partner-bank"])
ACCOUNT_ID = st.sidebar.text_input("Account ID", "demo_customer_001")


def headers(role: str = "integration") -> dict[str, str]:
    key = (
        ANALYST_KEY
        if role == "analyst"
        else AUDITOR_KEY
        if role == "auditor"
        else ADMIN_KEY
        if role == "admin"
        else API_KEY
    )
    return {"X-API-Key": key, "X-Tenant-ID": TENANT_ID, "Content-Type": "application/json"}


def api(method: str, path: str, payload: dict[str, Any] | None = None, role: str = "integration") -> Any:
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


def new_event_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def create_demo_account() -> None:
    payload = {
        "account_id": ACCOUNT_ID,
        "display_name": "Demo Customer",
        "shared_device_allowed": False,
        "regret_limit_30d": 3,
        "trusted_contact_masked": "+234 *** *** 104",
    }
    try:
        api("POST", "/v1/accounts", payload)
        st.success("Demo account created.")
    except RuntimeError as exc:
        if "already exists" in str(exc):
            st.info("Demo account already exists.")
        else:
            raise


def seed_history() -> None:
    now = datetime.now(UTC)
    recipients = ["merchant_grocery", "utility_power", "family_amina"]
    progress = st.progress(0.0)
    for index in range(30):
        channel = "ussd" if index % 2 else "app"
        payload = {
            "event_id": new_event_id("baseline"),
            "account_id": ACCOUNT_ID,
            "occurred_at": (now - timedelta(days=30 - index, hours=index % 3)).isoformat(),
            "event_type": "paybill" if index % 3 == 0 else "purchase",
            "channel": channel,
            "amount": 1700 + (index % 5) * 250,
            "available_balance_before": 20_000,
            "recipient_id": recipients[index % len(recipients)],
            "device_id": "device_primary",
            "sim_id": "sim_primary",
            "ip_prefix": "102.88.10.0/24",
            "latitude": 6.5244,
            "longitude": 3.3792,
            "interaction_ms": 19_000 + (index % 4) * 800,
            "menu_depth": 5,
            "input_method": "typed" if channel == "app" else "unknown",
            "keystroke_interval_ms": 185 + (index % 4) * 4 if channel == "app" else None,
            "device_tilt_variance": 2.2 + (index % 3) * 0.1 if channel == "app" else None,
            "navigation_signature": "app_home_pay" if channel == "app" else "ussd_1_2_1",
            "success": True,
        }
        api("POST", "/v1/events/score", payload)
        progress.progress((index + 1) / 30)
    st.success("Thirty normal events were added to the behavioural twin.")


def scenario_payload(name: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    base = {
        "event_id": new_event_id("scenario"),
        "account_id": ACCOUNT_ID,
        "occurred_at": now.isoformat(),
        "event_type": "purchase",
        "channel": "app",
        "amount": 2200,
        "available_balance_before": 24_000,
        "recipient_id": "merchant_grocery",
        "device_id": "device_primary",
        "sim_id": "sim_primary",
        "ip_prefix": "102.88.10.0/24",
        "latitude": 6.5244,
        "longitude": 3.3792,
        "interaction_ms": 20_000,
        "menu_depth": 5,
        "input_method": "typed",
        "keystroke_interval_ms": 188,
        "device_tilt_variance": 2.3,
        "navigation_signature": "app_home_pay",
        "success": True,
    }
    if name == "Legitimate new phone":
        base.update(device_id="device_new_legitimate", ip_prefix="102.88.11.0/24")
    elif name == "Verified SIM replacement":
        base.update(sim_id="sim_verified_replacement", sim_change_verified=True)
    elif name == "SIM-swap balance drain":
        base.update(
            event_type="transfer",
            channel="ussd",
            amount=48_000,
            available_balance_before=52_000,
            recipient_id="recipient_never_seen",
            device_id="device_unknown",
            sim_id="sim_unknown",
            ip_prefix="197.210.44.0/24",
            latitude=6.5244,
            longitude=3.3792,
            interaction_ms=2_500,
            menu_depth=7,
            input_method="unknown",
            keystroke_interval_ms=None,
            device_tilt_variance=None,
            navigation_signature="ussd_9_3_1",
        )
    elif name == "USSD automation burst":
        base.update(
            event_type="transfer",
            channel="ussd",
            amount=16_000,
            recipient_id="recipient_new_ussd",
            interaction_ms=1_100,
            menu_depth=8,
            input_method="unknown",
            keystroke_interval_ms=None,
            device_tilt_variance=None,
            navigation_signature="ussd_rapid_4_4_1",
        )
    elif name == "Pasted-credential takeover":
        base.update(
            event_type="transfer",
            amount=28_000,
            recipient_id="recipient_new_paste",
            device_id="device_remote_control",
            input_method="pasted",
            keystroke_interval_ms=42,
            device_tilt_variance=0.05,
            navigation_signature="app_deeplink_transfer",
        )
    elif name == "Recovery abuse":
        recovery = {
            **base,
            "event_id": new_event_id("recovery"),
            "occurred_at": (now - timedelta(minutes=15)).isoformat(),
            "event_type": "account_recovery",
            "amount": 0,
            "available_balance_before": None,
            "recipient_id": None,
            "device_id": "device_recovery",
            "sim_id": "sim_recovery",
            "interaction_ms": None,
            "menu_depth": None,
        }
        api("POST", "/v1/events/score", recovery)
        base.update(
            event_type="transfer",
            amount=32_000,
            available_balance_before=38_000,
            recipient_id="recipient_after_recovery",
            device_id="device_recovery",
            sim_id="sim_recovery",
        )
    elif name == "Coercion-assisted transfer":
        base.update(
            event_type="transfer",
            amount=18_000,
            recipient_id="recipient_directed_by_caller",
            interaction_ms=120_000,
            coercion_signals={
                "active_call": True,
                "screen_sharing_detected": True,
                "recipient_replacements": 3,
                "confirmation_backtracks": 4,
                "amount_edits": 2,
                "pause_before_confirmation_ms": 120_000,
                "recipient_pasted_during_call": True,
                "on_device_coercion_score": 0.91,
                "consented_device_attested": True,
            },
        )
    elif name == "Cross-channel takeover":
        app_login = {
            **base,
            "event_id": new_event_id("new_app_enrolment"),
            "occurred_at": (now - timedelta(minutes=8)).isoformat(),
            "event_type": "login",
            "amount": 0,
            "available_balance_before": None,
            "recipient_id": None,
            "device_id": "device_new_channel_attacker",
            "interaction_ms": None,
            "menu_depth": None,
        }
        api("POST", "/v1/events/score", app_login)
        base.update(
            event_type="transfer",
            channel="ussd",
            amount=22_000,
            recipient_id="recipient_cross_channel",
            input_method="unknown",
            keystroke_interval_ms=None,
            device_tilt_variance=None,
            navigation_signature="ussd_1_4_2",
        )
    elif name == "Established monthly payment":
        amount = 20_000
        for days in (92, 61, 31):
            prior = {
                **base,
                "event_id": new_event_id("monthly_pattern"),
                "occurred_at": (now - timedelta(days=days)).isoformat(),
                "event_type": "transfer",
                "amount": amount,
                "recipient_id": "landlord_monthly",
            }
            api("POST", "/v1/events/score", prior)
        base.update(
            event_type="transfer",
            amount=20_000,
            recipient_id="landlord_monthly",
        )
    elif name == "Compromised agent terminal":
        terminal = "terminal_dashboard_compromised"
        assurance = {
            "agent_token": "agent_dashboard_compromised",
            "terminal_token": terminal,
            "registered_latitude": 6.5244,
            "registered_longitude": 3.3792,
            "shift_start_hour": 6,
            "shift_end_hour": 22,
            "terminal_age_days": 540,
            "gateway_attested": True,
        }
        support_accounts = [f"agent_dashboard_customer_{index:02d}" for index in range(10)]
        for account_id in support_accounts:
            try:
                api(
                    "POST",
                    "/v1/accounts",
                    {"account_id": account_id, "display_name": account_id},
                )
            except RuntimeError as exc:
                if "already exists" not in str(exc):
                    raise
        for index in range(4):
            api(
                "POST",
                "/v1/events/score",
                {
                    **base,
                    "event_id": new_event_id("agent_failed_auth"),
                    "account_id": support_accounts[index],
                    "occurred_at": (now - timedelta(minutes=9 - index)).isoformat(),
                    "event_type": "failed_login",
                    "channel": "agent",
                    "amount": 0,
                    "available_balance_before": None,
                    "recipient_id": None,
                    "device_id": f"device_{terminal}",
                    "agent_assurance": assurance,
                    "success": False,
                },
            )
        for index in range(5):
            api(
                "POST",
                "/v1/events/score",
                {
                    **base,
                    "event_id": new_event_id("agent_concentrated_transfer"),
                    "account_id": support_accounts[4 + index],
                    "occurred_at": (now - timedelta(minutes=5 - index)).isoformat(),
                    "event_type": "transfer",
                    "channel": "agent",
                    "amount": 2_000,
                    "recipient_id": "mule_agent_dashboard",
                    "device_id": f"device_{terminal}",
                    "agent_assurance": assurance,
                    "input_method": "unknown",
                    "keystroke_interval_ms": None,
                    "device_tilt_variance": None,
                    "navigation_signature": "agent_customer_transfer",
                },
            )
        base.update(
            event_type="transfer",
            channel="agent",
            amount=2_000,
            recipient_id="mule_agent_dashboard",
            device_id=f"device_{terminal}",
            input_method="unknown",
            keystroke_interval_ms=None,
            device_tilt_variance=None,
            navigation_signature="agent_customer_transfer",
            agent_assurance=assurance,
        )
    return base


def status_chips() -> list[tuple[str, str]]:
    """Live service state for the brand bar. A dead API must look dead, not absent."""

    chips: list[tuple[str, str]] = [("Synthetic data only", "warn")]
    try:
        health = requests.get(f"{API_URL.rstrip('/')}/health", timeout=5).json()
    except (requests.RequestException, ValueError):
        return [("API <strong>unreachable</strong>", "warn"), *chips]
    mode = str(health.get("resilience_mode", "unknown"))
    chips = [
        (f"Mode <strong>{mode.upper()}</strong>", "live" if mode == "online" else "warn"),
        (f"Model <strong>{'loaded' if health.get('model_available') else 'missing'}</strong>", ""),
        (
            f"Audit chain <strong>{'valid' if health.get('audit_chain_valid') else 'broken'}</strong>",
            "" if health.get("audit_chain_valid") else "warn",
        ),
        *chips,
    ]
    return chips


theme.topbar(status_chips())
st.caption(
    "Auditable scoring for app, USSD and agency activity, including private cross-bank fraud sketches. "
    "All interventions are reversible and constrained by a Regret Budget."
)

theme.section("Set up the demonstration")
setup_one, setup_two, setup_three = st.columns(3)
with setup_one:
    if st.button("1 · Create demo account", use_container_width=True):
        try:
            create_demo_account()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
with setup_two:
    if st.button("2 · Seed normal history", use_container_width=True):
        try:
            seed_history()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
with setup_three:
    if st.button("Verify audit chain", use_container_width=True):
        try:
            result = api("GET", "/v1/audit/verify", role="auditor")
            st.success(f"Valid: {result['valid']} · Entries: {result['entries_checked']}")
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))

theme.section("Score a scenario")
scenario_panel = st.container(border=True)
scenario_field, scenario_action = scenario_panel.columns([3, 1], vertical_alignment="bottom")
scenario = scenario_field.selectbox(
    "Scenario",
    [
        "Normal purchase",
        "Legitimate new phone",
        "Verified SIM replacement",
        "SIM-swap balance drain",
        "USSD automation burst",
        "Pasted-credential takeover",
        "Recovery abuse",
        "Coercion-assisted transfer",
        "Cross-channel takeover",
        "Established monthly payment",
        "Compromised agent terminal",
    ],
)

if scenario_action.button("Score scenario", type="primary", use_container_width=True):
    try:
        decision = api("POST", "/v1/events/score", scenario_payload(scenario))
        st.session_state["last_decision"] = decision
    except (requests.RequestException, RuntimeError) as exc:
        st.error(str(exc))

decision = st.session_state.get("last_decision")
if decision:
    score = decision["score"]
    policy = decision["policy"]
    confidence = decision["decision_confidence"]
    resilience = decision.get("resilience", {})
    theme.hero(
        decision["risk_level"],
        score["fused_score"],
        policy["action"].replace("_", " ").title(),
        decision["customer_explanation"],
        confidence["score"],
    )
    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    metric_one.metric("Model score", f"{score['model_score']:.1%}" if score.get("model_score") is not None else "n/a")
    metric_two.metric("Anomaly score", f"{score['anomaly_score']:.1%}")
    metric_three.metric("Profile confidence", f"{score['profile_confidence']:.1%}")
    metric_four.metric("Hold", f"{policy['hold_seconds'] // 60} min" if policy["hold_seconds"] else "None")

    if resilience.get("mode", "online") != "online":
        st.warning(
            f"Outage mode: {resilience['mode'].upper()} · confidence multiplier "
            f"{resilience.get('confidence_multiplier', 1):.0%} · "
            f"missing: {', '.join(resilience.get('unavailable_sources', [])) or 'none'}"
        )
        if resilience.get("offline_reference"):
            st.info(f"Connectivity-safe reference: {resilience['offline_reference']}")

    if confidence["level"] == "low":
        st.warning("Low decision confidence: safe does not mean known. " + confidence["reasons"][0])
    reputation = decision.get("recipient_reputation", {})
    campaign = decision.get("campaign", {})
    agent_terminal = decision.get("agent_terminal", {})
    fraud_sketch = decision.get("fraud_sketch_exchange", {})
    if campaign.get("eligible"):
        st.error(
            f"Campaign DNA: {campaign['distinct_accounts']} accounts · "
            f"score {campaign['score']:.1%} · {', '.join(campaign['stages'])}"
        )
    learning = decision.get("learning", {})
    st.caption(
        f"Learning state: {learning.get('trust_state', 'legacy')} · "
        f"transaction lifecycle: {decision.get('transaction_state', 'legacy')}"
    )
    if reputation.get("confirmed_reports", 0):
        st.warning(
            f"Recipient watchlist: {reputation['status']} · "
            f"{reputation['confirmed_reports']} confirmed report(s) across "
            f"{reputation['distinct_accounts']} account(s)"
        )
    if agent_terminal.get("evidence_available"):
        terminal_message = (
            f"Agent-terminal integrity: {agent_terminal['status']} · "
            f"{agent_terminal['customer_diversity_1h']:.0f} customers in 1h · "
            f"recipient concentration {agent_terminal['recipient_concentration_24h']:.0%}"
        )
        if agent_terminal.get("quarantined"):
            st.error(terminal_message + " · QUARANTINED")
        elif "AGENT_TERMINAL_CAMPAIGN" in [reason["code"] for reason in decision["reasons"]]:
            st.warning(terminal_message + " · campaign pattern detected")
        else:
            st.info(terminal_message)
    if fraud_sketch.get("score", 0):
        sketch_message = (
            f"OlusoMesh private exchange: {fraud_sketch['status']} · "
            f"{fraud_sketch['independent_institutions']} independent institution(s) · "
            f"score {fraud_sketch['score']:.1%} · "
            f"source {fraud_sketch['source_mode']} · ceiling {fraud_sketch['action_ceiling']}"
        )
        if fraud_sketch.get("local_corroboration"):
            st.warning(sketch_message + " · locally corroborated")
        else:
            st.info(sketch_message + " · monitoring only")

    if decision.get("uncertainty_note"):
        st.info(decision["uncertainty_note"])
    st.caption(
        f"Evidence mode: {decision['evidence']['mode']} · "
        f"coverage {decision['evidence']['coverage']:.0%}"
    )
    risk_window = decision.get("risk_window", {})
    if risk_window.get("state") != "clear":
        st.warning(
            f"Account risk window: {risk_window['state']} · "
            f"{risk_window['hours_remaining']:.1f} hours remaining"
        )
    theme.section("Why the event was scored this way")
    for item in decision["reasons"]:
        theme.reason(item["code"], item["message"])

    if decision.get("recourse_options"):
        theme.section("Safe ways to clear this")
        for option in decision["recourse_options"]:
            theme.reason(
                option["action"].replace("_", " ").upper(),
                f"{option['description']} — {option['estimated_clearance']} "
                f"via {option['safe_channel']}",
            )

    with st.expander("Policy and technical detail"):
        st.json(
            {
                "decision_id": decision["decision_id"],
                "model": score["model_version"],
                "model_score": score["model_score"],
                "anomaly_score": score["anomaly_score"],
                "policy": policy,
                "risk_window": decision.get("risk_window"),
                "decision_confidence": confidence,
                "recipient_reputation": reputation,
                "campaign": campaign,
                "agent_terminal": agent_terminal,
                "fraud_sketch_exchange": fraud_sketch,
                "learning": learning,
                "provenance": decision.get("provenance"),
                "transaction_state": decision.get("transaction_state"),
                "resilience": resilience,
                "recourse_options": decision.get("recourse_options"),
                "features": decision["feature_snapshot"],
                "audit_hash": decision["audit_hash"],
            }
        )
    if st.button("Confirm fraud and update recipient watchlist", use_container_width=True):
        try:
            update = api(
                "POST",
                f"/v1/decisions/{decision['decision_id']}/feedback",
                {
                    "label": "account_takeover",
                    "analyst_id": "demo_analyst",
                    "notes": "Confirmed during the live demonstration.",
                },
                role="analyst",
            )
            st.success(
                "Feedback propagated. Recipient: "
                f"{update.get('recipient_reputation_update')} · agent terminal: "
                f"{update.get('agent_terminal_reputation_update')}"
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))

theme.section("Governance and operations")
ops_one, ops_two, ops_three, ops_four = st.columns(4)
with ops_one:
    if st.button("Review queue", use_container_width=True):
        try:
            st.json(api("GET", "/v1/cases", role="analyst"))
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))

with ops_two:
    if st.button("Drift report", use_container_width=True):
        try:
            st.json(api("GET", "/v1/governance/drift", role="auditor"))
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
with ops_three:
    if st.button("Equity report", use_container_width=True):
        try:
            st.json(api("GET", "/v1/governance/equity", role="auditor"))
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
with ops_four:
    if st.button("Policy what-if", use_container_width=True):
        try:
            st.json(api("POST", "/v1/policy/simulate", {}, role="auditor"))
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))

theme.section("Agent-terminal investigation")
terminal_lookup = st.text_input("Gateway terminal token", "terminal_dashboard_compromised")
if st.button("Check terminal reputation", use_container_width=True):
    try:
        st.json(api("GET", f"/v1/agent-terminals/{terminal_lookup}/status", role="analyst"))
    except (requests.RequestException, RuntimeError) as exc:
        st.error(str(exc))

theme.section("Power and network outage resilience")
try:
    outage_status = api("GET", "/v1/resilience/status")
    status_one, status_two, status_three, status_four = st.columns(4)
    status_one.metric("Operating mode", outage_status["mode"].upper())
    status_two.metric("Decision confidence", f"{outage_status['confidence_multiplier']:.0%}")
    status_three.metric("Queued events", outage_status["pending_journal_events"])
    status_four.metric(
        "Journal integrity",
        "VALID" if outage_status["journal_integrity"]["valid"] else "INVALID",
    )
    st.caption(
        "A signed edge capsule remains "
        + ("valid" if outage_status.get("capsule_valid") else "invalid")
        + "; unavailable evidence is never interpreted as safe."
    )
except (requests.RequestException, RuntimeError) as exc:
    st.info(f"Outage status unavailable: {exc}")

outage_one, outage_two, outage_three, outage_four = st.columns(4)
with outage_one:
    if st.button("Simulate degraded intelligence", use_container_width=True):
        try:
            st.json(api("POST", "/v1/resilience/simulate", {"mode": "degraded"}, role="admin"))
            st.rerun()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
with outage_two:
    if st.button("Simulate payment-rail outage", use_container_width=True):
        try:
            st.json(api("POST", "/v1/resilience/simulate", {"mode": "isolated"}, role="admin"))
            st.rerun()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
with outage_three:
    if st.button("Restore trusted services", use_container_width=True):
        try:
            st.json(api("POST", "/v1/resilience/simulate", {"mode": "online"}, role="admin"))
            st.rerun()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
with outage_four:
    if st.button("Verify and reconcile", use_container_width=True):
        try:
            st.json(api("POST", "/v1/resilience/reconcile", {"batch_size": 100}, role="auditor"))
            st.rerun()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))

profile_column, history_column = st.columns(2)
with profile_column:
    theme.section("Behavioural twin")
    if st.button("Refresh profile"):
        try:
            st.session_state["profile"] = api("GET", f"/v1/accounts/{ACCOUNT_ID}/profile")
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if st.session_state.get("profile"):
        st.json(st.session_state["profile"])

with history_column:
    theme.section("Recent decisions")
    if st.button("Refresh decisions"):
        try:
            st.session_state["decisions"] = api(
                "GET", f"/v1/accounts/{ACCOUNT_ID}/decisions?limit=12"
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    for item in st.session_state.get("decisions", []):
        theme.decision_row(
            item["risk_level"],
            item["score"]["fused_score"],
            item["policy"]["action"].replace("_", " "),
        )
