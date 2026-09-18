from __future__ import annotations

import hashlib
import math
import pickle
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .features import MODEL_FEATURE_NAMES, clamp
from .schemas import BehaviorEventIn, Channel, InputMethod, ResponseAction

REASON_MESSAGES = {
    "amount_deviation": "Amount differs sharply from this account's normal transaction range.",
    "amount_to_median": "Amount is many times larger than the account's typical transaction.",
    "balance_drain_ratio": "The transaction would remove a large share of the available balance.",
    "unusual_hour": "Activity occurred outside the account's usual operating hours.",
    "new_recipient": "The recipient has not previously been used by this account.",
    "recipient_rarity": "The recipient is rare in the account's historical activity.",
    "recipient_sender_diversity_24h": "The recipient recently received funds from many different senders.",
    "recipient_first_time_sender_ratio_24h": "Most recent senders had never paid this recipient before.",
    "recipient_inflow_velocity_1h": "Value is accumulating rapidly at the recipient.",
    "recipient_rapid_cashout_ratio_1h": "The recipient rapidly moved out recently received funds.",
    "recipient_confirmed_fraud_score": "Analyst-confirmed fraud reports are associated with this recipient.",
    "recipient_confirmed_accounts": "Multiple unrelated accounts reported fraud involving this recipient.",
    "new_device": "The event originated from a device not seen in the account history.",
    "device_rarity": "The device is unusual for this account.",
    "new_sim": "The SIM identity is new for this account.",
    "new_ip_prefix": "The network prefix has not previously been associated with the account.",
    "new_channel": "The customer switched to a channel not normally used by this account.",
    "channel_transition_novelty": "The sequence between banking channels is unusual for this account.",
    "cross_channel_events_15m": "Several different banking channels were used in a short period.",
    "new_channel_enrollment_24h": "A new-channel authentication event preceded this transaction.",
    "app_to_ussd_handoff": "App activity was followed quickly by a USSD transaction.",
    "cross_channel_device_mismatch": "Recent cross-channel activity used inconsistent devices.",
    "velocity_5m": "Several transactions occurred within five minutes.",
    "velocity_1h": "Transaction frequency is elevated over the last hour.",
    "failed_auth_24h": "Recent failed authentication attempts preceded this event.",
    "recovery_signal_72h": "A recent PIN reset or account-recovery event increases takeover risk.",
    "account_hazard_score": "Recent precursor events place this account inside a temporary risk window.",
    "impossible_travel": "Location changed faster than plausible physical travel.",
    "interaction_speed_deviation": "The app or USSD interaction rhythm differs from the user's norm.",
    "typing_cadence_deviation": "Typing cadence differs from the customer's usual rhythm.",
    "paste_anomaly": "Information was pasted where this customer normally types it.",
    "device_handling_deviation": "The way the phone was handled differs from the customer's usual pattern.",
    "navigation_novelty": "The sequence of screens or USSD menus is unfamiliar for this account.",
    "day_of_month_deviation": "The calendar date differs from this account's established monthly rhythm.",
    "call_transfer_overlap": "The transfer was prepared during an active call on a consented trusted device.",
    "screen_sharing_signal": "A consented trusted device detected screen sharing during the transfer.",
    "recipient_edit_anomaly": "The recipient was repeatedly replaced during this session.",
    "confirmation_friction": "Repeated edits, backtracking or hesitation occurred before confirmation.",
    "coercion_on_device_score": "A privacy-preserving on-device safety model detected possible coercion.",
    "recent_sim_activation": "A trusted telco signal shows that this SIM was activated recently.",
    "repeat_sim_change": "A trusted telco signal shows repeated SIM changes in the last 30 days.",
    "imsi_change": "The attested subscriber identity changed recently.",
    "iccid_change": "The attested SIM-card identity changed recently.",
    "sim_type_change": "The attested SIM type changed recently.",
    "otp_sim_change_proximity": "An OTP request closely followed the SIM change.",
    "otp_sim_geo_mismatch": "OTP and SIM-change locations were far apart.",
    "short_previous_sim_tenure": "The previous SIM had an unusually short tenure.",
    "agent_customer_diversity_1h": "The agent terminal handled many unrelated customers in a short period.",
    "agent_recipient_concentration_24h": "One recipient dominates this terminal's recent customer transfers.",
    "agent_first_time_recipient_ratio_24h": "Many customers used unfamiliar recipients through this terminal.",
    "agent_failed_auth_ratio_1h": "Authentication failures are concentrated at this terminal.",
    "agent_value_velocity_1h": "Unusually high value is moving through this terminal.",
    "agent_location_mismatch": "The terminal is operating far from its registered location.",
    "agent_after_hours": "The terminal is operating outside its registered service hours.",
    "agent_terminal_novelty": "The agency gateway reports a newly enrolled terminal.",
    "agent_confirmed_fraud_score": "Analyst-confirmed fraud reports are associated with this terminal.",
    "agent_confirmed_accounts": "Multiple unrelated customers reported fraud through this terminal.",
}


