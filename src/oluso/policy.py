from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schemas import ResponseAction, RiskLevel

INTRUSIVE_ACTIONS = {
    ResponseAction.STEP_UP,
    ResponseAction.DELAY,
    ResponseAction.HOLD,
    ResponseAction.SAFE_PAUSE,
}


#: Policy ladder thresholds on the fused score. These are governance constants, chosen on
#: the synthetic validation split and documented in MODEL_GOVERNANCE.md; field calibration
#: must re-derive them from consented production data rather than editing decision logic.
POLICY_THRESHOLDS: dict[str, float] = {
    "monitor": 0.30,   # allow -> allow with monitoring / step-up candidates
    "confirm": 0.48,   # customer confirmation becomes eligible ("challenge" threshold)
    "delay": 0.66,     # reversible settlement delay or hold candidates
    "hold": 0.84,      # reversible hold with analyst review
}


def risk_level_for_score(score: float) -> RiskLevel:
    if score < POLICY_THRESHOLDS["monitor"]:
        return RiskLevel.LOW
    if score < POLICY_THRESHOLDS["confirm"]:
        return RiskLevel.GUARDED
    if score < POLICY_THRESHOLDS["delay"]:
        return RiskLevel.ELEVATED
    if score < POLICY_THRESHOLDS["hold"]:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


@dataclass(frozen=True)
class PolicyOutcome:
    action: ResponseAction
    hold_seconds: int
    requires_trusted_confirmation: bool
    requires_analyst_review: bool
    regret_budget_used: int
    regret_budget_limit: int
    budget_consumed_by_decision: bool
    budget_override_reason: str | None
    selected_expected_cost: float
    action_costs: dict[str, float]
    personalization_reasons: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "hold_seconds": self.hold_seconds,
            "requires_trusted_confirmation": self.requires_trusted_confirmation,
            "requires_analyst_review": self.requires_analyst_review,
            "regret_budget_used": self.regret_budget_used,
            "regret_budget_limit": self.regret_budget_limit,
            "budget_consumed_by_decision": self.budget_consumed_by_decision,
            "budget_override_reason": self.budget_override_reason,
            "selected_expected_cost": self.selected_expected_cost,
            "action_costs": self.action_costs,
            "personalization_reasons": self.personalization_reasons,
        }


