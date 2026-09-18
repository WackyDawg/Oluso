from __future__ import annotations

import hashlib
import hmac
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from .storage import canonical_json, iso_utc

ALLOWED_INDICATOR_TYPES = {"recipient", "agent_terminal", "campaign"}
EVIDENCE_WEIGHTS = {
    "confirmed_customer_report": 1.0,
    "verified_account_takeover": 1.0,
    "confirmed_mule_cashout": 1.0,
    "confirmed_terminal_compromise": 1.0,
    "analyst_high_confidence": 0.90,
}


def normalise_indicator(indicator_type: str, value: str) -> str:
    """Return a deterministic representation without retaining the source identifier."""

    kind = indicator_type.strip().lower()
    if kind not in ALLOWED_INDICATOR_TYPES:
        raise ValueError(f"unsupported fraud-sketch indicator type: {kind}")
    clean = value.strip().lower()
    if kind == "campaign":
        stages = sorted({item.strip() for item in clean.split("|") if item.strip()})
        clean = "|".join(stages)
    if len(clean) < 3:
        raise ValueError("fraud-sketch indicator value is too short")
    return clean


def epoch_id(at: datetime, epoch_days: int) -> str:
    reference = at.astimezone(UTC)
    epoch_seconds = max(1, epoch_days) * 86_400
    return f"e{int(reference.timestamp()) // epoch_seconds:08x}"


def candidate_epochs(at: datetime, epoch_days: int, retention_days: int) -> list[str]:
    periods = max(1, math.ceil(retention_days / max(1, epoch_days)))
    return [epoch_id(at - timedelta(days=index * epoch_days), epoch_days) for index in range(periods + 1)]


def indicator_token(
    indicator_type: str,
    value: str,
    secret: str,
    *,
    epoch: str,
) -> str:
    clean = normalise_indicator(indicator_type, value)
    material = f"olusomesh-v1|{epoch}|{indicator_type.strip().lower()}|{clean}"
    return hmac.new(secret.encode("utf-8"), material.encode("utf-8"), hashlib.sha256).hexdigest()


def institution_token(institution_id: str, secret: str) -> str:
    material = f"olusomesh-institution-v1|{institution_id.strip().lower()}"
    return hmac.new(secret.encode("utf-8"), material.encode("utf-8"), hashlib.sha256).hexdigest()


def report_material(payload: dict[str, Any]) -> dict[str, Any]:
    observed_at = payload["observed_at"]
    if isinstance(observed_at, datetime):
        observed_at = iso_utc(observed_at)
    return {
        "report_id": str(payload["report_id"]),
        "institution_id": str(payload["institution_id"]).strip().lower(),
        "indicator_type": str(payload["indicator_type"]).strip().lower(),
        "indicator_value": normalise_indicator(
            str(payload["indicator_type"]), str(payload["indicator_value"])
        ),
        "confidence": round(float(payload["confidence"]), 6),
        "evidence_class": str(payload["evidence_class"]),
        "observed_at": str(observed_at),
        "ttl_hours": int(payload["ttl_hours"]),
        "nonce": str(payload["nonce"]),
    }


def sign_report(payload: dict[str, Any], institution_secret: str) -> str:
    return hmac.new(
        institution_secret.encode("utf-8"),
        canonical_json(report_material(payload)).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_report(payload: dict[str, Any], institution_secret: str, signature: str) -> bool:
    return hmac.compare_digest(sign_report(payload, institution_secret), signature)


def revocation_material(payload: dict[str, Any]) -> dict[str, Any]:
    revoked_at = payload["revoked_at"]
    if isinstance(revoked_at, datetime):
        revoked_at = iso_utc(revoked_at)
    return {
        "report_id": str(payload["report_id"]),
        "institution_id": str(payload["institution_id"]).strip().lower(),
        "reason": str(payload["reason"]).strip(),
        "revoked_at": str(revoked_at),
        "nonce": str(payload["nonce"]),
    }


def sign_revocation(payload: dict[str, Any], institution_secret: str) -> str:
    return hmac.new(
        institution_secret.encode("utf-8"),
        canonical_json(revocation_material(payload)).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_revocation(payload: dict[str, Any], institution_secret: str, signature: str) -> bool:
    return hmac.compare_digest(sign_revocation(payload, institution_secret), signature)


def score_reports(reports: list[dict[str, Any]], at: datetime) -> dict[str, Any]:
    """Aggregate active reports with diversity, evidence-quality and time decay."""

    reference = at.astimezone(UTC)
    active = []
    for report in reports:
        if str(report.get("status")) != "active":
            continue
        if datetime.fromisoformat(str(report["expires_at"])).astimezone(UTC) <= reference:
            continue
        active.append(report)
    institutions = {str(item["institution_token"]) for item in active}
    if not active:
        return {
            "score": 0.0,
            "confidence": 0.0,
            "independent_institutions": 0,
            "active_reports": 0,
            "status": "clear",
            "expires_at": None,
        }

    weighted: list[float] = []
    for item in active:
        observed = datetime.fromisoformat(str(item["observed_at"])).astimezone(UTC)
        age_hours = max(0.0, (reference - observed).total_seconds() / 3600.0)
        lifetime_hours = max(
            1.0,
            (
                datetime.fromisoformat(str(item["expires_at"])).astimezone(UTC) - observed
            ).total_seconds()
            / 3600.0,
        )
        freshness = max(0.25, 1.0 - age_hours / lifetime_hours)
        evidence_weight = EVIDENCE_WEIGHTS.get(str(item["evidence_class"]), 0.0)
        weighted.append(float(item["confidence"]) * evidence_weight * freshness)

    confidence = sum(weighted) / max(1, len(weighted))
    count = len(institutions)
    if count == 1:
        score = 0.30 + 0.08 * confidence
        status = "observe_only"
    elif count == 2:
        score = 0.58 + 0.16 * confidence
        status = "shared_watch"
    else:
        score = 0.72 + min(0.10, 0.025 * (count - 3)) + 0.14 * confidence
        status = "high_confidence"
    expires = min(datetime.fromisoformat(str(item["expires_at"])) for item in active)
    return {
        "score": round(min(0.92, score), 6),
        "confidence": round(min(1.0, confidence), 6),
        "independent_institutions": count,
        "active_reports": len(active),
        "status": status,
        "expires_at": iso_utc(expires),
    }


def capsule_material(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in (
            "capsule_id",
            "indicator_type",
            "indicator_token",
            "epoch_id",
            "score",
            "confidence",
            "independent_institutions",
            "active_reports",
            "status",
            "issued_at",
            "expires_at",
        )
    }


def sign_capsule(payload: dict[str, Any], secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        canonical_json(capsule_material(payload)).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_capsule(payload: dict[str, Any], signature: str, secret: str, at: datetime) -> bool:
    try:
        expires = datetime.fromisoformat(str(payload["expires_at"])).astimezone(UTC)
    except (KeyError, ValueError):
        return False
    return at.astimezone(UTC) < expires and hmac.compare_digest(
        sign_capsule(payload, secret), signature
    )
