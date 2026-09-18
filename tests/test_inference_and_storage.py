from __future__ import annotations

import sqlite3
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier

from oluso.features import MODEL_FEATURE_NAMES
from oluso.scoring import FastCalibratedForest, ModelBundle
from oluso.storage import Database


def _tiny_calibrated_forest(seed: int = 7) -> CalibratedClassifierCV:
    rng = np.random.default_rng(seed)
    X = rng.uniform(0.0, 1.0, size=(400, len(MODEL_FEATURE_NAMES)))
    y = (X[:, 0] + X[:, 2] + rng.normal(0, 0.15, 400) > 1.0).astype(int)
    model = CalibratedClassifierCV(
        RandomForestClassifier(n_estimators=12, max_depth=5, random_state=seed, n_jobs=1),
        method="sigmoid",
        cv=3,
    )
    model.fit(pd.DataFrame(X, columns=MODEL_FEATURE_NAMES), y)
    return model


def test_fast_tree_path_reproduces_sklearn_exactly(tmp_path: Path) -> None:
    model = _tiny_calibrated_forest()
    artifact_path = tmp_path / "tiny.joblib"
    joblib.dump({"model": model, "feature_names": MODEL_FEATURE_NAMES, "version": "tiny"}, artifact_path)

    bundle = ModelBundle(artifact_path)
    assert bundle.available
    assert bundle.inference_path == "fast_tree"

    rng = np.random.default_rng(11)
    rows = rng.uniform(0.0, 1.0, size=(50, len(MODEL_FEATURE_NAMES)))
    reference = model.predict_proba(pd.DataFrame(rows, columns=MODEL_FEATURE_NAMES))[:, 1]
    fast = FastCalibratedForest(model)
    for row, expected in zip(rows, reference):
        assert abs(fast.predict_positive(row) - expected) < 1e-6
        features = dict(zip(MODEL_FEATURE_NAMES, map(float, row)))
        assert abs(bundle.predict(features) - round(float(expected), 6)) <= 1e-6


def test_fast_path_rejects_unsupported_models() -> None:
    class NotCalibrated:  # no calibrated_classifiers_
        pass

    try:
        FastCalibratedForest(NotCalibrated())
    except ValueError as exc:
        assert "no calibrated classifiers" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_database_pools_and_closes_connections(tmp_path: Path) -> None:
    database = Database(tmp_path / "pool.db")
    database.initialize()
    assert database._pool.qsize() == 1  # the schema migration connection is kept warm
    with database.connect() as connection:
        connection.execute("SELECT 1").fetchone()
    assert database._pool.qsize() == 1
    with database.connect() as first, database.connect() as second:
        assert first is not second  # nested blocks still get distinct connections
    assert database._pool.qsize() == 2

    with pytest.raises(sqlite3.OperationalError), database.connect() as connection:
        connection.execute("SELECT * FROM table_that_does_not_exist")
    assert database._pool.qsize() == 1  # the failed connection is discarded, not pooled

    database.close()
    assert database._pool.qsize() == 0
    with database.connect() as connection:  # still usable after close; just not pooled
        connection.execute("SELECT 1").fetchone()
    assert database._pool.qsize() == 0
