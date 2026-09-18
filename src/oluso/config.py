from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def parse_string_list(value: object, *, field_name: str) -> list[str] | object:
    """Accept shell-friendly CSV or canonical JSON without settings-source pre-decoding."""

    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must contain at least one value")
    if text.startswith("["):
        decoded = json.loads(text)
        if not isinstance(decoded, list):
            raise ValueError(f"{field_name} JSON must be an array")
        items = decoded
    else:
        items = text.split(",")
    result = [str(item).strip() for item in items if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain at least one value")
    return result


class Settings(BaseSettings):
    """Runtime configuration loaded from ATO_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="ATO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    database_path: Path = Path("./data/oluso.db")
    model_path: Path = Path("./models/ato_model.joblib")
    api_key: str = Field(default="dev-only-change-me", min_length=12)
    analyst_api_key: str = Field(default="analyst-dev-only-change-me", min_length=12)
    auditor_api_key: str = Field(default="auditor-dev-only-change-me", min_length=12)
    admin_api_key: str = Field(default="admin-dev-only-change-me", min_length=12)
    recipient_hmac_key: str = Field(default="recipient-token-dev-only-change-me", min_length=16)
    fraud_sketch_token_key: str = Field(
        default="fraud-sketch-token-dev-only-change-me", min_length=16
    )
    fraud_sketch_capsule_key: str = Field(
        default="fraud-sketch-capsule-dev-only-change-me", min_length=16
    )
    fraud_sketch_institution_keys: dict[str, str] = Field(
        default_factory=lambda: {
            "bank-a": "bank-a-sketch-signing-dev-only-change-me",
            "bank-b": "bank-b-sketch-signing-dev-only-change-me",
            "bank-c": "bank-c-sketch-signing-dev-only-change-me",
        }
    )
    audit_anchor_key: str = Field(default="audit-anchor-dev-only-change-me", min_length=16)
    resilience_hmac_key: str = Field(default="resilience-heartbeat-dev-only-change-me", min_length=16)
    allowed_tenants: Annotated[list[str], NoDecode] = [
        "default",
        "demo-bank",
        "partner-bank",
    ]
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:8501",
        "http://localhost:3000",
    ]
    default_regret_limit: int = Field(default=3, ge=0, le=30)
    profile_lookback_days: int = Field(default=180, ge=7, le=730)
    max_history_events: int = Field(default=2000, ge=50, le=100_000)
    learning_quarantine_hours: int = Field(default=24, ge=1, le=168)
    campaign_window_hours: int = Field(default=24, ge=1, le=168)
    evidence_max_age_seconds: int = Field(default=300, ge=30, le=3600)
    fraud_sketch_max_age_seconds: int = Field(default=900, ge=60, le=86_400)
    fraud_sketch_epoch_days: int = Field(default=7, ge=1, le=30)
    fraud_sketch_retention_days: int = Field(default=30, ge=1, le=90)
    fraud_sketch_capsule_ttl_hours: int = Field(default=24, ge=1, le=168)
    fraud_sketch_reports_per_hour: int = Field(default=100, ge=1, le=10_000)
    heartbeat_max_age_seconds: int = Field(default=300, ge=30, le=3600)
    edge_capsule_ttl_hours: int = Field(default=8, ge=1, le=72)
    recovery_batch_size: int = Field(default=100, ge=1, le=1000)
    request_rate_per_minute: int = Field(default=600, ge=10, le=100_000)
    max_request_bytes: int = Field(default=262_144, ge=4096, le=5_000_000)
    policy_version: str = "policy-1.4.0"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        return parse_string_list(value, field_name="cors_origins")

    @field_validator("allowed_tenants", mode="before")
    @classmethod
    def parse_tenants(cls, value: object) -> object:
        return parse_string_list(value, field_name="allowed_tenants")

    @field_validator("fraud_sketch_institution_keys", mode="before")
    @classmethod
    def parse_institution_keys(cls, value: object) -> object:
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict) or not value:
            raise ValueError("at least one fraud-sketch institution key is required")
        result = {str(key).strip().lower(): str(secret) for key, secret in value.items()}
        if any(len(secret) < 16 for secret in result.values()):
            raise ValueError("fraud-sketch institution keys must be at least 16 characters")
        return result

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