class PolicyEngine:
    """Maps risk to reversible responses while enforcing a soft UX Regret Budget."""

    def decide(
        self,
        score: float,
        features: dict[str, float],
        *,
        regret_used: int,
        regret_limit: int,
        amount: float = 0.0,
        decision_confidence: float = 1.0,
    ) -> PolicyOutcome:
        if score < POLICY_THRESHOLDS["monitor"]:
            candidates = [ResponseAction.ALLOW, ResponseAction.ALLOW_MONITOR]
        elif score < POLICY_THRESHOLDS["confirm"]:
            candidates = [ResponseAction.ALLOW_MONITOR, ResponseAction.STEP_UP]
        elif score < POLICY_THRESHOLDS["delay"]:
            candidates = [ResponseAction.STEP_UP, ResponseAction.DELAY]
        elif score < POLICY_THRESHOLDS["hold"]:
            candidates = [ResponseAction.DELAY, ResponseAction.HOLD]
        else:
            candidates = [ResponseAction.HOLD]

        regret_ratio = regret_used / max(1, regret_limit)
        personalization_reasons: list[str] = []
        friction_multiplier = 1.0 + min(2.0, regret_ratio)
        if regret_ratio >= 1.0:
            personalization_reasons.append("The account has reached its 30-day intervention budget.")
        if features.get("is_ussd", 0.0) > 0:
            friction_multiplier *= 1.25
            personalization_reasons.append("USSD confirmation has higher customer effort.")
        if features.get("recurring_payment_match", 0.0) >= 0.80:
            friction_multiplier *= 1.45
            personalization_reasons.append("This resembles a well-established monthly payment.")
        if decision_confidence < 0.45:
            friction_multiplier *= 1.35
            personalization_reasons.append("Decision confidence is low, so irreversible friction is penalised.")

        exposure = max(500.0, amount, amount * features.get("balance_drain_ratio", 0.0))
        residual_loss = {
            ResponseAction.ALLOW: 0.98,
            ResponseAction.ALLOW_MONITOR: 0.78,
            ResponseAction.STEP_UP: 0.32,
            ResponseAction.DELAY: 0.12,
            ResponseAction.HOLD: 0.04,
        }
        base_friction = {
            ResponseAction.ALLOW: 0.0,
            ResponseAction.ALLOW_MONITOR: 15.0,
            ResponseAction.STEP_UP: 240.0,
            ResponseAction.DELAY: 720.0,
            ResponseAction.HOLD: 1_900.0,
        }
        action_costs = {
            item.value: round(
                score * exposure * residual_loss[item]
                + (1.0 - score) * base_friction[item] * friction_multiplier,
                2,
            )
            for item in residual_loss
        }
        action = min(candidates, key=lambda item: action_costs[item.value])
        if (
            features.get("recipient_confirmed_fraud_score", 0.0) > 0
            and features.get("recipient_confirmed_accounts", 0.0) * 3.0 < 2.0
            and score <= 0.45
        ):
            action = ResponseAction.ALLOW_MONITOR
            personalization_reasons.append(
                "A single recipient report triggers monitoring, not customer interruption."
            )
        if (
            features.get("fraud_sketch_risk", 0.0) > 0
            and features.get("fraud_sketch_local_corroboration", 0.0) == 0
            and score <= 0.45
        ):
            action = ResponseAction.ALLOW_MONITOR
            personalization_reasons.append(
                "Shared fraud sketches without local corroboration can only increase monitoring."
            )
        if (
            action == ResponseAction.HOLD
            and features.get("fraud_sketch_risk", 0.0) > 0
            and features.get("fraud_sketch_local_corroboration", 0.0) > 0
            and features.get("fraud_sketch_pre_exchange_score", score) < 0.66
            and score < 0.84
        ):
            action = ResponseAction.DELAY
            personalization_reasons.append(
                "Cross-bank evidence can justify a reversible delay, but not a hold without stronger local evidence."
            )

        coercion_signature = (
            features["coercion_evidence_coverage"] > 0
            and features["call_transfer_overlap"] > 0
            and features["new_recipient"] > 0
            and max(
                features["screen_sharing_signal"],
                features["confirmation_friction"],
                features["coercion_on_device_score"],
            ) >= 0.60
        )
        if coercion_signature:
            action = ResponseAction.SAFE_PAUSE
            action_costs[action.value] = round(
                score * exposure * 0.10 + (1.0 - score) * 520.0 * friction_multiplier,
                2,
            )

        critical_signal = (
            features["recovery_signal_72h"] > 0 and features["new_recipient"] > 0
        ) or (
            features["failed_auth_24h"] >= 0.60 and features["new_device"] > 0
        ) or (
            features["new_sim"] > 0
            and features["new_device"] > 0
            and features["verified_sim_change"] == 0
            and features["balance_drain_ratio"] >= 0.60
        ) or (
            features["new_sim"] > 0
            and features["recent_sim_activation"] >= 0.70
            and features["imsi_change"] + features["iccid_change"] >= 1.0
            and features["verified_sim_change"] == 0
        ) or (
            features["recipient_sender_diversity_24h"] >= 0.50
            and features["recipient_first_time_sender_ratio_24h"] >= 0.60
            and features["recipient_rapid_cashout_ratio_1h"] >= 0.45
        ) or (
            features.get("recipient_confirmed_accounts", 0.0) * 3.0 >= 2.0
        ) or (
            features.get("new_channel_enrollment_24h", 0.0) > 0
            and features.get("channel_transition_novelty", 0.0) >= 0.70
            and max(
                features.get("app_to_ussd_handoff", 0.0),
                features.get("cross_channel_device_mismatch", 0.0),
            ) > 0
        ) or (
            features.get("campaign_risk", 0.0) >= 0.75
        ) or (
            features.get("consortium_recipient_risk", 0.0) >= 0.75
        ) or (
            features.get("fraud_sketch_risk", 0.0) >= 0.75
            and features.get("fraud_sketch_local_corroboration", 0.0) > 0
        ) or coercion_signature

        override_reason = None
        if action == ResponseAction.HOLD and decision_confidence < 0.45 and not critical_signal:
            action = ResponseAction.DELAY
            override_reason = "Low decision confidence changed an automatic hold to a reversible delay."
        if action in INTRUSIVE_ACTIONS and regret_used >= regret_limit >= 0:
            if critical_signal or score >= 0.76:
                override_reason = "Security-critical evidence overrides the soft Regret Budget."
            elif action == ResponseAction.DELAY:
                action = ResponseAction.STEP_UP
                override_reason = "Regret Budget changed a settlement delay to trusted-channel confirmation."
            elif action == ResponseAction.STEP_UP:
                action = ResponseAction.ALLOW_MONITOR
                override_reason = "Regret Budget changed repeated confirmation to monitored approval."

        hold_seconds = 0
        if action in {ResponseAction.DELAY, ResponseAction.SAFE_PAUSE}:
            hold_seconds = 15 * 60
        elif action == ResponseAction.HOLD:
            hold_seconds = 2 * 60 * 60

        consumes_budget = action in INTRUSIVE_ACTIONS
        if not personalization_reasons:
            personalization_reasons.append("Standard risk, exposure and friction costs were applied.")
        return PolicyOutcome(
            action=action,
            hold_seconds=hold_seconds,
            requires_trusted_confirmation=action
            in {
                ResponseAction.STEP_UP,
                ResponseAction.DELAY,
                ResponseAction.HOLD,
                ResponseAction.SAFE_PAUSE,
            },
            requires_analyst_review=action == ResponseAction.HOLD,
            regret_budget_used=regret_used,
            regret_budget_limit=regret_limit,
            budget_consumed_by_decision=consumes_budget,
            budget_override_reason=override_reason,
            selected_expected_cost=action_costs.get(action.value, 0.0),
            action_costs=action_costs,
            personalization_reasons=personalization_reasons,
        )
