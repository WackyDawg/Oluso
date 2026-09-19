from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
import streamlit as st

import theme

st.set_page_config(
    page_title="Oluso ATO Lab",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)
theme.inject()

selected_tenant = st.session_state.get("tenant_select", "default")
theme.sidebar(selected_tenant)

with st.sidebar.expander("Connection settings", expanded=False):
    API_URL = st.text_input(
        "API URL",
        os.getenv("ATO_DASHBOARD_API_URL", "http://localhost:8000"),
    )
    API_KEY = st.text_input(
        "Integration key",
        os.getenv("ATO_API_KEY", "dev-only-change-me"),
        type="password",
    )
    ANALYST_KEY = st.text_input(
        "Analyst key",
        os.getenv("ATO_ANALYST_API_KEY", "analyst-dev-only-change-me"),
        type="password",
    )
    AUDITOR_KEY = st.text_input(
        "Auditor key",
        os.getenv("ATO_AUDITOR_API_KEY", "auditor-dev-only-change-me"),
        type="password",
    )
    ADMIN_KEY = st.text_input(
        "Admin key",
        os.getenv("ATO_ADMIN_API_KEY", "admin-dev-only-change-me"),
        type="password",
    )
    TENANT_ID = st.selectbox(
        "Tenant",
        ["default", "demo-bank", "partner-bank"],
        key="tenant_select",
    )
    ACCOUNT_ID = st.text_input("Account ID", "demo_customer_001")

SCENARIOS = [
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
]


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
    return {
        "X-API-Key": key,
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json",
    }