BASE_WEIGHTS = {
    "amount_deviation": 0.11,
    "amount_to_median": 0.05,
    "balance_drain_ratio": 0.09,
    "unusual_hour": 0.06,
    "new_recipient": 0.08,
    "recipient_rarity": 0.03,
    "recipient_sender_diversity_24h": 0.07,
    "recipient_first_time_sender_ratio_24h": 0.04,
    "recipient_inflow_velocity_1h": 0.06,
    "recipient_rapid_cashout_ratio_1h": 0.09,
    "recipient_confirmed_fraud_score": 0.13,
    "recipient_confirmed_accounts": 0.07,
    "new_device": 0.06,
    "device_rarity": 0.02,
    "new_sim": 0.11,
    "new_ip_prefix": 0.03,
    "new_channel": 0.02,
    "channel_transition_novelty": 0.04,
    "cross_channel_events_15m": 0.05,
    "new_channel_enrollment_24h": 0.09,
    "app_to_ussd_handoff": 0.04,
    "cross_channel_device_mismatch": 0.05,
    "velocity_5m": 0.10,
    "velocity_1h": 0.04,
    "failed_auth_24h": 0.10,
    "recovery_signal_72h": 0.10,
    "account_hazard_score": 0.10,
    "impossible_travel": 0.08,
    "interaction_speed_deviation": 0.05,
    "typing_cadence_deviation": 0.06,
    "paste_anomaly": 0.05,
    "device_handling_deviation": 0.04,
    "navigation_novelty": 0.05,
    "day_of_month_deviation": 0.035,
    "call_transfer_overlap": 0.03,
    "screen_sharing_signal": 0.09,
    "recipient_edit_anomaly": 0.05,
    "confirmation_friction": 0.05,
    "coercion_on_device_score": 0.08,
    "recent_sim_activation": 0.09,
    "repeat_sim_change": 0.06,
    "imsi_change": 0.05,
    "iccid_change": 0.05,
    "sim_type_change": 0.03,
    "otp_sim_change_proximity": 0.05,
    "otp_sim_geo_mismatch": 0.06,
    "short_previous_sim_tenure": 0.03,
    "agent_customer_diversity_1h": 0.03,
    "agent_recipient_concentration_24h": 0.04,
    "agent_first_time_recipient_ratio_24h": 0.02,
    "agent_failed_auth_ratio_1h": 0.07,
    "agent_value_velocity_1h": 0.04,
    "agent_location_mismatch": 0.08,
    "agent_after_hours": 0.03,
    "agent_terminal_novelty": 0.02,
    "agent_confirmed_fraud_score": 0.13,
    "agent_confirmed_accounts": 0.08,
}

PROFILE_DEPENDENT = {
    "unusual_hour",
    "new_recipient",
    "recipient_rarity",
    "new_device",
    "device_rarity",
    "new_sim",
    "new_ip_prefix",
    "new_channel",
    "channel_transition_novelty",
    "new_channel_enrollment_24h",
    "app_to_ussd_handoff",
    "cross_channel_device_mismatch",
    "interaction_speed_deviation",
    "typing_cadence_deviation",
    "paste_anomaly",
    "device_handling_deviation",
    "navigation_novelty",
    "day_of_month_deviation",
}


CUSTOMER_REASON_PHRASES = {
    "DEVICE_SIM_COCHANGE": "a new SIM and device appeared together",
    "RECOVERY_THEN_NEW_RECIPIENT": "a recent account recovery was followed by a new recipient",
    "UNUSUAL_BALANCE_DRAIN": "the amount was unusual and would move most of the available balance",
    "FAILED_AUTH_NEW_DEVICE": "failed sign-in attempts were followed by a new device",
    "USSD_RHYTHM_BURST": "the USSD timing and transaction pace changed together",
    "TELCO_SIM_SWAP_SIGNATURE": "a trusted network check found a very recent identity-changing SIM replacement",
    "OTP_SIM_GEO_CONFLICT": "an OTP followed the SIM change from a distant location",
    "MULE_COLLECTION_SIGNATURE": "the recipient showed a many-sender, rapid-movement pattern",
    "CONFIRMED_RECIPIENT_REPUTATION": "other confirmed fraud cases involved this recipient",
    "CROSS_CHANNEL_TAKEOVER_SEQUENCE": "a new cross-channel access sequence preceded the transfer",
    "CALENDAR_RHYTHM_MATCH": "the payment matched an established monthly pattern",
    "ACCOUNT_RISK_WINDOW": "recent recovery or authentication activity raised temporary account risk",
    "COERCION_SESSION_SIGNATURE": "the session showed signs that someone may be directing the customer",
    "AGENT_TERMINAL_CAMPAIGN": "the agency terminal connected several customers to a concentrated suspicious pattern",
    "CONFIRMED_AGENT_TERMINAL": "independent confirmed fraud reports involve this agency terminal",
    "AMOUNT_DEVIATION": "the amount differed from the account's usual range",
    "BALANCE_DRAIN_RATIO": "the transfer would move a large part of the available balance",
    "NEW_RECIPIENT": "the recipient had not been used before",
    "NEW_DEVICE": "the device had not been used on this account before",
    "NEW_SIM": "the SIM had not been seen on this account before",
    "UNUSUAL_HOUR": "the transaction occurred outside the account's usual hours",
    "FAILED_AUTH_24H": "there were recent failed sign-in attempts",
    "RECOVERY_SIGNAL_72H": "the account was recently recovered or its PIN was reset",
    "INTERACTION_SPEED_DEVIATION": "the app or USSD interaction rhythm changed",
    "TYPING_CADENCE_DEVIATION": "the typing rhythm changed",
    "PASTE_ANOMALY": "information was pasted where it is normally typed",
    "DEVICE_HANDLING_DEVIATION": "the way the phone was handled changed",
    "NAVIGATION_NOVELTY": "an unfamiliar screen or USSD menu path was used",
    "IMPOSSIBLE_TRAVEL": "the location change was faster than normal travel",
    "RECENT_SIM_ACTIVATION": "the network reported a newly activated SIM",
    "REPEAT_SIM_CHANGE": "the network reported repeated recent SIM changes",
    "RECIPIENT_SENDER_DIVERSITY_24H": "the recipient recently received funds from many unrelated senders",
    "RECIPIENT_RAPID_CASHOUT_RATIO_1H": "the recipient rapidly moved out recently received funds",
    "ACCOUNT_HAZARD_SCORE": "the account was already inside a temporary risk window",
    "POPULATION_MODEL_MATCH": "several signals matched account-takeover patterns",
}


