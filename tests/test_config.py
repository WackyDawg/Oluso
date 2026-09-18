from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from oluso.config import Settings

PROJECT = Path(__file__).resolve().parents[1]


def test_checked_in_env_example_is_parseable() -> None:
    settings = Settings(_env_file=PROJECT / ".env.example")

    assert settings.allowed_tenants == ["default", "demo-bank", "partner-bank"]
    assert settings.cors_origins == [
        "http://localhost:8501",
        "http://localhost:3000",
    ]
    assert set(settings.fraud_sketch_institution_keys) == {"bank-a", "bank-b", "bank-c"}


def test_csv_compatibility_values_are_parseable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATO_ALLOWED_TENANTS", "default,demo-bank,partner-bank")
    monkeypatch.setenv(
        "ATO_CORS_ORIGINS", "http://localhost:8501,http://localhost:3000"
    )

    settings = Settings(_env_file=None)

    assert settings.allowed_tenants == ["default", "demo-bank", "partner-bank"]
    assert settings.cors_origins == [
        "http://localhost:8501",
        "http://localhost:3000",
    ]


def test_empty_environment_list_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATO_ALLOWED_TENANTS", "[]")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