def api(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    role: str = "integration",
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


def health() -> dict[str, Any]:
    try:
        response = requests.get(f"{API_URL.rstrip('/')}/health", timeout=5)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return {
            "resilience_mode": "offline",
            "model_available": False,
            "audit_chain_valid": False,
        }


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
        st.session_state["demo_account_ready"] = True
        st.toast("Demo account created", icon="✅")
    except RuntimeError as exc:
        if "already exists" in str(exc):
            st.session_state["demo_account_ready"] = True
            st.toast("Demo account already exists", icon="ℹ️")
        else:
            raise


def seed_history() -> None:
    now = datetime.now(UTC)
    recipients = ["merchant_grocery", "utility_power", "family_amina"]
    progress = st.progress(0.0, text="Building the behavioural twin…")
    for index in range(30):
        channel = "ussd" if index % 2 else "app"
        payload = {
            "event_id": new_event_id("baseline"),
            "account_id": ACCOUNT_ID,
            "occurred_at": (
                now - timedelta(days=30 - index, hours=index % 3)
            ).isoformat(),
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
            "keystroke_interval_ms": (
                185 + (index % 4) * 4 if channel == "app" else None
            ),
            "device_tilt_variance": (
                2.2 + (index % 3) * 0.1 if channel == "app" else None
            ),
            "navigation_signature": (
                "app_home_pay" if channel == "app" else "ussd_1_2_1"
            ),
            "success": True,
        }
        api("POST", "/v1/events/score", payload)
        progress.progress(
            (index + 1) / 30,
            text=f"Building the behavioural twin… {index + 1}/30",
        )
    progress.empty()
    st.session_state["seeded_events"] = 30
    st.toast("Thirty normal events added to the behavioural twin", icon="✅")


def scenario_payload(name: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    base: dict[str, Any] = {
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
        base.update(
            device_id="device_new_legitimate",
            ip_prefix="102.88.11.0/24",
        )
    elif name == "Verified SIM replacement":
        base.update(
            sim_id="sim_verified_replacement",
            sim_change_verified=True,
        )
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
            telco_assurance={
                "imsi_changed": True,
                "iccid_changed": True,
                "sim_type_changed": True,
                "sim_activation_age_hours": 1.5,
                "sim_changes_30d": 2,
                "previous_sim_tenure_days": 640,
                "otp_to_sim_change_minutes": 12,
                "otp_sim_geo_distance_km": 510,
                "gateway_attested": True,
            },
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
        for days in (92, 61, 31):
            prior = {
                **base,
                "event_id": new_event_id("monthly_pattern"),
                "occurred_at": (now - timedelta(days=days)).isoformat(),
                "event_type": "transfer",
                "amount": 20_000,
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
        support_accounts = [
            f"agent_dashboard_customer_{index:02d}" for index in range(10)
        ]
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
                    "occurred_at": (
                        now - timedelta(minutes=9 - index)
                    ).isoformat(),
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
                    "occurred_at": (
                        now - timedelta(minutes=5 - index)
                    ).isoformat(),
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


def scenario_channel(name: str) -> str:
    if name in {
        "SIM-swap balance drain",
        "USSD automation burst",
        "Cross-channel takeover",
    }:
        return "ussd"
    if name == "Compromised agent terminal":
        return "agent"
    return "app"


health_state = health()
theme.topbar(health_state)

control = st.container(border=True)
with control:
    (
        scenario_col,
        create_col,
        seed_col,
        audit_col,
        score_col,
    ) = st.columns(
        [2.6, 1.1, 1.1, 1.1, 1.15],
        vertical_alignment="bottom",
    )
    scenario = scenario_col.selectbox("Scenario", SCENARIOS, index=3)
    if create_col.button("＋ Create Demo Account", use_container_width=True):
        try:
            create_demo_account()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if seed_col.button("▣ Seed Normal History", use_container_width=True):
        try:
            seed_history()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if audit_col.button("✓ Verify Audit Chain", use_container_width=True):
        try:
            result = api("GET", "/v1/audit/verify", role="auditor")
            st.toast(
                f"Audit chain valid: {result['valid']} · "
                f"{result['entries_checked']} entries",
                icon="🛡️",
            )
            st.session_state["audit_result"] = result
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if score_col.button(
        "▶ Score Scenario",
        type="primary",
        use_container_width=True,
    ):
        try:
            decision = api(
                "POST",
                "/v1/events/score",
                scenario_payload(scenario),
            )
            st.session_state["last_decision"] = decision
            history = list(st.session_state.get("risk_history", []))
            history.append(float(decision.get("score", {}).get("fused_score") or 0))
            st.session_state["risk_history"] = history[-18:]
            st.session_state["last_scenario"] = scenario
            st.toast("Scenario scored", icon="🛡️")
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))

try:
    resilience_status = api("GET", "/v1/resilience/status")
except (requests.RequestException, RuntimeError):
    resilience_status = {
        "mode": health_state.get("resilience_mode", "unknown"),
        "confidence_multiplier": 1.0,
        "pending_journal_events": 0,
        "journal_integrity": {
            "valid": bool(health_state.get("audit_chain_valid"))
        },
        "capsule_valid": False,
    }

try:
    review_cases = api("GET", "/v1/cases", role="analyst")
    if isinstance(review_cases, list):
        review_count = len(review_cases)
    else:
        review_count = len(review_cases.get("cases", []))
except (requests.RequestException, RuntimeError, AttributeError):
    review_count = None

decision = st.session_state.get("last_decision")
if decision:
    current_scenario = st.session_state.get("last_scenario", scenario)
    theme.decision_hero(
        decision,
        list(st.session_state.get("risk_history", [])),
    )
    theme.metrics(decision)
    theme.reasons_and_channels(
        decision,
        scenario_channel(current_scenario),
    )
    theme.recourse_and_twin(
        decision,
        ACCOUNT_ID,
        int(st.session_state.get("seeded_events", 0)),
    )
    theme.mesh(decision)
else:
    theme.empty_state()

theme.bottom_status(resilience_status, review_count)

with st.expander("Analyst & decision tools", expanded=False):
    analyst_one, analyst_two, analyst_three, analyst_four = st.columns(4)
    if analyst_one.button(
        "Confirm fraud feedback",
        use_container_width=True,
        disabled=decision is None,
    ):
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
            st.session_state["feedback_result"] = update
            st.toast("Fraud feedback propagated", icon="✅")
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if analyst_two.button("Refresh customer twin", use_container_width=True):
        try:
            st.session_state["profile"] = api(
                "GET",
                f"/v1/accounts/{ACCOUNT_ID}/profile",
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if analyst_three.button("Refresh decisions", use_container_width=True):
        try:
            st.session_state["decisions"] = api(
                "GET",
                f"/v1/accounts/{ACCOUNT_ID}/decisions?limit=12",
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    terminal_lookup = analyst_four.text_input(
        "Terminal token",
        "terminal_dashboard_compromised",
        label_visibility="collapsed",
    )
    if analyst_four.button("Check terminal", use_container_width=True):
        try:
            st.session_state["terminal_status"] = api(
                "GET",
                f"/v1/agent-terminals/{terminal_lookup}/status",
                role="analyst",
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))

    detail_left, detail_right = st.columns(2)
    with detail_left:
        if st.session_state.get("profile"):
            st.caption("Customer twin")
            st.json(st.session_state["profile"])
        if st.session_state.get("feedback_result"):
            st.caption("Feedback propagation")
            st.json(st.session_state["feedback_result"])
    with detail_right:
        if st.session_state.get("terminal_status"):
            st.caption("Agent terminal")
            st.json(st.session_state["terminal_status"])
        if st.session_state.get("decisions"):
            st.caption("Recent decisions")
            st.json(st.session_state["decisions"])

with st.expander("Governance tools", expanded=False):
    gov_one, gov_two, gov_three, gov_four = st.columns(4)
    if gov_one.button("Review queue", use_container_width=True):
        try:
            st.session_state["governance_output"] = api(
                "GET",
                "/v1/cases",
                role="analyst",
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if gov_two.button("Drift report", use_container_width=True):
        try:
            st.session_state["governance_output"] = api(
                "GET",
                "/v1/governance/drift",
                role="auditor",
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if gov_three.button("Equity report", use_container_width=True):
        try:
            st.session_state["governance_output"] = api(
                "GET",
                "/v1/governance/equity",
                role="auditor",
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if gov_four.button("Policy what-if", use_container_width=True):
        try:
            st.session_state["governance_output"] = api(
                "POST",
                "/v1/policy/simulate",
                {},
                role="auditor",
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if st.session_state.get("governance_output") is not None:
        st.json(st.session_state["governance_output"])

with st.expander("Resilience & outage controls", expanded=False):
    res_one, res_two, res_three, res_four = st.columns(4)
    if res_one.button("Degrade intelligence", use_container_width=True):
        try:
            st.session_state["resilience_output"] = api(
                "POST",
                "/v1/resilience/simulate",
                {"mode": "degraded"},
                role="admin",
            )
            st.rerun()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if res_two.button("Isolate payment rail", use_container_width=True):
        try:
            st.session_state["resilience_output"] = api(
                "POST",
                "/v1/resilience/simulate",
                {"mode": "isolated"},
                role="admin",
            )
            st.rerun()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if res_three.button("Restore services", use_container_width=True):
        try:
            st.session_state["resilience_output"] = api(
                "POST",
                "/v1/resilience/simulate",
                {"mode": "online"},
                role="admin",
            )
            st.rerun()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if res_four.button("Verify & reconcile", use_container_width=True):
        try:
            st.session_state["resilience_output"] = api(
                "POST",
                "/v1/resilience/reconcile",
                {"batch_size": 100},
                role="auditor",
            )
            st.rerun()
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))
    if st.session_state.get("resilience_output") is not None:
        st.json(st.session_state["resilience_output"])

if decision:
    with st.expander("Policy & technical evidence", expanded=False):
        score = decision.get("score", {})
        st.json(
            {
                "decision_id": decision.get("decision_id"),
                "model": score.get("model_version"),
                "model_score": score.get("model_score"),
                "anomaly_score": score.get("anomaly_score"),
                "policy": decision.get("policy"),
                "risk_window": decision.get("risk_window"),
                "decision_confidence": decision.get("decision_confidence"),
                "recipient_reputation": decision.get("recipient_reputation"),
                "campaign": decision.get("campaign"),
                "agent_terminal": decision.get("agent_terminal"),
                "fraud_sketch_exchange": decision.get("fraud_sketch_exchange"),
                "learning": decision.get("learning"),
                "provenance": decision.get("provenance"),
                "transaction_state": decision.get("transaction_state"),
                "resilience": decision.get("resilience"),
                "recourse_options": decision.get("recourse_options"),
                "features": decision.get("feature_snapshot"),
                "audit_hash": decision.get("audit_hash"),
            }
        )
