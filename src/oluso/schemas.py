from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Channel(StrEnum):
    APP = "app"
    USSD = "ussd"
    WEB = "web"
    AGENT = "agent"


class InputMethod(StrEnum):
    UNKNOWN = "unknown"
    TYPED = "typed"
    PASTED = "pasted"
    MIXED = "mixed"


class EventType(StrEnum):
    LOGIN = "login"
    FAILED_LOGIN = "failed_login"
    TRANSFER = "transfer"
    PAYBILL = "paybill"
    PURCHASE = "purchase"
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    PIN_RESET = "pin_reset"
    ACCOUNT_RECOVERY = "account_recovery"


class RiskLevel(StrEnum):
    LOW = "low"
    GUARDED = "guarded"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class ResponseAction(StrEnum):
    ALLOW = "allow"
    ALLOW_MONITOR = "allow_with_monitoring"
    STEP_UP = "trusted_channel_confirmation"
    DELAY = "reversible_settlement_delay"
    HOLD = "reversible_hold_and_review"
    SAFE_PAUSE = "private_safety_pause"


class ResilienceMode(StrEnum):
    ONLINE = "online"
    DEGRADED = "degraded"
    ISOLATED = "isolated"
    RECONCILING = "reconciling"


class FeedbackLabel(StrEnum):
    LEGITIMATE = "legitimate"
    ACCOUNT_TAKEOVER = "account_takeover"
    OTHER_FRAUD = "other_fraud"
    UNKNOWN = "unknown"


class FraudSketchIndicatorType(StrEnum):
    RECIPIENT = "recipient"
    AGENT_TERMINAL = "agent_terminal"
    CAMPAIGN = "campaign"


class AccountCreate(BaseModel):
    account_id: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    shared_device_allowed: bool = False
    regret_limit_30d: int | None = Field(default=None, ge=0, le=30)
    trusted_contact_masked: str | None = Field(default=None, max_length=40)


class AccountResponse(BaseModel):
    account_id: str
    display_name: str
    shared_device_allowed: bool
    regret_limit_30d: int
    trusted_contact_masked: str | None
    created_at: datetime


class TelcoAssurance(BaseModel):
    """Privacy-reduced SIM lifecycle signals supplied by a trusted bank/telco gateway."""

    imsi_changed: bool = False
    iccid_changed: bool = False
    sim_type_changed: bool = False
    sim_activation_age_hours: float | None = Field(default=None, ge=0.0, le=100_000.0)
    sim_changes_30d: int | None = Field(default=None, ge=0, le=30)
    previous_sim_tenure_days: float | None = Field(default=None, ge=0.0, le=10_000.0)
    otp_to_sim_change_minutes: float | None = Field(default=None, ge=0.0, le=100_000.0)
    otp_sim_geo_distance_km: float | None = Field(default=None, ge=0.0, le=20_100.0)
    gateway_attested: bool = False


class CoercionSignals(BaseModel):
    """Privacy-reduced session safety signals computed on a consented trusted device."""

    active_call: bool = False
    screen_sharing_detected: bool = False
    recipient_replacements: int = Field(default=0, ge=0, le=20)
    confirmation_backtracks: int = Field(default=0, ge=0, le=30)
    amount_edits: int = Field(default=0, ge=0, le=30)
    pause_before_confirmation_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    recipient_pasted_during_call: bool = False
    on_device_coercion_score: float | None = Field(default=None, ge=0.0, le=1.0)
    consented_device_attested: bool = False


class AgentTerminalAssurance(BaseModel):
    """Tokenised agent and terminal identity supplied only by the bank's agency gateway."""

    agent_token: str = Field(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9_.:-]+$")
    terminal_token: str = Field(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9_.:-]+$")
    registered_latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    registered_longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    shift_start_hour: int | None = Field(default=None, ge=0, le=23)
    shift_end_hour: int | None = Field(default=None, ge=0, le=23)
    terminal_age_days: float | None = Field(default=None, ge=0.0, le=10_000.0)
    gateway_attested: bool = False

    @model_validator(mode="after")
    def validate_pairs(self) -> AgentTerminalAssurance:
        if (self.registered_latitude is None) != (self.registered_longitude is None):
            raise ValueError("registered agent latitude and longitude must be supplied together")
        if (self.shift_start_hour is None) != (self.shift_end_hour is None):
            raise ValueError("agent shift start and end hours must be supplied together")
        return self


class BehaviorEventIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: str = Field(min_length=6, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    account_id: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: EventType
    channel: Channel
    amount: float = Field(default=0.0, ge=0.0, le=1_000_000_000.0)
    available_balance_before: float | None = Field(default=None, ge=0.0, le=10_000_000_000.0)
    recipient_id: str | None = Field(default=None, max_length=100)
    device_id: str | None = Field(default=None, max_length=160)
    sim_id: str | None = Field(default=None, max_length=160)
    ip_prefix: str | None = Field(default=None, max_length=80)
    session_id: str | None = Field(default=None, max_length=160)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    interaction_ms: int | None = Field(default=None, ge=50, le=3_600_000)
    menu_depth: int | None = Field(default=None, ge=1, le=100)
    input_method: InputMethod = InputMethod.UNKNOWN
    keystroke_interval_ms: float | None = Field(default=None, ge=20.0, le=5_000.0)
    device_tilt_variance: float | None = Field(default=None, ge=0.0, le=10_000.0)
    navigation_signature: str | None = Field(default=None, max_length=120)
    sim_change_verified: bool = False
    telco_assurance: TelcoAssurance | None = None
    agent_assurance: AgentTerminalAssurance | None = None
    coercion_signals: CoercionSignals | None = None
    success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_coordinates_and_transaction(self) -> BehaviorEventIn:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        transactional = {
            EventType.TRANSFER,
            EventType.PAYBILL,
            EventType.PURCHASE,
            EventType.WITHDRAWAL,
            EventType.DEPOSIT,
        }
        if self.event_type not in transactional and self.amount != 0:
            raise ValueError("non-transaction events must use amount=0")
        if self.menu_depth is not None and self.interaction_ms is None:
            raise ValueError("interaction_ms is required when menu_depth is supplied")
        if self.agent_assurance is not None and self.channel != Channel.AGENT:
            raise ValueError("agent_assurance is only valid for the agent channel")
        return self


class Reason(BaseModel):
    code: str
    message: str
    contribution: float = Field(ge=0.0, le=1.0)


class ScoreBreakdown(BaseModel):
    model_score: float | None = Field(default=None, ge=0.0, le=1.0)
    anomaly_score: float = Field(ge=0.0, le=1.0)
    fused_score: float = Field(ge=0.0, le=1.0)
    profile_confidence: float = Field(ge=0.0, le=1.0)
    model_version: str


class PolicyResult(BaseModel):
    action: ResponseAction
    hold_seconds: int = Field(ge=0)
    requires_trusted_confirmation: bool
    requires_analyst_review: bool
    regret_budget_used: int = Field(ge=0)
    regret_budget_limit: int = Field(ge=0)
    budget_consumed_by_decision: bool
    budget_override_reason: str | None = None
    selected_expected_cost: float = Field(default=0.0, ge=0.0)
    action_costs: dict[str, float] = Field(default_factory=dict)
    personalization_reasons: list[str] = Field(default_factory=list)


class DecisionConfidenceSummary(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    level: str
    profile_maturity: float = Field(ge=0.0, le=1.0)
    data_coverage: float = Field(ge=0.0, le=1.0)
    scorer_agreement: float = Field(ge=0.0, le=1.0)
    reasons: list[str]


class RecipientReputationSummary(BaseModel):
    status: str
    score: float = Field(ge=0.0, le=1.0)
    confirmed_reports: int = Field(ge=0)
    distinct_accounts: int = Field(ge=0)
    expires_at: datetime | None = None


class AgentTerminalSummary(BaseModel):
    status: str
    score: float = Field(ge=0.0, le=1.0)
    confirmed_reports: int = Field(ge=0)
    distinct_accounts: int = Field(ge=0)
    quarantined: bool = False
    expires_at: datetime | None = None


class FraudSketchSummary(BaseModel):
    status: str = "clear"
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    independent_institutions: int = Field(default=0, ge=0)
    active_reports: int = Field(default=0, ge=0)
    matched_indicators: list[str] = Field(default_factory=list)
    source_mode: str = "live"
    local_corroboration: bool = False
    action_ceiling: str = "monitor"
    expires_at: datetime | None = None


class EvidenceSummary(BaseModel):
    mode: str
    coverage: float = Field(ge=0.0, le=1.0)
    available_signals: list[str]
    missing_optional_signals: list[str]


class RiskWindowSummary(BaseModel):
    state: str
    score: float = Field(ge=0.0, le=1.0)
    hours_remaining: float = Field(ge=0.0)
    active_precursors: list[str]


class RecourseOption(BaseModel):
    action: str
    description: str
    estimated_clearance: str
    safe_channel: str


class OutageResilienceSummary(BaseModel):
    mode: ResilienceMode = ResilienceMode.ONLINE
    confidence_multiplier: float = Field(default=1.0, ge=0.0, le=1.0)
    unavailable_sources: list[str] = Field(default_factory=list)
    evidence_freshness: dict[str, str] = Field(default_factory=dict)
    capsule_id: str | None = None
    capsule_valid: bool = False
    capsule_expires_at: datetime | None = None
    safety_envelope_applied: bool = False
    offline_reference: str | None = None


class RiskDecisionResponse(BaseModel):
    decision_id: str
    event_id: str
    account_id: str
    risk_level: RiskLevel
    score: ScoreBreakdown
    policy: PolicyResult
    reasons: list[Reason]
    customer_explanation: str
    evidence: EvidenceSummary
    risk_window: RiskWindowSummary
    decision_confidence: DecisionConfidenceSummary
    recipient_reputation: RecipientReputationSummary
    agent_terminal: AgentTerminalSummary
    fraud_sketch_exchange: FraudSketchSummary = Field(default_factory=FraudSketchSummary)
    recourse_options: list[RecourseOption]
    uncertainty_note: str | None
    feature_snapshot: dict[str, float]
    audit_hash: str
    created_at: datetime
    campaign: dict[str, Any] = Field(default_factory=dict)
    learning: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    transaction_state: str = "created"
    resilience: OutageResilienceSummary = Field(default_factory=OutageResilienceSummary)


class ProfileResponse(BaseModel):
    account_id: str
    profile_version: int
    history_events: int
    transaction_events: int
    profile_confidence: float
    amount_median: float
    amount_mad: float
    common_hours: list[int]
    known_devices: int
    known_sims: int
    known_recipients: int
    known_channels: list[str]
    recent_failed_auth_24h: int
    last_event_at: datetime | None
    updated_at: datetime


class FeedbackRequest(BaseModel):
    label: FeedbackLabel
    analyst_id: str = Field(min_length=2, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    case_quality: str = Field(default="verified_callback", max_length=80)
    second_approver_id: str | None = Field(default=None, min_length=2, max_length=100)


class LifecycleState(StrEnum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    HELD = "held"
    RELEASED = "released"
    SETTLED = "settled"
    CANCELLED = "cancelled"


class LifecycleTransitionRequest(BaseModel):
    target_state: LifecycleState
    actor_id: str = Field(min_length=2, max_length=100)
    reason: str = Field(min_length=3, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=120)


class ReplayResponse(BaseModel):
    decision_id: str
    exact_match: bool
    stored_digest: str
    replay_digest: str
    model_version: str
    policy_version: str
    cutoff_at: datetime


class AppealRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
    contact_channel: str = Field(default="official_callback", max_length=80)


class ConsortiumReportRequest(BaseModel):
    recipient_id: str = Field(min_length=3, max_length=100)
    institution_id: str = Field(min_length=3, max_length=100)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_class: str = Field(default="confirmed_customer_report", max_length=100)


class FraudSketchReportRequest(BaseModel):
    report_id: str = Field(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    institution_id: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    indicator_type: FraudSketchIndicatorType
    indicator_value: str = Field(min_length=3, max_length=160)
    confidence: float = Field(ge=0.60, le=1.0)
    evidence_class: str = Field(
        default="verified_account_takeover",
        pattern=(
            r"^(confirmed_customer_report|verified_account_takeover|"
            r"confirmed_mule_cashout|confirmed_terminal_compromise|analyst_high_confidence)$"
        ),
    )
    observed_at: datetime
    ttl_hours: int = Field(default=168, ge=1, le=720)
    nonce: str = Field(min_length=12, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    signature: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")

    @field_validator("observed_at")
    @classmethod
    def sketch_time_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value.astimezone(UTC)


class FraudSketchRevocationRequest(BaseModel):
    institution_id: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    reason: str = Field(min_length=5, max_length=500)
    revoked_at: datetime
    nonce: str = Field(min_length=12, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    signature: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")

    @field_validator("revoked_at")
    @classmethod
    def revocation_time_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("revoked_at must include a timezone")
        return value.astimezone(UTC)


class PolicySimulationRequest(BaseModel):
    monitor_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    confirm_threshold: float = Field(default=0.48, ge=0.0, le=1.0)
    delay_threshold: float = Field(default=0.66, ge=0.0, le=1.0)
    hold_threshold: float = Field(default=0.84, ge=0.0, le=1.0)


class OutageHeartbeatRequest(BaseModel):
    source_id: str = Field(min_length=3, max_length=100)
    observed_at: datetime
    nonce: str = Field(min_length=12, max_length=120)
    core_banking_available: bool = True
    telco_gateway_available: bool = True
    consortium_available: bool = True
    recipient_graph_available: bool = True
    agent_integrity_available: bool = True
    model_runtime_available: bool = True
    signature: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")

    @field_validator("observed_at")
    @classmethod
    def heartbeat_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value.astimezone(UTC)


class OutageSimulationRequest(BaseModel):
    mode: ResilienceMode


class ReconciliationRequest(BaseModel):
    batch_size: int = Field(default=100, ge=1, le=1000)


class PrivacyRequest(BaseModel):
    account_id: str = Field(min_length=3, max_length=80)
    request_type: str = Field(pattern=r"^(export|delete)$")
    requester_id: str = Field(min_length=2, max_length=100)


class ProfileSuccessionRequest(BaseModel):
    account_id: str = Field(min_length=3, max_length=80)
    trusted_device_confirmed: bool
    official_callback_confirmed: bool
    reason: str = Field(min_length=3, max_length=500)


class CampaignSummary(BaseModel):
    signature: str
    score: float = Field(ge=0.0, le=1.0)
    distinct_accounts: int = Field(ge=0)
    stages: list[str]
    eligible: bool


class LearningSummary(BaseModel):
    trust_state: str
    eligible_after: datetime | None = None
    profile_epoch: int = Field(default=0, ge=0)


class ProvenanceSummary(BaseModel):
    event_digest: str
    feature_digest: str
    replay_digest: str
    policy_version: str
    cutoff_at: datetime


class AuditVerificationResponse(BaseModel):
    valid: bool
    entries_checked: int
    first_invalid_sequence: int | None = None
    head_hash: str | None = None


class MetricsResponse(BaseModel):
    accounts: int
    events: int
    decisions: int
    decisions_by_level: dict[str, int]
    decisions_by_action: dict[str, int]
    feedback_by_label: dict[str, int]
    pending_learning_events: int = 0
    open_cases: int = 0
    outbox_pending: int = 0
    offline_journal_pending: int = 0
    resilience_modes: dict[str, int] = Field(default_factory=dict)
    active_fraud_sketch_reports: int = Field(default=0, ge=0)
    active_fraud_sketch_capsules: int = Field(default=0, ge=0)
