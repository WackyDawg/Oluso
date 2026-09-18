from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from .agent import summarize_agent_terminal
from .audit import AuditChain
from .config import Settings
from .features import FeatureEngine
from .fraud_sketch import (
    candidate_epochs,
    capsule_material,
    epoch_id,
    indicator_token,
    institution_token,
    score_reports,
    sign_capsule,
    verify_capsule,
    verify_report,
    verify_revocation,
)
from .network import summarize_recipient_network
from .platform import (
    campaign_is_eligible,
    campaign_score,
    campaign_signature,
    evidence_provenance,
    hmac_token,
    psi,
    review_priority,
)
from .policy import POLICY_THRESHOLDS, PolicyEngine, risk_level_for_score
from .profile import ProfileBuilder
from .resilience import ResilienceController
from .schemas import (
    AccountCreate,
    AccountResponse,
    AppealRequest,
    BehaviorEventIn,
    ConsortiumReportRequest,
    FeedbackRequest,
    FraudSketchReportRequest,
    FraudSketchRevocationRequest,
    LifecycleTransitionRequest,
    OutageHeartbeatRequest,
    OutageSimulationRequest,
    PolicySimulationRequest,
    PrivacyRequest,
    ProfileResponse,
    ProfileSuccessionRequest,
    ReconciliationRequest,
    ResilienceMode,
    RiskDecisionResponse,
)
from .scoring import (
    AnomalyScorer,
    FusionBreakdown,
    ModelBundle,
    build_customer_explanation,
    build_decision_confidence,
    build_evidence_summary,
    build_recourse_options,
    fuse_scores_detailed,
)
from .storage import Database, canonical_json, iso_utc
from .telemetry import Telemetry, timed


class ServiceError(Exception):
    pass


class NotFoundError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass


class AtoService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = Database(settings.database_path)
        self.database.initialize()
        self.audit = AuditChain(self.database)
        self.feature_engine = FeatureEngine()
        self.profile_builder = ProfileBuilder()
        self.anomaly_scorer = AnomalyScorer()
        self.model_bundle = ModelBundle(settings.model_path)
        self.policy_engine = PolicyEngine()
        self.resilience = ResilienceController(self.database, settings)
        self.telemetry = Telemetry()
        # Striped locks preserve per-account ordering without serialising every bank customer.
        self._score_locks = [threading.RLock() for _ in range(64)]
        for tenant_id in settings.allowed_tenants:
            if self.database.get_active_resilience_capsule(tenant_id) is None:
                self.resilience.create_capsule(
                    tenant_id,
                    model_version=self.model_bundle.version,
                    model_hash=self.model_bundle.artifact_hash,
                    policy_version=settings.policy_version,
                )

    def create_account(self, request: AccountCreate, tenant_id: str = "default") -> AccountResponse:
        payload = request.model_dump()
        payload["regret_limit_30d"] = (
            request.regret_limit_30d
            if request.regret_limit_30d is not None
            else self.settings.default_regret_limit
        )
        try:
            account = self.database.create_account(payload, tenant_id)
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"account already exists: {request.account_id}") from exc
        self.audit.append(
            "account_created",
            request.account_id,
            {
                "account_id": request.account_id,
                "shared_device_allowed": request.shared_device_allowed,
                "regret_limit_30d": payload["regret_limit_30d"],
            },
        )
        return AccountResponse.model_validate(account)

    def get_account(self, account_id: str, tenant_id: str = "default") -> AccountResponse:
        account = self.database.get_account(account_id, tenant_id)
        if account is None:
            raise NotFoundError(f"account not found: {account_id}")
        return AccountResponse.model_validate(account)

    def _institution_secret(self, institution_id: str) -> str:
        secret = self.settings.fraud_sketch_institution_keys.get(institution_id.strip().lower())
        if secret is None:
            raise ConflictError("institution is not enrolled in the fraud-sketch exchange")
        return secret

    def _refresh_fraud_sketch_capsule(
        self,
        indicator_type: str,
        token: str,
        epoch: str,
        at: datetime,
    ) -> dict[str, Any]:
        summary = score_reports(
            self.database.fraud_sketch_reports(indicator_type, [token]), at
        )
        issued_at = datetime.now(UTC)
        report_expiry = (
            datetime.fromisoformat(str(summary["expires_at"])).astimezone(UTC)
            if summary.get("expires_at")
            else issued_at + timedelta(hours=1)
        )
        expires_at = min(
            report_expiry,
            issued_at + timedelta(hours=self.settings.fraud_sketch_capsule_ttl_hours),
        )
        capsule_id = "fsc_" + hashlib.sha256(
            f"{indicator_type}|{token}|{iso_utc(issued_at)}".encode()
        ).hexdigest()[:24]
        payload = {
            "capsule_id": capsule_id,
            "indicator_type": indicator_type,
            "indicator_token": token,
            "epoch_id": epoch,
            "score": summary["score"],
            "confidence": summary["confidence"],
            "independent_institutions": summary["independent_institutions"],
            "active_reports": summary["active_reports"],
            "status": summary["status"],
            "issued_at": iso_utc(issued_at),
            "expires_at": iso_utc(expires_at),
        }
        signature = sign_capsule(payload, self.settings.fraud_sketch_capsule_key)
        return self.database.save_fraud_sketch_capsule(payload, signature)

    def _fraud_sketch_indicator_summary(
        self,
        indicator_type: str,
        value: str,
        at: datetime,
        *,
        exchange_available: bool,
    ) -> dict[str, Any]:
        epochs = candidate_epochs(
            at,
            self.settings.fraud_sketch_epoch_days,
            self.settings.fraud_sketch_retention_days,
        )
        tokens = [
            indicator_token(
                indicator_type,
                value,
                self.settings.fraud_sketch_token_key,
                epoch=epoch,
            )
            for epoch in epochs
        ]
        candidates: list[dict[str, Any]] = []
        if exchange_available:
            rows = self.database.fraud_sketch_reports(indicator_type, tokens)
            for token in tokens:
                token_rows = [row for row in rows if row["indicator_token"] == token]
                summary = score_reports(token_rows, at)
                if summary["active_reports"]:
                    candidates.append({**summary, "source_mode": "live"})
        else:
            for capsule in self.database.fraud_sketch_capsules(indicator_type, tokens):
                signature = str(capsule.pop("signature"))
                if not verify_capsule(
                    capsule,
                    signature,
                    self.settings.fraud_sketch_capsule_key,
                    at,
                ):
                    continue
                candidates.append(
                    {
                        **capsule_material(capsule),
                        "score": round(float(capsule["score"]) * 0.85, 6),
                        "confidence": round(float(capsule["confidence"]) * 0.75, 6),
                        "source_mode": "signed_cache",
                    }
                )
        if not candidates:
            return {
                "score": 0.0,
                "confidence": 0.0,
                "independent_institutions": 0,
                "active_reports": 0,
                "status": "clear" if exchange_available else "unavailable",
                "expires_at": None,
                "source_mode": "live" if exchange_available else "unavailable",
            }
        return max(
            candidates,
            key=lambda item: (
                float(item["score"]),
                int(item["independent_institutions"]),
                float(item["confidence"]),
            ),
        )

    def _fraud_sketch_for_event(
        self,
        event: BehaviorEventIn,
        campaign_value: str,
        terminal_token: str | None,
        at: datetime,
        pre_exchange_score: float,
        features: dict[str, float],
        recipient_reputation: dict[str, Any],
        agent_reputation: dict[str, Any],
        campaign_risk: float,
        *,
        exchange_available: bool,
    ) -> tuple[dict[str, Any], float]:
        indicators: list[tuple[str, str]] = []
        if event.recipient_id:
            indicators.append(("recipient", event.recipient_id))
        if terminal_token:
            indicators.append(("agent_terminal", terminal_token))
        if campaign_risk > 0:
            indicators.append(("campaign", campaign_value))

        matched: list[tuple[str, dict[str, Any]]] = []
        source_modes: set[str] = set()
        for kind, value in indicators:
            summary = self._fraud_sketch_indicator_summary(
                kind, value, at, exchange_available=exchange_available
            )
            source_modes.add(str(summary["source_mode"]))
            if float(summary["score"]) > 0:
                matched.append((kind, summary))

        local_corroboration = (
            pre_exchange_score >= 0.30
            or float(recipient_reputation.get("score", 0.0)) >= 0.35
            or float(agent_reputation.get("score", 0.0)) >= 0.35
            or campaign_risk >= 0.62
            or (
                features.get("new_recipient", 0.0) > 0
                and features.get("balance_drain_ratio", 0.0) >= 0.45
            )
        )
        if not matched:
            source_mode = (
                "unavailable"
                if "unavailable" in source_modes
                else "signed_cache"
                if "signed_cache" in source_modes
                else "live"
            )
            return {
                "status": "clear" if source_mode != "unavailable" else "unavailable",
                "score": 0.0,
                "confidence": 0.0,
                "independent_institutions": 0,
                "active_reports": 0,
                "matched_indicators": [],
                "source_mode": source_mode,
                "local_corroboration": local_corroboration,
                "action_ceiling": "monitor",
                "expires_at": None,
            }, pre_exchange_score

        best_kind, best = max(
            matched,
            key=lambda item: (
                float(item[1]["score"]),
                int(item[1]["independent_institutions"]),
            ),
        )
        exchange_score = min(
            0.92,
            float(best["score"]) + (0.04 if len(matched) >= 2 else 0.0),
        )
        independent = int(best["independent_institutions"])
        action_ceiling = "delay" if independent >= 2 and local_corroboration else "monitor"
        contribution_ceiling = 0.82 if action_ceiling == "delay" else 0.42
        applied_score = max(pre_exchange_score, min(contribution_ceiling, exchange_score))
        status = str(best["status"])
        if str(best["source_mode"]) == "signed_cache":
            status = f"cached_{status}"
        return {
            "status": status,
            "score": round(exchange_score, 6),
            "confidence": float(best["confidence"]),
            "independent_institutions": independent,
            "active_reports": int(best["active_reports"]),
            "matched_indicators": sorted(kind for kind, _ in matched),
            "source_mode": str(best["source_mode"]),
            "local_corroboration": local_corroboration,
            "action_ceiling": action_ceiling,
            "expires_at": best.get("expires_at"),
            "primary_indicator": best_kind,
        }, round(applied_score, 6)

    #: Features whose distribution is tracked by the drift report. They are the strongest
    #: univariate signals in the robustness audit plus the evidence-availability features,
    #: so both behavioural shift and telemetry-feed shift are visible.
    DRIFT_MONITORED_FEATURES: tuple[str, ...] = (
        "balance_drain_ratio",
        "amount_to_median",
        "amount_deviation",
        "new_recipient",
        "new_device",
        "recipient_inflow_velocity_1h",
        "history_confidence",
        "evidence_coverage",
        "telco_assurance_coverage",
    )

    @staticmethod
    def _fuse(
        model_score: float | None,
        anomaly_score: float,
        features: dict[str, float],
    ) -> FusionBreakdown:
        """Fuse scores and record the breakdown in the feature snapshot for replay and audit."""

        fusion = fuse_scores_detailed(model_score, anomaly_score, features)
        features["fusion_blended_score"] = fusion.blended_score
        features["fusion_security_floor"] = fusion.security_floor
        features["fusion_model_weight"] = (
            fusion.model_weight if fusion.model_weight is not None else 0.0
        )
        features["fusion_floor_driven"] = 1.0 if fusion.driver == "security_floor" else 0.0
        return fusion

    def close(self) -> None:
        """Release pooled database connections (called from the API lifespan hook)."""

        self.database.close()

    def score_event(self, event: BehaviorEventIn, tenant_id: str = "default") -> RiskDecisionResponse:
        with timed(self.telemetry):
            return self._score_event(event, tenant_id)

    def _score_event(self, event: BehaviorEventIn, tenant_id: str) -> RiskDecisionResponse:
        account_lock = self._score_locks[hash(event.account_id) % len(self._score_locks)]
        with account_lock:
            account = self.database.get_account(event.account_id, tenant_id)
            if account is None:
                raise NotFoundError(f"account not found: {event.account_id}")
            if self.database.event_exists(event.event_id, tenant_id):
                raise ConflictError(f"event already scored: {event.event_id}")

            resilience_context = self.resilience.context(tenant_id)
            if not resilience_context.dependencies.get("telco_gateway", True) and event.telco_assurance:
                event = event.model_copy(
                    update={
                        "telco_assurance": event.telco_assurance.model_copy(
                            update={"gateway_attested": False}
                        )
                    }
                )
            if not resilience_context.dependencies.get("agent_integrity", True) and event.agent_assurance:
                event = event.model_copy(
                    update={
                        "agent_assurance": event.agent_assurance.model_copy(
                            update={"gateway_attested": False}
                        )
                    }
                )
            event = self._enforce_evidence_freshness(event)
            history_start = event.occurred_at - timedelta(days=self.settings.profile_lookback_days)
            history = self.database.get_events(
                event.account_id,
                tenant_id=tenant_id,
                before=event.occurred_at,
                since=history_start,
                limit=self.settings.max_history_events,
            )
            network_events = (
                self.database.get_network_events(
                    before=event.occurred_at,
                    since=event.occurred_at - timedelta(days=7),
                    tenant_id=tenant_id,
                )
                if resilience_context.dependencies.get("recipient_graph", True)
                or resilience_context.dependencies.get("agent_integrity", True)
                else []
            )
            recipient_context = summarize_recipient_network(
                network_events
                if resilience_context.dependencies.get("recipient_graph", True)
                else [],
                event.recipient_id,
                event.account_id,
                event.occurred_at,
            )
            recipient_reputation = self.database.get_recipient_reputation(
                event.recipient_id, at=event.occurred_at
            )
            recipient_context.update(
                {
                    "confirmed_fraud_score": recipient_reputation["score"],
                    "confirmed_distinct_accounts": recipient_reputation["distinct_accounts"],
                    "watchlist_evidence_available": recipient_reputation[
                        "watchlist_evidence_available"
                    ],
                }
            )
            terminal_token = (
                event.agent_assurance.terminal_token
                if event.agent_assurance and event.agent_assurance.gateway_attested
                else None
            )
            agent_reputation = self.database.get_agent_terminal_reputation(
                terminal_token,
                tenant_id=tenant_id,
                at=event.occurred_at,
            )
            agent_context = summarize_agent_terminal(
                network_events
                if resilience_context.dependencies.get("agent_integrity", True)
                else [],
                event,
                agent_reputation,
            )
            features, profile_before = self.feature_engine.extract(
                event,
                history,
                account,
                recipient_context,
                agent_context,
            )
            anomaly = self.anomaly_scorer.score(features)
            model_score = (
                self.model_bundle.predict(features)
                if resilience_context.dependencies.get("model_runtime", True)
                else None
            )
            fusion = self._fuse(model_score, anomaly.score, features)
            fused_score, uncertainty_note = fusion.fused_score, fusion.note

            signature, stages = campaign_signature(event.model_dump(mode="json"), features)
            campaign_memory = self.database.record_campaign(
                tenant_id, signature, event.account_id, stages, event.occurred_at
            )
            campaign_risk = campaign_score(campaign_memory["distinct_accounts"], stages)
            campaign = {
                "signature": signature,
                "score": campaign_risk,
                "distinct_accounts": campaign_memory["distinct_accounts"],
                "stages": stages,
                "eligible": campaign_is_eligible(stages),
            }
            if campaign_risk >= 0.62:
                fused_score = max(fused_score, campaign_risk)
            features["campaign_risk"] = campaign_risk

            consortium = (
                self.database.consortium_score(
                    hmac_token(event.recipient_id, self.settings.recipient_hmac_key)
                )
                if event.recipient_id
                and resilience_context.dependencies.get("consortium", True)
                else {"score": 0.0, "independent_institutions": 0}
            )
            if consortium["score"] >= 0.70:
                fused_score = max(fused_score, min(0.96, consortium["score"] + 0.04))
                features["consortium_recipient_risk"] = consortium["score"]
            pre_sketch_score = fused_score
            fraud_sketch, fused_score = self._fraud_sketch_for_event(
                event,
                "|".join(stages),
                terminal_token,
                event.occurred_at,
                pre_sketch_score,
                features,
                recipient_reputation,
                agent_reputation,
                campaign_risk,
                exchange_available=resilience_context.dependencies.get("consortium", True),
            )
            features["fraud_sketch_risk"] = float(fraud_sketch["score"])
            features["fraud_sketch_independent_institutions"] = min(
                1.0, float(fraud_sketch["independent_institutions"]) / 3.0
            )
            features["fraud_sketch_local_corroboration"] = (
                1.0 if fraud_sketch["local_corroboration"] else 0.0
            )
            features["fraud_sketch_cached"] = (
                1.0 if fraud_sketch["source_mode"] == "signed_cache" else 0.0
            )
            features["fraud_sketch_pre_exchange_score"] = round(pre_sketch_score, 6)
            decision_confidence = build_decision_confidence(
                features, model_score, anomaly.score
            )
            if fraud_sketch["source_mode"] == "signed_cache":
                decision_confidence["score"] = round(
                    decision_confidence["score"] * 0.90, 6
                )
                decision_confidence["reasons"] = [
                    "Cross-bank fraud intelligence came from a valid short-lived outage cache.",
                    *decision_confidence["reasons"],
                ]
            if resilience_context.mode != ResilienceMode.ONLINE:
                decision_confidence["score"] = round(
                    decision_confidence["score"] * resilience_context.confidence_multiplier,
                    6,
                )
                decision_confidence["level"] = (
                    "high"
                    if decision_confidence["score"] >= 0.75
                    else "medium"
                    if decision_confidence["score"] >= 0.45
                    else "low"
                )
                decision_confidence["reasons"] = [
                    f"Resilience mode is {resilience_context.mode.value}; unavailable evidence is not treated as safe.",
                    *decision_confidence["reasons"],
                ]
            risk_level = risk_level_for_score(fused_score)

            regret_used = self.database.count_intrusive_decisions(event.account_id, days=30)
            regret_limit = int(account["regret_limit_30d"])
            policy = self.policy_engine.decide(
                fused_score,
                features,
                regret_used=regret_used,
                regret_limit=regret_limit,
                amount=event.amount,
                decision_confidence=decision_confidence["score"],
            )
            policy, safety_envelope_applied, outage_policy_reason = (
                self.resilience.apply_safety_envelope(policy, event, features, resilience_context)
            )

            reasons = anomaly.reasons
            if campaign_risk >= 0.62:
                reasons = [{
                    "code": "CROSS_ACCOUNT_CAMPAIGN_DNA",
                    "message": "The attack sequence matches a recent pattern across distinct accounts.",
                    "contribution": round(min(1.0, campaign_risk * 0.35), 6),
                }, *reasons]
            if consortium["score"] >= 0.70:
                reasons = [{
                    "code": "INDEPENDENT_CONSORTIUM_REPORTS",
                    "message": "Multiple independent institutions reported the tokenised recipient.",
                    "contribution": round(min(1.0, consortium["score"] * 0.35), 6),
                }, *reasons]
            if fraud_sketch["score"] > 0:
                contribution = max(0.0, fused_score - pre_sketch_score)
                if fraud_sketch["action_ceiling"] == "delay":
                    code = "PRIVATE_SKETCH_CORROBORATED"
                    message = (
                        "Independent institutions observed a matching private fraud pattern, "
                        "and local account evidence corroborates it."
                    )
                elif fraud_sketch["independent_institutions"] >= 2:
                    code = "PRIVATE_SKETCH_UNCORROBORATED"
                    message = (
                        "Independent institutions observed a matching private fraud pattern; "
                        "without local corroboration it can only increase monitoring."
                    )
                else:
                    code = "PRIVATE_SKETCH_OBSERVE_ONLY"
                    message = (
                        "One institution reported a matching private fraud pattern; "
                        "a single report cannot trigger an intrusive action."
                    )
                if fraud_sketch["source_mode"] == "signed_cache":
                    message += " A short-lived signed outage cache supplied the shared signal."
                reasons = [{
                    "code": code,
                    "message": message,
                    "contribution": round(min(1.0, contribution), 6),
                }, *reasons]
            if model_score is not None and model_score >= 0.65:
                reasons = [
                    {
                        "code": "POPULATION_MODEL_MATCH",
                        "message": "The combination of signals resembles account-takeover patterns.",
                        "contribution": round(min(1.0, model_score * 0.30), 6),
                    },
                    *reasons,
                ]
            if fusion.driver == "security_floor":
                reasons = [
                    {
                        "code": "SECURITY_FLOOR_APPLIED",
                        "message": (
                            "A named security rule set the minimum risk: "
                            + ", ".join(fusion.security_floor_codes)
                            + "."
                        ),
                        "contribution": round(
                            max(0.0, fusion.security_floor - fusion.blended_score), 6
                        ),
                    },
                    *reasons,
                ]
            if not reasons:
                reasons = [
                    {
                        "code": "NO_MATERIAL_ANOMALY",
                        "message": "No material departure from the available behavioural profile was detected.",
                        "contribution": 0.0,
                    }
                ]
            if resilience_context.mode != ResilienceMode.ONLINE:
                reasons = [
                    {
                        "code": "OUTAGE_EVIDENCE_DEGRADED",
                        "message": (
                            "One or more trusted services are unavailable; missing evidence lowered confidence "
                            "and activated the outage safety policy."
                        ),
                        "contribution": 0.0,
                    },
                    *reasons,
                ]
            reasons = reasons[:8]
            recourse_options = build_recourse_options(policy.action, policy.hold_seconds)
            customer_explanation = build_customer_explanation(policy.action, reasons, features)
            evidence = build_evidence_summary(event, features)
            evidence["missing_optional_signals"] = sorted(
                set(evidence["missing_optional_signals"] + resilience_context.unavailable_sources)
            )
            offline_reference = (
                self.resilience.offline_reference(tenant_id, event.event_id)
                if resilience_context.mode != ResilienceMode.ONLINE
                else None
            )
            if resilience_context.mode == ResilienceMode.ISOLATED and event.amount > 0:
                customer_explanation = (
                    "We could not settle this transaction because the payment network is unavailable; "
                    f"no money has been moved, keep reference {offline_reference} and confirm after service returns."
                )
            elif safety_envelope_applied and outage_policy_reason:
                customer_explanation = (
                    customer_explanation[:-1]
                    + "; some trusted checks are temporarily unavailable, so the safer reversible option was used."
                )
            risk_window = profile_before.get(
                "risk_window",
                {"state": "clear", "score": 0.0, "hours_remaining": 0.0, "active_precursors": []},
            )

            decision_id = f"dec_{uuid.uuid4().hex}"
            created_at = datetime.now(UTC)
            event_payload = event.model_dump(mode="json")
            event_payload["_tenant_id"] = tenant_id
            provisionally_safe = (
                policy.action.value in {"allow", "allow_with_monitoring"}
                and fused_score < 0.48
            )
            eligible_after = created_at + timedelta(hours=self.settings.learning_quarantine_hours)
            is_mature_historical = event.occurred_at <= created_at - timedelta(hours=self.settings.learning_quarantine_hours)
            trust_state = "trusted" if provisionally_safe and is_mature_historical else "pending" if provisionally_safe else "excluded"
            if resilience_context.mode != ResilienceMode.ONLINE:
                trust_state = "excluded"
            event_payload["_profile_eligible"] = trust_state == "trusted"
            self.database.insert_event(event_payload, tenant_id)
            self.database.set_event_trust(
                event.event_id, trust_state,
                eligible_after=eligible_after if trust_state == "pending" else None,
                reason=(
                    "outage_learning_frozen"
                    if resilience_context.mode != ResilienceMode.ONLINE
                    else "safe_learning_quarantine"
                    if trust_state == "pending"
                    else policy.action.value
                ),
            )

            updated_history = [*history, event_payload]
            profile_after = self.profile_builder.build(
                event.account_id,
                updated_history,
                reference_time=max(created_at, event.occurred_at),
                profile_version=int(profile_before["profile_version"]) + 1,
            )
            self.database.save_profile(event.account_id, profile_after)

            decision_record = {
                "decision_id": decision_id,
                "event_id": event.event_id,
                "account_id": event.account_id,
                "risk_score": fused_score,
                "model_score": model_score,
                "anomaly_score": anomaly.score,
                "profile_confidence": features["history_confidence"],
                "risk_level": risk_level.value,
                "action": policy.action.value,
                "model_version": self.model_bundle.version,
                "reasons": reasons,
                "customer_explanation": customer_explanation,
                "evidence": evidence,
                "risk_window": risk_window,
                "decision_confidence": decision_confidence,
                "recipient_reputation": {
                    key: recipient_reputation[key]
                    for key in (
                        "status",
                        "score",
                        "confirmed_reports",
                        "distinct_accounts",
                        "expires_at",
                    )
                },
                "agent_terminal": {
                    key: agent_reputation[key]
                    for key in (
                        "status",
                        "score",
                        "confirmed_reports",
                        "distinct_accounts",
                        "quarantined",
                        "expires_at",
                    )
                },
                "fraud_sketch_exchange": {
                    key: fraud_sketch[key]
                    for key in (
                        "status",
                        "score",
                        "confidence",
                        "independent_institutions",
                        "active_reports",
                        "matched_indicators",
                        "source_mode",
                        "local_corroboration",
                        "action_ceiling",
                        "expires_at",
                    )
                },
                "recourse_options": recourse_options,
                "feature_snapshot": features,
                "policy": policy.as_dict(),
                "uncertainty_note": uncertainty_note,
                "audit_hash": None,
                "created_at": iso_utc(created_at),
                "tenant_id": tenant_id,
                "campaign": campaign,
                "learning": {
                    "trust_state": trust_state,
                    "eligible_after": iso_utc(eligible_after) if trust_state == "pending" else None,
                    "profile_epoch": int(profile_after["profile_version"]),
                },
                "transaction_state": "created",
                "resilience": {
                    **resilience_context.as_dict(),
                    "safety_envelope_applied": safety_envelope_applied,
                    "offline_reference": offline_reference,
                },
            }
            provenance = evidence_provenance(
                event_payload, features, model_version=self.model_bundle.version,
                policy_version=self.settings.policy_version, cutoff_at=event.occurred_at,
            )
            decision_record["provenance"] = provenance
            self.database.insert_decision(decision_record)

            if resilience_context.mode != ResilienceMode.ONLINE:
                journal = self.database.append_offline_journal(
                    f"journal_{uuid.uuid4().hex}",
                    tenant_id,
                    event.event_id,
                    event.occurred_at,
                    {
                        "decision_id": decision_id,
                        "offline_reference": offline_reference,
                        "mode": resilience_context.mode.value,
                        "risk_score": fused_score,
                        "action": policy.action.value,
                        "event_digest": provenance["event_digest"],
                    },
                )
                decision_record["resilience"]["journal_id"] = journal["journal_id"]
                self.telemetry.increment("offline_journaled")

            initial_state = "held" if policy.action.value in {"reversible_hold_and_review", "private_safety_pause", "reversible_settlement_delay"} else "authorized"
            self.database.transition_lifecycle(
                event.event_id, initial_state, "policy-engine", policy.action.value,
                f"policy-{decision_id}",
            )
            decision_record["transaction_state"] = initial_state
            self.database.enqueue("decision.created", {"decision_id": decision_id, "action": policy.action.value})
            if policy.requires_analyst_review or fused_score >= 0.84:
                self.database.create_case(
                    f"case_{uuid.uuid4().hex}", tenant_id, decision_id,
                    review_priority(
                        fused_score,
                        event.amount,
                        decision_confidence["score"],
                        recipient_reputation["confirmed_reports"]
                        + agent_reputation["confirmed_reports"]
                        + fraud_sketch["active_reports"],
                    ),
                )
            elif int(hashlib.sha256(decision_id.encode()).hexdigest()[:6], 16) % 100 == 0:
                self.database.create_case(f"audit_{uuid.uuid4().hex}", tenant_id, decision_id, 0.1, random_audit=True)
            self.telemetry.increment(f"action_{policy.action.value}")

            event_digest = hashlib.sha256(canonical_json(event_payload).encode("utf-8")).hexdigest()
            audit_hash = self.audit.append(
                "risk_decision",
                decision_id,
                {
                    "decision_id": decision_id,
                    "event_id": event.event_id,
                    "account_id": event.account_id,
                    "event_digest": event_digest,
                    "risk_score": fused_score,
                    "risk_level": risk_level.value,
                    "action": policy.action.value,
                    "model_version": self.model_bundle.version,
                    "customer_explanation_digest": hashlib.sha256(
                        customer_explanation.encode("utf-8")
                    ).hexdigest(),
                    "feature_digest": hashlib.sha256(
                        canonical_json(features).encode("utf-8")
                    ).hexdigest(),
                    "resilience_mode": resilience_context.mode.value,
                    "offline_reference": offline_reference,
                    "fraud_sketch_digest": hashlib.sha256(
                        canonical_json(decision_record["fraud_sketch_exchange"]).encode("utf-8")
                    ).hexdigest(),
                },
            )
            self.database.set_decision_audit_hash(decision_id, audit_hash)
            decision_record["audit_hash"] = audit_hash
            return self._decision_response(decision_record)

    def get_profile(self, account_id: str, tenant_id: str = "default") -> ProfileResponse:
        account = self.database.get_account(account_id, tenant_id)
        if account is None:
            raise NotFoundError(f"account not found: {account_id}")
        profile = self.database.get_profile(account_id)
        if profile is None:
            profile = self.profile_builder.build(account_id, [], profile_version=0)
        return ProfileResponse.model_validate(profile)

    def get_decisions(self, account_id: str, limit: int = 100, tenant_id: str = "default") -> list[RiskDecisionResponse]:
        if self.database.get_account(account_id, tenant_id) is None:
            raise NotFoundError(f"account not found: {account_id}")
        return [self._decision_response(row) for row in self.database.get_decisions(account_id, limit, tenant_id)]

    def agent_terminal_status(
        self, terminal_token: str, tenant_id: str = "default"
    ) -> dict[str, Any]:
        reputation = self.database.get_agent_terminal_reputation(
            terminal_token, tenant_id=tenant_id
        )
        return {
            "terminal_reference": hashlib.sha256(
                f"{tenant_id}|{terminal_token}".encode()
            ).hexdigest()[:16],
            **{
                key: reputation[key]
                for key in (
                    "status",
                    "score",
                    "confirmed_reports",
                    "distinct_accounts",
                    "quarantined",
                    "expires_at",
                )
            },
        }

    def add_feedback(self, decision_id: str, request: FeedbackRequest, tenant_id: str = "default") -> dict[str, Any]:
        decision = self.database.get_decision(decision_id, tenant_id)
        if decision is None:
            raise NotFoundError(f"decision not found: {decision_id}")
        payload = request.model_dump(mode="json")
        reputation_update = None
        agent_reputation_update = None
        event = None
        if request.label.value in {"account_takeover", "other_fraud"}:
            event = self.database.get_event(decision["event_id"], tenant_id)
            if event and event.get("recipient_id"):
                existing_reputation = self.database.get_recipient_reputation(str(event["recipient_id"]))
                if existing_reputation["confirmed_reports"] >= 1 and not request.second_approver_id:
                    raise ConflictError("a second approver is required to strengthen recipient reputation")
            assurance = event.get("agent_assurance") if event else None
            if isinstance(assurance, dict) and assurance.get("gateway_attested"):
                existing_agent = self.database.get_agent_terminal_reputation(
                    str(assurance["terminal_token"]), tenant_id=tenant_id
                )
                if existing_agent["confirmed_reports"] >= 1 and not request.second_approver_id:
                    raise ConflictError(
                        "a second approver is required to strengthen agent-terminal reputation"
                    )
            if request.second_approver_id == request.analyst_id:
                raise ConflictError("the second approver must be independent")
        result = self.database.add_feedback(decision_id, payload)
        if request.label.value in {"account_takeover", "other_fraud"}:
            if event and event.get("recipient_id"):
                reputation_update = self.database.record_recipient_fraud(
                    str(event["recipient_id"]), str(decision["account_id"])
                )
            assurance = event.get("agent_assurance") if event else None
            if isinstance(assurance, dict) and assurance.get("gateway_attested"):
                agent_reputation_update = self.database.record_agent_terminal_fraud(
                    str(assurance["terminal_token"]),
                    str(decision["account_id"]),
                    tenant_id=tenant_id,
                )
            self.database.set_event_trust(decision["event_id"], "revoked", reason=request.label.value)
            self.database.set_event_profile_eligibility(decision["event_id"], False)
            self._rebuild_profile(str(decision["account_id"]), tenant_id)
        elif request.label.value == "legitimate":
            self.database.set_event_trust(decision["event_id"], "trusted", reason="analyst_confirmed_legitimate")
            self.database.set_event_profile_eligibility(decision["event_id"], True)
            self._rebuild_profile(str(decision["account_id"]), tenant_id)
        analyst_digest = hashlib.sha256(request.analyst_id.encode("utf-8")).hexdigest()
        result["audit_hash"] = self.audit.append(
            "decision_feedback",
            decision_id,
            {
                "decision_id": decision_id,
                "label": request.label.value,
                "analyst_digest": analyst_digest,
                "notes_present": bool(request.notes),
                "recipient_reputation_updated": reputation_update is not None,
                "agent_terminal_reputation_updated": agent_reputation_update is not None,
            },
        )
        result["recipient_reputation_update"] = reputation_update
        result["agent_terminal_reputation_update"] = agent_reputation_update
        return result

    def _rebuild_profile(self, account_id: str, tenant_id: str) -> None:
        events = self.database.get_events(account_id, tenant_id=tenant_id, limit=self.settings.max_history_events)
        previous = self.database.get_profile(account_id)
        profile = self.profile_builder.build(
            account_id, events, reference_time=datetime.now(UTC),
            profile_version=int(previous["profile_version"] if previous else 0) + 1,
        )
        self.database.save_profile(account_id, profile)

    def _enforce_evidence_freshness(self, event: BehaviorEventIn) -> BehaviorEventIn:
        observed = event.metadata.get("gateway_observed_at")
        if not observed:
            return event
        try:
            parsed = datetime.fromisoformat(str(observed)).astimezone(UTC)
        except ValueError:
            parsed = event.occurred_at - timedelta(days=1)
        if abs((event.occurred_at - parsed).total_seconds()) <= self.settings.evidence_max_age_seconds:
            return event
        updates: dict[str, Any] = {}
        if event.telco_assurance:
            updates["telco_assurance"] = event.telco_assurance.model_copy(update={"gateway_attested": False})
        if event.coercion_signals:
            updates["coercion_signals"] = event.coercion_signals.model_copy(update={"consented_device_attested": False})
        if event.agent_assurance:
            updates["agent_assurance"] = event.agent_assurance.model_copy(
                update={"gateway_attested": False}
            )
        metadata = dict(event.metadata)
        metadata["evidence_freshness_status"] = "stale_ignored"
        updates["metadata"] = metadata
        return event.model_copy(update=updates)

    def mature_learning(self, at: datetime | None = None) -> dict[str, Any]:
        matured = self.database.mature_learning_events(at=at)
        accounts: set[str] = set()
        for event_id in matured:
            self.database.set_event_profile_eligibility(event_id, True)
            event = self.database.get_event(event_id)
            if event:
                accounts.add(str(event["account_id"]))
        for account_id in accounts:
            self._rebuild_profile(account_id, "default")
        return {"matured_events": len(matured), "accounts_rebuilt": len(accounts)}

    def model_status(self) -> dict[str, Any]:
        payload = {
            "available": self.model_bundle.available,
            "version": self.model_bundle.version,
            "artifact_hash": self.model_bundle.artifact_hash,
            "training_data_hash": self.model_bundle.training_data_hash,
            "feature_schema_hash": self.model_bundle.feature_schema_hash,
            "metrics": self.model_bundle.metrics,
            "load_error": self.model_bundle.load_error,
            "inference_path": self.model_bundle.inference_path,
            "policy_version": self.settings.policy_version,
        }
        payload["registry_signature"] = hashlib.sha256(
            f"{payload['artifact_hash']}|{payload['training_data_hash']}|{payload['feature_schema_hash']}|{self.settings.audit_anchor_key}".encode()
        ).hexdigest()
        return payload

    def replay_decision(self, decision_id: str, tenant_id: str = "default") -> dict[str, Any]:
        decision = self.database.get_decision(decision_id, tenant_id)
        if decision is None:
            raise NotFoundError(f"decision not found: {decision_id}")
        stored = decision.get("provenance", {})
        replay_material = {
            key: stored[key]
            for key in ("event_digest", "feature_digest", "model_version", "policy_version", "cutoff_at")
        }
        replay_digest = hashlib.sha256(canonical_json(replay_material).encode()).hexdigest()
        return {
            "decision_id": decision_id,
            "exact_match": replay_digest == stored.get("replay_digest"),
            "stored_digest": stored.get("replay_digest", ""),
            "replay_digest": replay_digest,
            "model_version": stored.get("model_version", decision["model_version"]),
            "policy_version": stored.get("policy_version", self.settings.policy_version),
            "cutoff_at": stored.get("cutoff_at", decision["created_at"]),
        }

    def transition_lifecycle(
        self, event_id: str, request: LifecycleTransitionRequest, tenant_id: str = "default",
    ) -> dict[str, Any]:
        event = self.database.get_event(event_id, tenant_id)
        if not event:
            raise NotFoundError(f"event not found: {event_id}")
        try:
            result = self.database.transition_lifecycle(
                event_id, request.target_state.value, request.actor_id, request.reason,
                request.idempotency_key,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        self.database.enqueue("transaction.lifecycle", {"event_id": event_id, "state": request.target_state.value})
        self.audit.append("lifecycle_transition", event_id, result)
        return result

    def create_appeal(self, decision_id: str, request: AppealRequest, tenant_id: str = "default") -> dict[str, Any]:
        if self.database.get_decision(decision_id, tenant_id) is None:
            raise NotFoundError(f"decision not found: {decision_id}")
        appeal = self.database.create_appeal({
            "appeal_id": f"appeal_{uuid.uuid4().hex}", "tenant_id": tenant_id,
            "decision_id": decision_id, "reason": request.reason,
            "contact_channel": request.contact_channel, "created_at": iso_utc(datetime.now(UTC)),
        })
        self.audit.append("appeal_created", appeal["appeal_id"], {"decision_id": decision_id, "tenant_id": tenant_id})
        return appeal

    def consortium_report(self, request: ConsortiumReportRequest) -> dict[str, Any]:
        recipient_token = hmac_token(request.recipient_id, self.settings.recipient_hmac_key)
        institution_token = hmac_token(request.institution_id, self.settings.recipient_hmac_key)
        result = self.database.record_consortium_report(
            recipient_token, institution_token, request.confidence, request.evidence_class
        )
        self.audit.append("consortium_report", recipient_token[:16], {
            "institution_token": institution_token[:16], "independent_institutions": result["independent_institutions"]
        })
        return result

    def fraud_sketch_report(self, request: FraudSketchReportRequest) -> dict[str, Any]:
        now = datetime.now(UTC)
        age_seconds = (now - request.observed_at).total_seconds()
        if age_seconds > self.settings.fraud_sketch_max_age_seconds or age_seconds < -60:
            raise ConflictError("fraud-sketch report timestamp is stale or in the future")
        institution_id = request.institution_id.strip().lower()
        secret = self._institution_secret(institution_id)
        payload = request.model_dump(mode="python")
        if not verify_report(payload, secret, request.signature):
            raise ConflictError("fraud-sketch report signature is invalid")

        signature_digest = hashlib.sha256(request.signature.encode("utf-8")).hexdigest()
        existing = self.database.get_fraud_sketch_report(request.report_id)
        if existing:
            if str(existing["signature_digest"]) != signature_digest:
                raise ConflictError("fraud-sketch report id has conflicting content")
            summary = score_reports(
                self.database.fraud_sketch_reports(
                    str(existing["indicator_type"]), [str(existing["indicator_token"])]
                ),
                now,
            )
            return {
                "report_id": request.report_id,
                "accepted": True,
                "idempotent_replay": True,
                "indicator_type": existing["indicator_type"],
                "epoch_id": existing["epoch_id"],
                **summary,
                "privacy_notice": "No source identifier or customer record was stored.",
            }

        institution_hash = institution_token(
            institution_id, self.settings.fraud_sketch_token_key
        )
        recent = self.database.fraud_sketch_report_count(
            institution_hash, since=now - timedelta(hours=1)
        )
        if recent >= self.settings.fraud_sketch_reports_per_hour:
            raise ConflictError("fraud-sketch institution rate limit exceeded")
        if not self.database.claim_fraud_sketch_nonce(request.nonce, institution_hash):
            raise ConflictError("fraud-sketch nonce has already been used")

        epoch = epoch_id(request.observed_at, self.settings.fraud_sketch_epoch_days)
        token = indicator_token(
            request.indicator_type.value,
            request.indicator_value,
            self.settings.fraud_sketch_token_key,
            epoch=epoch,
        )
        expires_at = min(
            request.observed_at + timedelta(hours=request.ttl_hours),
            now + timedelta(days=self.settings.fraud_sketch_retention_days),
        )
        try:
            stored = self.database.record_fraud_sketch_report(
                {
                    "report_id": request.report_id,
                    "indicator_type": request.indicator_type.value,
                    "indicator_token": token,
                    "epoch_id": epoch,
                    "institution_token": institution_hash,
                    "confidence": request.confidence,
                    "evidence_class": request.evidence_class,
                    "observed_at": iso_utc(request.observed_at),
                    "expires_at": iso_utc(expires_at),
                    "signature_digest": signature_digest,
                    "created_at": iso_utc(now),
                }
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        capsule = self._refresh_fraud_sketch_capsule(
            request.indicator_type.value, token, epoch, now
        )
        self.audit.append(
            "fraud_sketch_report",
            request.report_id,
            {
                "indicator_type": request.indicator_type.value,
                "epoch_id": epoch,
                "institution_token_prefix": institution_hash[:12],
                "indicator_token_prefix": token[:12],
                "independent_institutions": capsule["independent_institutions"],
                "expires_at": iso_utc(expires_at),
            },
        )
        self.telemetry.increment("fraud_sketch_reports")
        return {
            "report_id": request.report_id,
            "accepted": True,
            "idempotent_replay": bool(stored["idempotent_replay"]),
            "indicator_type": request.indicator_type.value,
            "epoch_id": epoch,
            "score": capsule["score"],
            "confidence": capsule["confidence"],
            "independent_institutions": capsule["independent_institutions"],
            "active_reports": capsule["active_reports"],
            "status": capsule["status"],
            "expires_at": capsule["expires_at"],
            "privacy_notice": "No source identifier or customer record was stored.",
        }

    def revoke_fraud_sketch_report(
        self,
        report_id: str,
        request: FraudSketchRevocationRequest,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        age_seconds = (now - request.revoked_at).total_seconds()
        if age_seconds > self.settings.fraud_sketch_max_age_seconds or age_seconds < -60:
            raise ConflictError("fraud-sketch revocation timestamp is stale or in the future")
        institution_id = request.institution_id.strip().lower()
        secret = self._institution_secret(institution_id)
        payload = {"report_id": report_id, **request.model_dump(mode="python")}
        if not verify_revocation(payload, secret, request.signature):
            raise ConflictError("fraud-sketch revocation signature is invalid")
        institution_hash = institution_token(
            institution_id, self.settings.fraud_sketch_token_key
        )
        if not self.database.claim_fraud_sketch_nonce(request.nonce, institution_hash):
            raise ConflictError("fraud-sketch nonce has already been used")
        try:
            revoked = self.database.revoke_fraud_sketch_report(
                report_id,
                institution_hash,
                request.reason,
                request.revoked_at,
            )
        except KeyError as exc:
            raise NotFoundError(f"fraud-sketch report not found: {report_id}") from exc
        except PermissionError as exc:
            raise ConflictError(str(exc)) from exc
        capsule = self._refresh_fraud_sketch_capsule(
            str(revoked["indicator_type"]),
            str(revoked["indicator_token"]),
            str(revoked["epoch_id"]),
            now,
        )
        self.audit.append(
            "fraud_sketch_revoked",
            report_id,
            {
                "institution_token_prefix": institution_hash[:12],
                "reason_digest": hashlib.sha256(request.reason.encode("utf-8")).hexdigest(),
                "remaining_independent_institutions": capsule["independent_institutions"],
            },
        )
        self.telemetry.increment("fraud_sketch_revocations")
        return {
            "report_id": report_id,
            "status": "revoked",
            "idempotent_replay": bool(revoked["idempotent_replay"]),
            "remaining_score": capsule["score"],
            "remaining_independent_institutions": capsule["independent_institutions"],
            "privacy_notice": "The private indicator remains undisclosed.",
        }

    def fraud_sketch_status(
        self,
        indicator_type: str,
        indicator_value: str,
        *,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        reference = (at or datetime.now(UTC)).astimezone(UTC)
        summary = self._fraud_sketch_indicator_summary(
            indicator_type,
            indicator_value,
            reference,
            exchange_available=True,
        )
        return {
            "indicator_type": indicator_type,
            "score": summary["score"],
            "confidence": summary["confidence"],
            "independent_institutions": summary["independent_institutions"],
            "active_reports": summary["active_reports"],
            "status": summary["status"],
            "expires_at": summary.get("expires_at"),
            "source_mode": summary["source_mode"],
            "privacy_notice": "Tokens, institution identities and source values are not returned.",
        }

    def policy_simulation(self, request: PolicySimulationRequest, tenant_id: str = "default") -> dict[str, Any]:
        rows = self.database.decision_scores(tenant_id)
        thresholds = {
            "allow": request.monitor_threshold, "monitor": request.confirm_threshold,
            "confirm": request.delay_threshold, "delay": request.hold_threshold,
        }
        counts = {"allow": 0, "monitor": 0, "confirm": 0, "delay": 0, "hold": 0}
        for row in rows:
            score = float(row["risk_score"])
            bucket = "hold" if score >= request.hold_threshold else "delay" if score >= request.delay_threshold else "confirm" if score >= request.confirm_threshold else "monitor" if score >= request.monitor_threshold else "allow"
            counts[bucket] += 1
        return {"policy_version": "simulation-only", "events": len(rows), "projected_actions": counts, "thresholds": thresholds, "mutated_live_policy": False}

    @staticmethod
    def _drift_status(value: float) -> str:
        return "alert" if value >= 0.25 else "watch" if value >= 0.10 else "stable"

    def drift_report(self, tenant_id: str = "default") -> dict[str, Any]:
        """Reference-window drift on scores, monitored features and action mix.

        The reference window is the earliest block of decisions after deployment (or after the
        last model promotion, since `model_version` is recorded per decision); the current window
        is the most recent block of the same size. PSI thresholds follow the usual 0.10 / 0.25
        convention. The report recommends, but never triggers, retraining: promotion stays a
        governed human action.
        """

        minimum_sample = 20
        rows = self.database.decision_scores(tenant_id)
        total = len(rows)
        base: dict[str, Any] = {
            "events": total,
            "minimum_sample_met": total >= minimum_sample,
            "population_stability_index": 0.0,
            "status": "stable",
            "window_size": 0,
            "reference_window": None,
            "current_window": None,
            "feature_drift": {},
            "action_drift": {"max_share_change": 0.0, "reference": {}, "current": {}},
            "model_versions_in_scope": sorted({str(row["model_version"]) for row in rows}),
            "retraining_recommended": False,
            "reasons": [],
        }
        if total < minimum_sample:
            base["reasons"].append(
                f"Fewer than {minimum_sample} decisions recorded; drift is not assessed."
            )
            return base

        window = min(500, total // 2)
        reference = rows[:window]
        current = rows[-window:]
        score_psi = psi(
            [float(row["risk_score"]) for row in reference],
            [float(row["risk_score"]) for row in current],
        )

        def snapshots(block: list[dict[str, Any]]) -> list[dict[str, float]]:
            output: list[dict[str, float]] = []
            for row in block:
                try:
                    output.append(json.loads(row.get("feature_snapshot_json") or "{}"))
                except (TypeError, ValueError):
                    output.append({})
            return output

        reference_snapshots = snapshots(reference)
        current_snapshots = snapshots(current)
        feature_drift: dict[str, dict[str, Any]] = {}
        for name in self.DRIFT_MONITORED_FEATURES:
            value = psi(
                [float(item.get(name, 0.0)) for item in reference_snapshots],
                [float(item.get(name, 0.0)) for item in current_snapshots],
            )
            feature_drift[name] = {"psi": value, "status": self._drift_status(value)}

        def action_shares(block: list[dict[str, Any]]) -> dict[str, float]:
            counts: dict[str, int] = {}
            for row in block:
                counts[str(row["action"])] = counts.get(str(row["action"]), 0) + 1
            return {key: round(value / max(1, len(block)), 6) for key, value in sorted(counts.items())}

        reference_actions = action_shares(reference)
        current_actions = action_shares(current)
        max_share_change = max(
            (
                abs(current_actions.get(key, 0.0) - reference_actions.get(key, 0.0))
                for key in set(reference_actions) | set(current_actions)
            ),
            default=0.0,
        )

        statuses = [self._drift_status(score_psi), *(item["status"] for item in feature_drift.values())]
        overall = "alert" if "alert" in statuses else "watch" if "watch" in statuses else "stable"
        alerting_features = [name for name, item in feature_drift.items() if item["status"] == "alert"]
        reasons: list[str] = []
        if self._drift_status(score_psi) != "stable":
            reasons.append(f"Fused score PSI is {score_psi:.3f} ({self._drift_status(score_psi)}).")
        for name in alerting_features:
            reasons.append(f"Feature {name!r} PSI is {feature_drift[name]['psi']:.3f} (alert).")
        if max_share_change >= 0.15:
            reasons.append(
                f"Action mix moved by {max_share_change:.1%} for at least one response class."
            )
        if len(base["model_versions_in_scope"]) > 1:
            reasons.append(
                "More than one model version is inside the window; compare per version before acting."
            )
        retraining_recommended = (
            self._drift_status(score_psi) == "alert" or len(alerting_features) >= 2
        )
        if retraining_recommended:
            thresholds = ", ".join(f"{key}={value}" for key, value in POLICY_THRESHOLDS.items())
            reasons.append(
                "Retraining is recommended: re-derive the policy thresholds "
                f"({thresholds}) on fresh labelled data and promote through the governed "
                "champion/challenger path."
            )
        if not reasons:
            reasons.append("Score, monitored features and action mix are within stable PSI bounds.")

        base.update(
            {
                "population_stability_index": score_psi,
                "status": overall,
                "window_size": window,
                "reference_window": {
                    "from": reference[0]["created_at"],
                    "to": reference[-1]["created_at"],
                    "events": len(reference),
                },
                "current_window": {
                    "from": current[0]["created_at"],
                    "to": current[-1]["created_at"],
                    "events": len(current),
                },
                "feature_drift": feature_drift,
                "action_drift": {
                    "max_share_change": round(max_share_change, 6),
                    "reference": reference_actions,
                    "current": current_actions,
                },
                "retraining_recommended": retraining_recommended,
                "reasons": reasons,
            }
        )
        return base

    def equity_report(self, tenant_id: str = "default") -> dict[str, Any]:
        rows = self.database.decision_scores(tenant_id)
        actions: dict[str, int] = {}
        for row in rows:
            actions[str(row["action"])] = actions.get(str(row["action"]), 0) + 1
        return {"scope": "channel-and-friction operational equity; no protected attributes inferred",
                "events": len(rows), "action_distribution": actions,
                "warning": "Outcome parity requires representative labels and approved protected-attribute governance."}

    def privacy_request(self, request: PrivacyRequest, tenant_id: str = "default") -> dict[str, Any]:
        if self.database.get_account(request.account_id, tenant_id) is None:
            raise NotFoundError(f"account not found: {request.account_id}")
        result = self.database.create_privacy_request({
            "request_id": f"privacy_{uuid.uuid4().hex}", "tenant_id": tenant_id,
            **request.model_dump(), "created_at": iso_utc(datetime.now(UTC)),
        })
        self.audit.append("privacy_request", result["request_id"], {"type": request.request_type, "tenant_id": tenant_id})
        return result

    def profile_succession(self, request: ProfileSuccessionRequest, tenant_id: str = "default") -> dict[str, Any]:
        if self.database.get_account(request.account_id, tenant_id) is None:
            raise NotFoundError(f"account not found: {request.account_id}")
        approved = request.trusted_device_confirmed and request.official_callback_confirmed
        result = {
            "account_id": request.account_id,
            "approved": approved,
            "mode": "conservative_reseed" if approved else "verification_required",
            "old_profile_retained_for_monitoring": True,
            "learning_quarantine_hours": self.settings.learning_quarantine_hours,
        }
        self.audit.append("profile_succession", request.account_id, {"tenant_id": tenant_id, **result})
        return result

    def audit_anchor(self) -> dict[str, Any]:
        verified = self.audit.verify()
        head = verified.get("head_hash") or "genesis"
        return self.database.anchor_audit(str(head), self.settings.audit_anchor_key)

    def sign_resilience_heartbeat(self, request: OutageHeartbeatRequest) -> str:
        return self.resilience.sign_heartbeat(request)

    def resilience_heartbeat(
        self,
        request: OutageHeartbeatRequest,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        try:
            state = self.resilience.apply_heartbeat(tenant_id, request)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        context = self.resilience.context(tenant_id)
        self.audit.append(
            "resilience_mode_changed",
            tenant_id,
            {
                "mode": context.mode.value,
                "previous_mode": state.get("previous_mode"),
                "source_id": request.source_id,
                "unavailable_sources": context.unavailable_sources,
            },
        )
        self.telemetry.increment(f"resilience_{context.mode.value}")
        return {**state, "context": context.as_dict()}

    def simulate_resilience_mode(
        self,
        request: OutageSimulationRequest,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        if self.settings.environment == "production":
            raise ConflictError("outage simulation is disabled in production")
        available = request.mode in {ResilienceMode.ONLINE, ResilienceMode.RECONCILING}
        heartbeat = OutageHeartbeatRequest(
            source_id="demo-resilience-simulator",
            observed_at=datetime.now(UTC),
            nonce=f"demo-{uuid.uuid4().hex}",
            core_banking_available=request.mode != ResilienceMode.ISOLATED,
            telco_gateway_available=available,
            consortium_available=available,
            recipient_graph_available=available,
            model_runtime_available=available,
            signature="0" * 64,
        )
        heartbeat = heartbeat.model_copy(
            update={"signature": self.sign_resilience_heartbeat(heartbeat)}
        )
        return self.resilience_heartbeat(heartbeat, tenant_id)

    def resilience_status(self, tenant_id: str = "default") -> dict[str, Any]:
        context = self.resilience.context(tenant_id)
        journal = self.database.verify_offline_journal(tenant_id)
        pending = self.database.list_offline_journal(tenant_id, status="pending", limit=10_000)
        return {
            **context.as_dict(),
            "pending_journal_events": len(pending),
            "oldest_pending_event_at": pending[0]["original_occurred_at"] if pending else None,
            "journal_integrity": journal,
        }

    def _reconciliation_rescore(self, event: BehaviorEventIn, tenant_id: str) -> dict[str, Any]:
        account = self.database.get_account(event.account_id, tenant_id)
        if account is None:
            raise NotFoundError(f"account not found: {event.account_id}")
        history = self.database.get_events(
            event.account_id,
            tenant_id=tenant_id,
            before=event.occurred_at,
            since=event.occurred_at - timedelta(days=self.settings.profile_lookback_days),
            limit=self.settings.max_history_events,
        )
        network_events = self.database.get_network_events(
            before=event.occurred_at,
            since=event.occurred_at - timedelta(days=7),
            tenant_id=tenant_id,
        )
        recipient_context = summarize_recipient_network(
            network_events, event.recipient_id, event.account_id, event.occurred_at
        )
        reputation = self.database.get_recipient_reputation(event.recipient_id, at=event.occurred_at)
        recipient_context.update(
            {
                "confirmed_fraud_score": reputation["score"],
                "confirmed_distinct_accounts": reputation["distinct_accounts"],
                "watchlist_evidence_available": reputation["watchlist_evidence_available"],
            }
        )
        terminal_token = (
            event.agent_assurance.terminal_token
            if event.agent_assurance and event.agent_assurance.gateway_attested
            else None
        )
        agent_reputation = self.database.get_agent_terminal_reputation(
            terminal_token, tenant_id=tenant_id, at=event.occurred_at
        )
        agent_context = summarize_agent_terminal(
            network_events, event, agent_reputation
        )
        features, _ = self.feature_engine.extract(
            event, history, account, recipient_context, agent_context
        )
        anomaly = self.anomaly_scorer.score(features)
        model_score = self.model_bundle.predict(features)
        fusion = self._fuse(model_score, anomaly.score, features)
        score, note = fusion.fused_score, fusion.note
        if event.recipient_id:
            consortium = self.database.consortium_score(
                hmac_token(event.recipient_id, self.settings.recipient_hmac_key)
            )
            if consortium["score"] >= 0.70:
                score = max(score, min(0.96, consortium["score"] + 0.04))
        _, stages = campaign_signature(event.model_dump(mode="json"), features)
        fraud_sketch, score = self._fraud_sketch_for_event(
            event,
            "|".join(stages),
            terminal_token,
            event.occurred_at,
            score,
            features,
            reputation,
            agent_reputation,
            0.0,
            exchange_available=True,
        )
        confidence = build_decision_confidence(features, model_score, anomaly.score)
        return {
            "restored_score": round(score, 6),
            "restored_confidence": confidence["score"],
            "restored_risk_level": risk_level_for_score(score).value,
            "uncertainty_note": note,
            "fraud_sketch_exchange": fraud_sketch,
        }

    def reconcile_outage(
        self,
        request: ReconciliationRequest,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        context = self.resilience.context(tenant_id)
        pending = self.database.list_offline_journal(
            tenant_id, status="pending", limit=100_000
        )
        pending.sort(
            key=lambda item: (
                -float(item["payload"].get("risk_score", 0.0)),
                int(item["sequence"]),
            )
        )
        pending = pending[: request.batch_size]
        if context.mode == ResilienceMode.ONLINE and not pending:
            return {
                "status": "already_reconciled",
                "processed": 0,
                "failed": 0,
                "duplicate_actions": 0,
                "integrity_valid": self.database.verify_offline_journal(tenant_id)["valid"],
                "remaining": 0,
            }
        if context.mode != ResilienceMode.RECONCILING:
            raise ConflictError("all trusted services must return before reconciliation begins")

        integrity = self.database.verify_offline_journal(tenant_id)
        run_id = f"reconcile_{uuid.uuid4().hex}"
        self.database.start_reconciliation_run(run_id, tenant_id)
        if not integrity["valid"]:
            result = self.database.finish_reconciliation_run(
                run_id,
                status="blocked_integrity_failure",
                processed=0,
                failed=len(pending),
                duplicate_actions=0,
                integrity_valid=False,
            )
            self.audit.append("reconciliation_blocked", run_id, integrity)
            return {**result, "remaining": len(pending), "journal_integrity": integrity}

        processed = 0
        failed = 0
        circuit_breaker_open = False
        failure_budget = max(1, min(5, request.batch_size // 10))
        score_changes: list[dict[str, Any]] = []
        for item in pending:
            try:
                raw_event = self.database.get_event(str(item["event_id"]), tenant_id)
                if raw_event is None:
                    raise NotFoundError(f"event not found: {item['event_id']}")
                restored = self._reconciliation_rescore(
                    BehaviorEventIn.model_validate(raw_event), tenant_id
                )
                original_score = float(item["payload"].get("risk_score", 0.0))
                restored["event_id"] = str(item["event_id"])
                restored["journal_id"] = str(item["journal_id"])
                restored["original_score"] = original_score
                restored["score_delta"] = round(restored["restored_score"] - original_score, 6)
                restored["automatic_settlement_performed"] = False
                self.database.mark_offline_reconciled(str(item["journal_id"]), restored)
                score_changes.append(restored)
                processed += 1
            except (NotFoundError, ValueError):
                failed += 1
                if failed >= failure_budget:
                    circuit_breaker_open = True
                    break

        remaining = len(
            self.database.list_offline_journal(tenant_id, status="pending", limit=100_000)
        )
        status = (
            "circuit_breaker_open"
            if circuit_breaker_open
            else "completed"
            if failed == 0 and remaining == 0
            else "partial"
        )
        result = self.database.finish_reconciliation_run(
            run_id,
            status=status,
            processed=processed,
            failed=failed,
            duplicate_actions=0,
            integrity_valid=True,
        )
        if status == "completed":
            self.database.complete_reconciliation(tenant_id)
        self.audit.append(
            "outage_reconciled",
            run_id,
            {
                "tenant_id": tenant_id,
                "processed": processed,
                "failed": failed,
                "remaining": remaining,
                "duplicate_actions": 0,
            },
        )
        self.telemetry.increment("outage_reconciled_events", processed)
        return {
            **result,
            "remaining": remaining,
            "journal_integrity": integrity,
            "score_changes": score_changes,
            "priority_order": "risk_descending_then_original_sequence",
            "batch_limit": request.batch_size,
            "failure_budget": failure_budget,
            "circuit_breaker_open": circuit_breaker_open,
            "final_mode": self.resilience.context(tenant_id).mode.value,
        }

    def _decision_response(self, record: dict[str, Any]) -> RiskDecisionResponse:
        return RiskDecisionResponse.model_validate(
            {
                "decision_id": record["decision_id"],
                "event_id": record["event_id"],
                "account_id": record["account_id"],
                "risk_level": record["risk_level"],
                "score": {
                    "model_score": record.get("model_score"),
                    "anomaly_score": record["anomaly_score"],
                    "fused_score": record["risk_score"],
                    "profile_confidence": record["profile_confidence"],
                    "model_version": record["model_version"],
                },
                "policy": record["policy"],
                "reasons": record["reasons"],
                "customer_explanation": record["customer_explanation"],
                "evidence": record["evidence"],
                "risk_window": record["risk_window"],
                "decision_confidence": record["decision_confidence"],
                "recipient_reputation": record["recipient_reputation"],
                "agent_terminal": record.get(
                    "agent_terminal",
                    {
                        "status": "not_applicable",
                        "score": 0.0,
                        "confirmed_reports": 0,
                        "distinct_accounts": 0,
                        "quarantined": False,
                        "expires_at": None,
                    },
                ),
                "fraud_sketch_exchange": record.get("fraud_sketch_exchange", {}),
                "recourse_options": record["recourse_options"],
                "uncertainty_note": record.get("uncertainty_note"),
                "feature_snapshot": record["feature_snapshot"],
                "audit_hash": record.get("audit_hash") or "pending",
                "created_at": record["created_at"],
                "campaign": record.get("campaign", {}),
                "learning": record.get("learning", {}),
                "provenance": record.get("provenance", {}),
                "transaction_state": record.get("transaction_state", "created"),
                "resilience": record.get("resilience", {}),
            }
        )
