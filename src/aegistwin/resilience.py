from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import Settings
from .policy import PolicyOutcome
from .schemas import BehaviorEventIn, OutageHeartbeatRequest, ResilienceMode, ResponseAction
from .storage import Database, canonical_json, iso_utc


@dataclass(frozen=True)
class ResilienceContext:
    mode: ResilienceMode
    dependencies: dict[str, bool]
    confidence_multiplier: float
    unavailable_sources: list[str]
    evidence_freshness: dict[str, str]
    capsule_id: str | None
    capsule_valid: bool
    capsule_expires_at: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "confidence_multiplier": self.confidence_multiplier,
            "unavailable_sources": self.unavailable_sources,
            "evidence_freshness": self.evidence_freshness,
            "capsule_id": self.capsule_id,
            "capsule_valid": self.capsule_valid,
            "capsule_expires_at": self.capsule_expires_at,
            "safety_envelope_applied": False,
            "offline_reference": None,
        }


def heartbeat_material(request: OutageHeartbeatRequest) -> dict[str, Any]:
    return {
        "source_id": request.source_id,
        "observed_at": request.observed_at.astimezone(UTC).isoformat(),
        "nonce": request.nonce,
        "core_banking_available": request.core_banking_available,
        "telco_gateway_available": request.telco_gateway_available,
        "consortium_available": request.consortium_available,
        "recipient_graph_available": request.recipient_graph_available,
        "agent_integrity_available": request.agent_integrity_available,
        "model_runtime_available": request.model_runtime_available,
    }