@dataclass(frozen=True)
class AnomalyResult:
    score: float
    reasons: list[dict[str, Any]]


class AnomalyScorer:
    """Transparent behavioural scorer used beside the population ML model."""

    def score(self, features: dict[str, float]) -> AnomalyResult:
        confidence = features["history_confidence"]
        shared_device_factor = 0.25 if features["shared_device_allowed"] else 1.0
        contributions: dict[str, float] = {}

        for feature, weight in BASE_WEIGHTS.items():
            multiplier = 1.0
            if feature in PROFILE_DEPENDENT:
                multiplier *= max(0.10, confidence)
            if feature in {"new_device", "device_rarity"}:
                multiplier *= shared_device_factor
            if feature in {
                "new_sim",
                "recent_sim_activation",
                "repeat_sim_change",
                "imsi_change",
                "iccid_change",
                "sim_type_change",
                "otp_sim_change_proximity",
                "otp_sim_geo_mismatch",
                "short_previous_sim_tenure",
            } and features["verified_sim_change"]:
                multiplier *= 0.05
            if feature == "day_of_month_deviation":
                multiplier *= features.get("calendar_confidence", 0.0)
            if feature in {
                "amount_deviation",
                "amount_to_median",
                "unusual_hour",
                "new_recipient",
                "recipient_rarity",
                "day_of_month_deviation",
            }:
                multiplier *= 1.0 - (
                    0.65
                    * features.get("recurring_payment_match", 0.0)
                    * features.get("calendar_confidence", 0.0)
                )
            contributions[feature] = weight * features.get(feature, 0.0) * multiplier

        compound_reasons: list[dict[str, Any]] = []
        compound_total = 0.0

        if (
            features["new_device"]
            and features["new_sim"]
            and not features["verified_sim_change"]
            and confidence >= 0.2
        ):
            value = 0.12 * max(0.25, confidence) * shared_device_factor
            compound_total += value
            compound_reasons.append(
                {
                    "code": "DEVICE_SIM_COCHANGE",
                    "message": "A new device and new SIM appeared together.",
                    "contribution": round(value, 6),
                }
            )
        if (
            features.get("new_channel_enrollment_24h", 0.0) >= 1.0
            and features.get("channel_transition_novelty", 0.0) >= 0.70
            and max(
                features.get("app_to_ussd_handoff", 0.0),
                features.get("cross_channel_device_mismatch", 0.0),
            ) > 0
        ):
            value = 0.13
            compound_total += value
            compound_reasons.append(
                {
                    "code": "CROSS_CHANNEL_TAKEOVER_SEQUENCE",
                    "message": "A new-channel authentication sequence was followed by a mismatched transfer.",
                    "contribution": value,
                }
            )
        if features.get("recipient_confirmed_fraud_score", 0.0) > 0:
            value = 0.08 * features["recipient_confirmed_fraud_score"]
            compound_total += value
            compound_reasons.append(
                {
                    "code": "CONFIRMED_RECIPIENT_REPUTATION",
                    "message": "Prior analyst-confirmed fraud reports involve this recipient.",
                    "contribution": round(value, 6),
                }
            )
        if features.get("agent_confirmed_fraud_score", 0.0) > 0:
            value = 0.08 * features["agent_confirmed_fraud_score"]
            compound_total += value
            compound_reasons.append(
                {
                    "code": "CONFIRMED_AGENT_TERMINAL",
                    "message": "Prior analyst-confirmed fraud reports involve this agency terminal.",
                    "contribution": round(value, 6),
                }
            )
        if features["recovery_signal_72h"] and features["new_recipient"]:
            value = 0.12
            compound_total += value
            compound_reasons.append(
                {
                    "code": "RECOVERY_THEN_NEW_RECIPIENT",
                    "message": "A recovery event was followed by payment to a new recipient.",
                    "contribution": value,
                }
            )
        if features["balance_drain_ratio"] >= 0.70 and features["amount_deviation"] >= 0.45:
            value = 0.09
            compound_total += value
            compound_reasons.append(
                {
                    "code": "UNUSUAL_BALANCE_DRAIN",
                    "message": "An unusually large transaction would drain most of the balance.",
                    "contribution": value,
                }
            )
        if features["failed_auth_24h"] >= 0.40 and features["new_device"]:
            value = 0.08
            compound_total += value
            compound_reasons.append(
                {
                    "code": "FAILED_AUTH_NEW_DEVICE",
                    "message": "Failed authentication attempts were followed by activity from a new device.",
                    "contribution": value,
                }
            )
        if (
            features["is_ussd"]
            and features["interaction_speed_deviation"] >= 0.50
            and features["velocity_5m"] >= 0.40
        ):
            value = 0.06
            compound_total += value
            compound_reasons.append(
                {
                    "code": "USSD_RHYTHM_BURST",
                    "message": "USSD navigation rhythm and transaction velocity changed together.",
                    "contribution": value,
                }
            )

        identity_changes = features["imsi_change"] + features["iccid_change"]
        if (
            features["recent_sim_activation"] >= 0.70
            and identity_changes >= 1.0
            and features["new_sim"]
            and not features["verified_sim_change"]
        ):
            value = 0.14
            compound_total += value
            compound_reasons.append(
                {
                    "code": "TELCO_SIM_SWAP_SIGNATURE",
                    "message": "Attested telco evidence shows a recent identity-changing SIM replacement.",
                    "contribution": value,
                }
            )
        if (
            features["otp_sim_change_proximity"] >= 0.75
            and features["otp_sim_geo_mismatch"] >= 0.60
            and features["new_sim"]
            and not features["verified_sim_change"]
        ):
            value = 0.12
            compound_total += value
            compound_reasons.append(
                {
                    "code": "OTP_SIM_GEO_CONFLICT",
                    "message": "An OTP followed the SIM change from a distant location.",
                    "contribution": value,
                }
            )

        if (
            features["recipient_sender_diversity_24h"] >= 0.50
            and features["recipient_first_time_sender_ratio_24h"] >= 0.60
            and features["recipient_rapid_cashout_ratio_1h"] >= 0.45
        ):
            value = 0.14
            compound_total += value
            compound_reasons.append(
                {
                    "code": "MULE_COLLECTION_SIGNATURE",
                    "message": "The recipient combined many first-time senders with rapid fund movement.",
                    "contribution": value,
                }
            )
        if (
            features.get("agent_evidence_coverage", 0.0) > 0
            and features.get("agent_customer_diversity_1h", 0.0) >= 0.40
            and features.get("agent_recipient_concentration_24h", 0.0) >= 0.60
            and max(
                features.get("recipient_rapid_cashout_ratio_1h", 0.0),
                features.get("agent_failed_auth_ratio_1h", 0.0),
                features.get("agent_location_mismatch", 0.0),
                features.get("agent_confirmed_fraud_score", 0.0),
            )
            >= 0.35
        ):
            value = 0.16
            compound_total += value
            compound_reasons.append(
                {
                    "code": "AGENT_TERMINAL_CAMPAIGN",
                    "message": "One attested agent terminal linked several customers to a concentrated suspicious pattern.",
                    "contribution": value,
                }
            )
        if features["account_hazard_score"] >= 0.30 and features["new_recipient"]:
            value = 0.10
            compound_total += value
            compound_reasons.append(
                {
                    "code": "ACCOUNT_RISK_WINDOW",
                    "message": "This payment occurred during a decaying precursor-risk window.",
                    "contribution": value,
                }
            )
        if (
            features["coercion_evidence_coverage"] > 0
            and features["call_transfer_overlap"]
            and features["new_recipient"]
            and max(
                features["screen_sharing_signal"],
                features["confirmation_friction"],
                features["coercion_on_device_score"],
            ) >= 0.60
        ):
            value = 0.14
            compound_total += value
            compound_reasons.append(
                {
                    "code": "COERCION_SESSION_SIGNATURE",
                    "message": "Attested session signals suggest the customer may be acting under direction.",
                    "contribution": value,
                }
            )

        total = sum(contributions.values()) + compound_total
        score = clamp(total / 0.72)

        reasons = [
            {
                "code": feature.upper(),
                "message": REASON_MESSAGES[feature],
                "contribution": round(value, 6),
            }
            for feature, value in contributions.items()
            if value >= 0.015 and features.get(feature, 0.0) > 0
        ]
        reasons.extend(compound_reasons)
        reasons.sort(key=lambda item: item["contribution"], reverse=True)
        return AnomalyResult(score=round(score, 6), reasons=reasons[:8])


