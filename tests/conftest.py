from __future__ import annotations

from pathlib import Path

import pytest

from aegistwin.config import Settings


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_path=tmp_path / "aegistwin-test.db",
        model_path=tmp_path / "missing-model.joblib",
        api_key="test-api-key-12345",
        cors_origins=["http://testserver"],
        default_regret_limit=3,
        profile_lookback_days=180,
        max_history_events=2000,
    )