class ResilienceController:
    """Trusted outage state, signed edge capsules and conservative fallback policy."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    def sign_heartbeat(self, request: OutageHeartbeatRequest) -> str:
        material = heartbeat_material(request)
        return hmac.new(
            self.settings.resilience_hmac_key.encode("utf-8"),
            canonical_json(material).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def create_capsule(
        self,
        tenant_id: str,
        *,
        model_version: str,
        model_hash: str | None,
        policy_version: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        payload = {
            "tenant_id": tenant_id,
            "model_version": model_version,
            "model_hash": model_hash or "rules-only",
            "policy_version": policy_version,
            "issued_at": iso_utc(now),
            "expires_at": iso_utc(now + timedelta(hours=self.settings.edge_capsule_ttl_hours)),
            "allowed_modes": ["online", "degraded", "isolated", "reconciling"],
        }
        signature = hmac.new(
            self.settings.resilience_hmac_key.encode("utf-8"),
            canonical_json(payload).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        capsule_id = f"cap_{hashlib.sha256((tenant_id + signature).encode()).hexdigest()[:20]}"
        return self.database.save_resilience_capsule(capsule_id, tenant_id, payload, signature)

    def verify_capsule(self, capsule: dict[str, Any] | None) -> bool:
        if not capsule:
            return False
        payload = capsule["payload"]
        expected = hmac.new(
            self.settings.resilience_hmac_key.encode("utf-8"),
            canonical_json(payload).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        try:
            expires_at = datetime.fromisoformat(str(payload["expires_at"])).astimezone(UTC)
        except (KeyError, ValueError):
            return False
        return hmac.compare_digest(expected, str(capsule["signature"])) and datetime.now(UTC) < expires_at

    def apply_heartbeat(self, tenant_id: str, request: OutageHeartbeatRequest) -> dict[str, Any]:
        age = abs((datetime.now(UTC) - request.observed_at).total_seconds())
        if age > self.settings.heartbeat_max_age_seconds:
            raise ValueError("heartbeat is stale")
        if not hmac.compare_digest(self.sign_heartbeat(request), request.signature):
            raise ValueError("heartbeat signature is invalid")
        if not self.database.claim_resilience_nonce(request.nonce, request.observed_at):
            raise ValueError("heartbeat nonce has already been used")

        dependencies = {
            "core_banking": request.core_banking_available,
            "telco_gateway": request.telco_gateway_available,
            "consortium": request.consortium_available,
            "recipient_graph": request.recipient_graph_available,
            "agent_integrity": request.agent_integrity_available,
            "model_runtime": request.model_runtime_available,
        }
        current = self.database.get_resilience_state(tenant_id)
        previous = ResilienceMode(str(current["mode"])) if current else ResilienceMode.ONLINE
        all_available = all(dependencies.values())
        if not request.core_banking_available:
            mode = ResilienceMode.ISOLATED
        elif not all_available:
            mode = ResilienceMode.DEGRADED
        elif previous in {
            ResilienceMode.DEGRADED,
            ResilienceMode.ISOLATED,
            ResilienceMode.RECONCILING,
        }:
            mode = ResilienceMode.RECONCILING
        else:
            mode = ResilienceMode.ONLINE
        return self.database.set_resilience_state(
            tenant_id,
            mode.value,
            dependencies,
            request.observed_at,
            previous.value,
            source_id=request.source_id,
        )

    def context(self, tenant_id: str) -> ResilienceContext:
        state = self.database.get_resilience_state(tenant_id)
        dependencies = (
            dict(state["dependencies"])
            if state
            else {
                "core_banking": True,
                "telco_gateway": True,
                "consortium": True,
                "recipient_graph": True,
                "agent_integrity": True,
                "model_runtime": True,
            }
        )
        mode = ResilienceMode(str(state["mode"])) if state else ResilienceMode.ONLINE
        capsule = self.database.get_active_resilience_capsule(tenant_id)
        capsule_valid = self.verify_capsule(capsule)
        unavailable = sorted(name for name, available in dependencies.items() if not available)
        freshness = {
            name: "fresh" if available else "unavailable"
            for name, available in dependencies.items()
        }
        multiplier = {
            ResilienceMode.ONLINE: 1.0,
            ResilienceMode.DEGRADED: 0.72 if not dependencies.get("model_runtime", True) else 0.82,
            ResilienceMode.ISOLATED: 0.35,
            ResilienceMode.RECONCILING: 0.75,
        }[mode]
        if mode != ResilienceMode.ONLINE and not capsule_valid:
            multiplier = min(multiplier, 0.25)
        return ResilienceContext(
            mode=mode,
            dependencies=dependencies,
            confidence_multiplier=multiplier,
            unavailable_sources=unavailable,
            evidence_freshness=freshness,
            capsule_id=str(capsule["capsule_id"]) if capsule else None,
            capsule_valid=capsule_valid,
            capsule_expires_at=str(capsule["expires_at"]) if capsule else None,
        )

    @staticmethod
    def offline_reference(tenant_id: str, event_id: str) -> str:
        digest = hashlib.sha256(f"{tenant_id}|{event_id}".encode()).hexdigest()[:12].upper()
        return f"OFF-{digest}"

    def apply_safety_envelope(
        self,
        policy: PolicyOutcome,
        event: BehaviorEventIn,
        features: dict[str, float],
        context: ResilienceContext,
    ) -> tuple[PolicyOutcome, bool, str | None]:
        if context.mode == ResilienceMode.ONLINE:
            return policy, False, None

        transaction = event.amount > 0
        risky_change = (
            features.get("new_recipient", 0.0) > 0
            or features.get("recovery_signal_72h", 0.0) > 0
            or features.get("new_sim", 0.0) + features.get("new_device", 0.0) >= 2.0
            or features.get("balance_drain_ratio", 0.0) >= 0.50
        )
        order = {
            ResponseAction.ALLOW: 0,
            ResponseAction.ALLOW_MONITOR: 1,
            ResponseAction.STEP_UP: 2,
            ResponseAction.DELAY: 3,
            ResponseAction.HOLD: 4,
            ResponseAction.SAFE_PAUSE: 5,
        }
        target = policy.action
        reason: str | None = None
        if context.mode == ResilienceMode.ISOLATED and transaction:
            target = max((target, ResponseAction.DELAY), key=lambda item: order[item])
            reason = "The payment rail is unavailable, so settlement remains pending and reversible."
        elif risky_change and transaction:
            target = max((target, ResponseAction.STEP_UP), key=lambda item: order[item])
            reason = "Trusted intelligence is incomplete, so an unusual payment requires safe confirmation."
        elif target == ResponseAction.ALLOW:
            target = ResponseAction.ALLOW_MONITOR
            reason = "Trusted intelligence is incomplete, so the permitted activity is monitored."

        if target == policy.action:
            return policy, reason is not None, reason
        hold_seconds = policy.hold_seconds
        if target == ResponseAction.DELAY:
            hold_seconds = max(hold_seconds, 15 * 60)
        elif target == ResponseAction.HOLD:
            hold_seconds = max(hold_seconds, 2 * 60 * 60)
        reasons = [*policy.personalization_reasons]
        if reason and reason not in reasons:
            reasons.append(reason)
        updated = replace(
            policy,
            action=target,
            hold_seconds=hold_seconds,
            requires_trusted_confirmation=target not in {ResponseAction.ALLOW, ResponseAction.ALLOW_MONITOR},
            requires_analyst_review=target == ResponseAction.HOLD,
            budget_consumed_by_decision=target not in {ResponseAction.ALLOW, ResponseAction.ALLOW_MONITOR},
            budget_override_reason=reason,
            personalization_reasons=reasons,
        )
        return updated, True, reason