class FastCalibratedForest:
    """Single-row inference for a binary sigmoid-calibrated random-forest ensemble.

    `CalibratedClassifierCV.predict_proba` re-validates the input inside every one of the
    480 trees (3 calibration folds x 160 trees); for a one-row live request that Python
    overhead is ~50x the actual tree traversal. This class walks the same fitted trees through
    their Cython `tree_.predict` and reproduces sklearn's averaging and sigmoid calibration
    exactly. `ModelBundle` only enables it after verifying agreement with the sklearn path on
    the loaded artifact, so a mismatch falls back to sklearn rather than changing scores.
    """

    def __init__(self, calibrated_model: Any):
        members: list[tuple[list[Any], int, float, float]] = []
        for calibrated in getattr(calibrated_model, "calibrated_classifiers_", []):
            if getattr(calibrated, "method", None) != "sigmoid" or len(calibrated.calibrators) != 1:
                raise ValueError("fast path supports binary sigmoid calibration only")
            forest = calibrated.estimator
            classes = list(forest.classes_)
            if len(classes) != 2:
                raise ValueError("fast path supports binary classification only")
            calibrator = calibrated.calibrators[0]
            members.append(
                (
                    [tree.tree_ for tree in forest.estimators_],
                    classes.index(max(classes)),
                    float(calibrator.a_),
                    float(calibrator.b_),
                )
            )
        if not members:
            raise ValueError("no calibrated classifiers in artifact")
        self.members = members
        self.n_features = int(calibrated_model.n_features_in_)

    def predict_positive(self, row: Any) -> float:
        x = np.ascontiguousarray(row, dtype=np.float32).reshape(1, self.n_features)
        total = 0.0
        for trees, positive_index, a, b in self.members:
            positive = 0.0
            for tree in trees:
                leaf = np.asarray(tree.predict(x))[0]
                if leaf.ndim == 2:  # (n_outputs, n_classes) on older tree layouts
                    leaf = leaf[0]
                normaliser = float(leaf.sum())
                positive += float(leaf[positive_index]) / normaliser if normaliser > 0 else 0.0
            positive /= len(trees)
            # _SigmoidCalibration.predict: expit(-(a * T + b))
            total += 1.0 / (1.0 + math.exp(a * positive + b))
        return total / len(self.members)


class ModelBundle:
    """Loads a local, versioned model artifact and enforces its feature schema."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.model: Any | None = None
        self.feature_names = MODEL_FEATURE_NAMES.copy()
        self.version = "rules-only-1.0"
        self.metrics: dict[str, Any] = {}
        self.artifact_hash: str | None = None
        self.training_data_hash: str | None = None
        self.feature_schema_hash: str | None = None
        self.load_error: str | None = None
        self.inference_path = "none"
        self._fast: FastCalibratedForest | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self.load_error = "model artifact not found; transparent rules-only mode is active"
            return
        try:
            artifact = joblib.load(self.path)
            if not isinstance(artifact, dict) or "model" not in artifact:
                raise ValueError("model artifact must be a dictionary containing 'model'")
            artifact_features = list(artifact.get("feature_names", []))
            if artifact_features != MODEL_FEATURE_NAMES:
                raise ValueError("model feature schema does not match runtime feature schema")
            self.model = artifact["model"]
            self.feature_names = artifact_features
            self.version = str(artifact.get("version", "unversioned-model"))
            self.metrics = dict(artifact.get("metrics", {}))
            self.training_data_hash = artifact.get("training_data_sha256")
            self.feature_schema_hash = artifact.get("feature_schema_sha256")
            self.artifact_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()
            self._fast = self._verified_fast_path(self.model, self.feature_names)
            self.inference_path = "fast_tree" if self._fast is not None else "sklearn"
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            ImportError,
            EOFError,
            pickle.UnpicklingError,
        ) as exc:  # fail closed to interpretable rules rather than crash scoring
            self.model = None
            self.load_error = f"model unavailable: {exc}"
            self.version = "rules-only-1.0"

    @staticmethod
    def _verified_fast_path(model: Any, feature_names: list[str]) -> FastCalibratedForest | None:
        """Build the fast predictor only if it reproduces sklearn on a probe set."""

        try:
            fast = FastCalibratedForest(model)
        except (AttributeError, ValueError, TypeError, IndexError):
            return None
        rng = np.random.default_rng(2026)
        probes = np.vstack(
            [
                np.zeros((1, len(feature_names))),
                np.ones((1, len(feature_names))),
                rng.uniform(0.0, 1.0, size=(62, len(feature_names))),
            ]
        )
        frame = pd.DataFrame(probes, columns=feature_names)
        try:
            reference = model.predict_proba(frame)[:, 1]
            candidate = np.asarray([fast.predict_positive(row) for row in probes])
        except (AttributeError, ValueError, TypeError, IndexError):
            return None
        if candidate.shape != reference.shape or not np.all(np.isfinite(candidate)):
            return None
        return fast if float(np.max(np.abs(candidate - reference))) < 1e-6 else None

    @property
    def available(self) -> bool:
        return self.model is not None

    def predict(self, features: dict[str, float]) -> float | None:
        if self.model is None:
            return None
        row = [features[name] for name in self.feature_names]
        if self._fast is not None:
            return round(clamp(self._fast.predict_positive(row)), 6)
        frame = pd.DataFrame([row], columns=self.feature_names)
        probability = float(self.model.predict_proba(frame)[0][1])
        return round(clamp(probability), 6)


# ---------------------------------------------------------------------------
# Score fusion
#
# Every constant below is a policy choice, not a learned parameter. They are named
# here, in one place, so that field calibration edits configuration rather than logic
# and so the evaluation can attribute each alert to the component that produced it.
# ---------------------------------------------------------------------------

#: Profiles below this confidence are "immature"; the transparent scorer already
#: discounts profile-dependent novelty for them, so the population model gets more weight.
IMMATURE_PROFILE_CONFIDENCE = 0.30
MODEL_WEIGHT_IMMATURE_PROFILE = 0.68
MODEL_WEIGHT_MATURE_PROFILE = 0.58

#: Notes attached when the decision is made with less evidence than usual.
COLD_START_CONFIDENCE = 0.20
SPARSE_EVIDENCE_COVERAGE = 0.45


@dataclass(frozen=True)
class SecurityFloorRule:
    """A named minimum-risk rule applied after blending.

    Floors encode attack signatures that must never be averaged away by a benign-looking
    model score (for example an unverified SIM swap followed by a drain). Each rule returns
    the floor it asserts, or 0.0 when it does not apply, so the fired rules are auditable.
    """

    code: str
    description: str
    evaluate: Callable[[dict[str, float]], float]


def _floor_device_sim_cochange(f: dict[str, float]) -> float:
    if (
        f["new_device"]
        and f["new_sim"]
        and not f["verified_sim_change"]
        and f["history_confidence"] >= 0.25
    ):
        return 0.70 + 0.15 * f["balance_drain_ratio"]
    return 0.0


def _floor_recovery_then_new_recipient(f: dict[str, float]) -> float:
    return 0.78 if f["recovery_signal_72h"] and f["new_recipient"] else 0.0


def _floor_failed_auth_new_device(f: dict[str, float]) -> float:
    return 0.82 if f["failed_auth_24h"] >= 0.60 and f["new_device"] else 0.0


def _floor_impossible_travel_new_device(f: dict[str, float]) -> float:
    return 0.76 if f["impossible_travel"] >= 0.70 and f["new_device"] else 0.0


def _floor_attested_sim_identity_change(f: dict[str, float]) -> float:
    identity_changes = f["imsi_change"] + f["iccid_change"]
    if (
        f["new_sim"]
        and f["recent_sim_activation"] >= 0.70
        and identity_changes >= 1.0
        and not f["verified_sim_change"]
    ):
        return 0.80
    return 0.0


def _floor_otp_after_sim_change(f: dict[str, float]) -> float:
    if (
        f["new_sim"]
        and f["otp_sim_change_proximity"] >= 0.75
        and f["otp_sim_geo_mismatch"] >= 0.60
        and not f["verified_sim_change"]
    ):
        return 0.84
    return 0.0


def _floor_mule_fan_in_cashout(f: dict[str, float]) -> float:
    if (
        f["recipient_sender_diversity_24h"] >= 0.50
        and f["recipient_first_time_sender_ratio_24h"] >= 0.60
        and f["recipient_rapid_cashout_ratio_1h"] >= 0.45
    ):
        return 0.76
    return 0.0


def _floor_agent_single_report(f: dict[str, float]) -> float:
    # A single independent report raises monitoring only; it does not quarantine.
    return 0.42 if f.get("agent_confirmed_fraud_score", 0.0) > 0 else 0.0


def _floor_agent_multi_victim(f: dict[str, float]) -> float:
    return 0.76 if f.get("agent_confirmed_accounts", 0.0) * 3.0 >= 2.0 else 0.0


def _floor_agent_campaign_pattern(f: dict[str, float]) -> float:
    if (
        f.get("agent_evidence_coverage", 0.0) > 0
        and f.get("agent_customer_diversity_1h", 0.0) >= 0.40
        and f.get("agent_recipient_concentration_24h", 0.0) >= 0.60
        and max(
            f.get("recipient_rapid_cashout_ratio_1h", 0.0),
            f.get("agent_failed_auth_ratio_1h", 0.0),
            f.get("agent_location_mismatch", 0.0),
            f.get("agent_confirmed_fraud_score", 0.0),
        )
        >= 0.35
    ):
        return 0.74
    return 0.0


def _floor_risk_window_new_recipient(f: dict[str, float]) -> float:
    return 0.66 if f["account_hazard_score"] >= 0.35 and f["new_recipient"] else 0.0


def _floor_cross_channel_sequence(f: dict[str, float]) -> float:
    if (
        f.get("new_channel_enrollment_24h", 0.0) >= 1.0
        and f.get("channel_transition_novelty", 0.0) >= 0.70
        and max(
            f.get("app_to_ussd_handoff", 0.0),
            f.get("cross_channel_device_mismatch", 0.0),
        )
        > 0
    ):
        return 0.72
    return 0.0


def _floor_recipient_single_report(f: dict[str, float]) -> float:
    # One report is a reversible monitoring signal, never an automatic block.
    return 0.42 if f.get("recipient_confirmed_fraud_score", 0.0) > 0 else 0.0


def _floor_recipient_multi_account(f: dict[str, float]) -> float:
    return 0.76 if f.get("recipient_confirmed_accounts", 0.0) * 3.0 >= 2.0 else 0.0


def _floor_coercion_during_call(f: dict[str, float]) -> float:
    if (
        f["coercion_evidence_coverage"] > 0
        and f["call_transfer_overlap"]
        and f["new_recipient"]
        and max(
            f["screen_sharing_signal"],
            f["confirmation_friction"],
            f["coercion_on_device_score"],
        )
        >= 0.60
    ):
        return 0.70
    return 0.0


SECURITY_FLOOR_RULES: tuple[SecurityFloorRule, ...] = (
    SecurityFloorRule(
        "DEVICE_SIM_COCHANGE",
        "Unverified new device and new SIM together on a mature profile.",
        _floor_device_sim_cochange,
    ),
    SecurityFloorRule(
        "RECOVERY_THEN_NEW_RECIPIENT",
        "Account recovery in the last 72 hours followed by a first-time recipient.",
        _floor_recovery_then_new_recipient,
    ),
    SecurityFloorRule(
        "FAILED_AUTH_NEW_DEVICE",
        "Burst of failed authentication followed by a new device.",
        _floor_failed_auth_new_device,
    ),
    SecurityFloorRule(
        "IMPOSSIBLE_TRAVEL_NEW_DEVICE",
        "Implausible location change combined with a new device.",
        _floor_impossible_travel_new_device,
    ),
    SecurityFloorRule(
        "ATTESTED_SIM_IDENTITY_CHANGE",
        "Telco-attested IMSI/ICCID change on a freshly activated, unverified SIM.",
        _floor_attested_sim_identity_change,
    ),
    SecurityFloorRule(
        "OTP_AFTER_SIM_CHANGE",
        "OTP requested shortly after an unverified SIM change from a distant location.",
        _floor_otp_after_sim_change,
    ),
    SecurityFloorRule(
        "MULE_FAN_IN_CASHOUT",
        "Recipient receiving from many first-time senders and cashing out rapidly.",
        _floor_mule_fan_in_cashout,
    ),
    SecurityFloorRule(
        "AGENT_SINGLE_REPORT",
        "One confirmed fraud report against the agent terminal (monitoring only).",
        _floor_agent_single_report,
    ),
    SecurityFloorRule(
        "AGENT_MULTI_VICTIM",
        "Confirmed fraud reports from two or more distinct customers at the terminal.",
        _floor_agent_multi_victim,
    ),
    SecurityFloorRule(
        "AGENT_CAMPAIGN_PATTERN",
        "Attested terminal serving many customers into a concentrated recipient set with a risk signal.",
        _floor_agent_campaign_pattern,
    ),
    SecurityFloorRule(
        "RISK_WINDOW_NEW_RECIPIENT",
        "Active precursor risk window combined with a first-time recipient.",
        _floor_risk_window_new_recipient,
    ),
    SecurityFloorRule(
        "CROSS_CHANNEL_SEQUENCE",
        "New-channel enrolment followed by a mismatched cross-channel transfer.",
        _floor_cross_channel_sequence,
    ),
    SecurityFloorRule(
        "RECIPIENT_SINGLE_REPORT",
        "One confirmed fraud report against the recipient (monitoring only).",
        _floor_recipient_single_report,
    ),
    SecurityFloorRule(
        "RECIPIENT_MULTI_ACCOUNT",
        "Confirmed fraud reports from two or more distinct accounts against the recipient.",
        _floor_recipient_multi_account,
    ),
    SecurityFloorRule(
        "COERCION_DURING_CALL",
        "Transfer to a new recipient prepared during a call with coercion indicators.",
        _floor_coercion_during_call,
    ),
)


def security_floors(features: dict[str, float]) -> list[dict[str, Any]]:
    """Return every floor rule that applies, with its asserted minimum score."""

    fired: list[dict[str, Any]] = []
    for rule in SECURITY_FLOOR_RULES:
        value = rule.evaluate(features)
        if value > 0.0:
            fired.append(
                {"code": rule.code, "value": round(float(value), 6), "description": rule.description}
            )
    return fired


@dataclass(frozen=True)
class FusionBreakdown:
    """Everything needed to explain a fused score and attribute it to a component."""

    model_score: float | None
    anomaly_score: float
    model_weight: float | None
    blended_score: float
    security_floor: float
    security_floor_codes: list[str] = field(default_factory=list)
    fused_score: float = 0.0
    note: str | None = None
    #: "security_floor" when a floor lifted the score above the blend, else "blend".
    driver: str = "blend"

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_score": self.model_score,
            "anomaly_score": self.anomaly_score,
            "model_weight": self.model_weight,
            "blended_score": self.blended_score,
            "security_floor": self.security_floor,
            "security_floor_codes": list(self.security_floor_codes),
            "fused_score": self.fused_score,
            "driver": self.driver,
        }


def fuse_scores_detailed(
    model_score: float | None,
    anomaly_score: float,
    features: dict[str, float],
) -> FusionBreakdown:
    confidence = features["history_confidence"]
    if model_score is None:
        model_weight: float | None = None
        blended = float(anomaly_score)
        note: str | None = (
            "Population model unavailable; decision uses the transparent behavioural scorer."
        )
    else:
        model_weight = (
            MODEL_WEIGHT_IMMATURE_PROFILE
            if confidence < IMMATURE_PROFILE_CONFIDENCE
            else MODEL_WEIGHT_MATURE_PROFILE
        )
        blended = model_weight * model_score + (1.0 - model_weight) * anomaly_score
        note = None

    fired = security_floors(features)
    security_floor = max((item["value"] for item in fired), default=0.0)
    fused = max(blended, security_floor)

    if confidence < COLD_START_CONFIDENCE:
        cold_start = "Behavioural profile is immature; novelty findings carry reduced weight."
        note = f"{note} {cold_start}".strip() if note else cold_start
    if features["evidence_coverage"] < SPARSE_EVIDENCE_COVERAGE:
        sparse = "Only core transaction signals were available; the response remains reversible."
        note = f"{note} {sparse}".strip() if note else sparse
    return FusionBreakdown(
        model_score=model_score,
        anomaly_score=float(anomaly_score),
        model_weight=model_weight,
        blended_score=round(clamp(blended), 6),
        security_floor=round(clamp(security_floor), 6),
        security_floor_codes=[item["code"] for item in fired],
        fused_score=round(clamp(fused), 6),
        note=note,
        driver="security_floor" if security_floor > blended else "blend",
    )


def fuse_scores(
    model_score: float | None,
    anomaly_score: float,
    features: dict[str, float],
) -> tuple[float, str | None]:
    """Backward-compatible wrapper returning only the fused score and uncertainty note."""

    breakdown = fuse_scores_detailed(model_score, anomaly_score, features)
    return breakdown.fused_score, breakdown.note


def build_decision_confidence(
    features: dict[str, float],
    model_score: float | None,
    anomaly_score: float,
) -> dict[str, Any]:
    """Quantify how much evidence supports the score, independently of fraud risk."""

    profile_maturity = clamp(features.get("history_confidence", 0.0))
    evidence = clamp(features.get("evidence_coverage", 0.0))
    recipient_present = bool(
        features.get("new_recipient", 0.0) or features.get("recipient_rarity", 0.0)
    )
    recipient_coverage = max(
        features.get("recipient_network_coverage", 0.0),
        features.get("recipient_watchlist_coverage", 0.0),
    )
    agent_coverage = features.get("agent_evidence_coverage", 0.0)
    if recipient_present:
        data_coverage = clamp(0.75 * evidence + 0.25 * recipient_coverage)
    else:
        data_coverage = evidence
    if agent_coverage > 0:
        data_coverage = clamp(0.75 * data_coverage + 0.25 * agent_coverage)
    scorer_agreement = 0.55 if model_score is None else clamp(1.0 - abs(model_score - anomaly_score))
    score = clamp(0.40 * profile_maturity + 0.35 * data_coverage + 0.25 * scorer_agreement)
    reasons: list[str] = []
    if profile_maturity < 0.35:
        reasons.append("The behavioural baseline is still immature.")
    if data_coverage < 0.50:
        reasons.append("Only part of the expected channel evidence was available.")
    if recipient_present and recipient_coverage == 0:
        reasons.append("No prior recipient-network or watchlist evidence was available.")
    if features.get("is_agent", 0.0) and agent_coverage == 0:
        reasons.append("No attested agent-terminal evidence was available.")
    if model_score is None:
        reasons.append("The population model was unavailable, so scorer agreement is unknown.")
    elif scorer_agreement < 0.65:
        reasons.append("The population model and transparent scorer disagree.")
    if not reasons:
        reasons.append("The profile, evidence coverage and independent scorers are consistent.")
    level = "high" if score >= 0.75 else "medium" if score >= 0.45 else "low"
    return {
        "score": round(score, 6),
        "level": level,
        "profile_maturity": round(profile_maturity, 6),
        "data_coverage": round(data_coverage, 6),
        "scorer_agreement": round(scorer_agreement, 6),
        "reasons": reasons,
    }


def build_customer_explanation(
    action: ResponseAction,
    reasons: list[dict[str, Any]],
    features: dict[str, float],
) -> str:
    """Return one non-technical sentence suitable for a customer notification."""

    if action == ResponseAction.ALLOW and features["verified_sim_change"]:
        return (
            "We approved this transaction because the SIM change was verified and the remaining "
            "activity matched the account's usual pattern."
        )
    if action == ResponseAction.ALLOW:
        return "We approved this transaction because it matched the account's usual activity."

    phrases: list[str] = []
    for reason in reasons:
        phrase = CUSTOMER_REASON_PHRASES.get(str(reason["code"]))
        if phrase and phrase not in phrases:
            phrases.append(phrase)
        if len(phrases) == 3:
            break
    detail = ", ".join(phrases[:-1]) + (f" and {phrases[-1]}" if len(phrases) > 1 else (phrases[0] if phrases else "the activity differed from the account's usual pattern"))
    if len(phrases) == 1:
        detail = phrases[0]

    prefixes = {
        ResponseAction.ALLOW_MONITOR: "We approved this transaction but are monitoring it because",
        ResponseAction.STEP_UP: "We need an extra confirmation because",
        ResponseAction.DELAY: "We temporarily delayed this transaction because",
        ResponseAction.HOLD: "We temporarily paused this transaction because",
        ResponseAction.SAFE_PAUSE: "We privately paused this transaction because",
    }
    recourse = {
        ResponseAction.ALLOW_MONITOR: "You can review it in transaction history or contact the bank through its official channel",
        ResponseAction.STEP_UP: "Confirm from a previously registered device or request an official bank callback",
        ResponseAction.DELAY: "Confirm from a previously registered device or wait for the short safety delay to expire",
        ResponseAction.HOLD: "Contact the bank through its official channel or wait for analyst review",
        ResponseAction.SAFE_PAUSE: "End any call or screen-sharing session and confirm privately through the bank's official channel",
    }
    return f"{prefixes[action]} {detail}; {recourse[action]}."


def build_recourse_options(action: ResponseAction, hold_seconds: int) -> list[dict[str, str]]:
    """Offer safe clearance routes without disclosing thresholds or attacker-gameable features."""

    if action == ResponseAction.ALLOW:
        return []
    options = [
        {
            "action": "review_activity",
            "description": "Review the recipient and amount in transaction history.",
            "estimated_clearance": "No interruption",
            "safe_channel": "bank app or statement",
        }
    ]
    if action in {
        ResponseAction.STEP_UP,
        ResponseAction.DELAY,
        ResponseAction.HOLD,
        ResponseAction.SAFE_PAUSE,
    }:
        options.extend(
            [
                {
                    "action": "trusted_device_confirmation",
                    "description": "Confirm from a previously registered device after ending any call or screen share.",
                    "estimated_clearance": "Immediate after successful confirmation",
                    "safe_channel": "registered device",
                },
                {
                    "action": "official_bank_callback",
                    "description": "Request a callback using the number in the bank's app, website or card.",
                    "estimated_clearance": "After identity verification",
                    "safe_channel": "bank-initiated callback",
                },
            ]
        )
    if hold_seconds:
        options.append(
            {
                "action": "automatic_review_or_expiry",
                "description": "Take no action while the reversible safety period completes.",
                "estimated_clearance": f"Within {max(1, hold_seconds // 60)} minutes",
                "safe_channel": "automatic",
            }
        )
    return options


def build_evidence_summary(
    event: BehaviorEventIn,
    features: dict[str, float],
) -> dict[str, Any]:
    """Describe the graceful-degradation path used for this channel."""

    signals = {
        "balance context": event.available_balance_before is not None,
        "recipient history": event.recipient_id is not None,
        "device identity": event.device_id is not None,
        "SIM identity": event.sim_id is not None,
        "network prefix": event.ip_prefix is not None,
        "coarse location": event.latitude is not None,
        "interaction rhythm": event.interaction_ms is not None and event.menu_depth is not None,
        "typing cadence": event.keystroke_interval_ms is not None,
        "typed-or-pasted signal": event.input_method != InputMethod.UNKNOWN,
        "device handling": event.device_tilt_variance is not None,
        "navigation path": event.navigation_signature is not None,
        "attested telco SIM lifecycle": bool(
            event.telco_assurance and event.telco_assurance.gateway_attested
        ),
        "recipient network history": features["recipient_network_coverage"] > 0,
        "consented coercion-safety telemetry": features["coercion_evidence_coverage"] > 0,
        "attested agent-terminal integrity": features.get("agent_evidence_coverage", 0.0) > 0,
    }
    if event.channel == Channel.APP:
        expected = list(signals)
        mode = "app_rich_behaviour" if features["evidence_coverage"] >= 0.60 else "core_banking_fallback"
    elif event.channel == Channel.USSD:
        expected = [
            "balance context",
            "recipient history",
            "SIM identity",
            "network prefix",
            "coarse location",
            "interaction rhythm",
            "navigation path",
            "attested telco SIM lifecycle",
            "recipient network history",
        ]
        mode = (
            "ussd_telco_assured"
            if signals["attested telco SIM lifecycle"]
            else "ussd_gateway_behaviour"
            if signals["interaction rhythm"] or signals["navigation path"]
            else "core_banking_fallback"
        )
    elif event.channel == Channel.AGENT:
        expected = [
            "balance context",
            "recipient history",
            "device identity",
            "network prefix",
            "coarse location",
            "navigation path",
            "attested telco SIM lifecycle",
            "recipient network history",
            "attested agent-terminal integrity",
        ]
        mode = (
            "agent_terminal_integrity"
            if signals["attested agent-terminal integrity"]
            else "agent_network_behaviour"
        )
    else:
        expected = [
            "balance context",
            "recipient history",
            "device identity",
            "network prefix",
            "coarse location",
            "interaction rhythm",
            "attested telco SIM lifecycle",
            "recipient network history",
        ]
        mode = "web_session_behaviour"
    return {
        "mode": mode,
        "coverage": round(features["evidence_coverage"], 6),
        "available_signals": [name for name in expected if signals[name]],
        "missing_optional_signals": [name for name in expected if not signals[name]],
    }
