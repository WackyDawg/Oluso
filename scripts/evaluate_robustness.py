from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score

from aegistwin.evaluation import leakage_audit
from aegistwin.features import FEATURE_NAMES, MODEL_EXCLUDED_FEATURES, MODEL_FEATURE_NAMES
from aegistwin.scoring import AnomalyScorer, fuse_scores


def operating_point(labels: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, Any]:
    predictions = scores >= threshold
    negatives = int((labels == 0).sum())
    true_positives = int((predictions & (labels == 1)).sum())
    false_positives = int((predictions & (labels == 0)).sum())
    positives = int((labels == 1).sum())
    return {
        "threshold": threshold,
        "recall": round(float(recall_score(labels, predictions, zero_division=0)), 6),
        "precision": round(float(precision_score(labels, predictions, zero_division=0)), 6),
        "false_positive_rate": round(false_positives / max(1, negatives), 6),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": positives - true_positives,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit synthetic separability and account-disjoint generalisation"
    )
    parser.add_argument("--input", type=Path, default=Path("data/training_features.csv"))
    parser.add_argument("--model", type=Path, default=Path("models/ato_model.joblib"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/robustness.json"))
    args = parser.parse_args()

    frame = pd.read_csv(args.input).sort_values("event_time").reset_index(drop=True)
    chronological_test = frame.iloc[int(len(frame) * 0.82) :].copy()
    chronological_labels = chronological_test["is_takeover"].to_numpy()
    artifact = joblib.load(args.model)
    chronological_probabilities = artifact["model"].predict_proba(
        chronological_test[MODEL_FEATURE_NAMES]
    )[:, 1]

    univariate: list[dict[str, Any]] = []
    for feature in MODEL_FEATURE_NAMES:
        values = chronological_test[feature].fillna(0.0).to_numpy()
        if np.unique(values).size < 2:
            continue
        auc = float(roc_auc_score(chronological_labels, values))
        univariate.append(
            {
                "feature": feature,
                "auc": round(auc, 6),
                "separation_auc": round(max(auc, 1.0 - auc), 6),
            }
        )
    univariate.sort(key=lambda item: item["separation_auc"], reverse=True)

    account_numbers = frame["account_id"].str.rsplit("_", n=1).str[-1].astype(int)
    buckets = account_numbers % 10
    train = frame[buckets < 6]
    test = frame[buckets >= 8].copy()
    model = CalibratedClassifierCV(
        RandomForestClassifier(
            n_estimators=120,
            max_depth=12,
            min_samples_leaf=4,
            class_weight="balanced_subsample",
            random_state=2027,
            n_jobs=1,
        ),
        method="sigmoid",
        cv=3,
    )
    model.fit(train[MODEL_FEATURE_NAMES], train["is_takeover"])
    probabilities = model.predict_proba(test[MODEL_FEATURE_NAMES])[:, 1]
    scorer = AnomalyScorer()
    fused = np.asarray(
        [
            fuse_scores(
                float(probability),
                scorer.score({name: float(row[name]) for name in FEATURE_NAMES}).score,
                {name: float(row[name]) for name in FEATURE_NAMES},
            )[0]
            for (_, row), probability in zip(test.iterrows(), probabilities)
        ]
    )
    labels = test["is_takeover"].to_numpy()

    # Evidence-availability features must describe which telemetry arrived, not the label.
    coverage_features = [
        name
        for name in FEATURE_NAMES
        if name.endswith(("_coverage", "_confidence"))
        or name in {"shared_device_allowed", "is_ussd", "is_agent"}
    ]
    coverage_audit = leakage_audit(
        {name: frame[name].to_numpy() for name in coverage_features},
        frame["is_takeover"].to_numpy(),
    )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "purpose": "detect perfect synthetic separation and measure unseen-account behaviour",
        "excluded_population_model_features": sorted(MODEL_EXCLUDED_FEATURES),
        "coverage_leakage_audit": coverage_audit,
        "chronological_separability": {
            "model_only_roc_auc": round(
                float(roc_auc_score(chronological_labels, chronological_probabilities)), 6
            ),
            "perfect_model_ranking": bool(
                chronological_probabilities[chronological_labels == 1].min()
                > chronological_probabilities[chronological_labels == 0].max()
            ),
            "top_univariate_features": univariate[:10],
        },
        "account_disjoint": {
            "train_accounts": int(train["account_id"].nunique()),
            "test_accounts": int(test["account_id"].nunique()),
            "account_overlap": len(set(train["account_id"]) & set(test["account_id"])),
            "train_events": len(train),
            "test_events": len(test),
            "takeover_events": int(labels.sum()),
            "model_only_roc_auc": round(float(roc_auc_score(labels, probabilities)), 6),
            "model_only_pr_auc": round(float(average_precision_score(labels, probabilities)), 6),
            "fused_roc_auc": round(float(roc_auc_score(labels, fused)), 6),
            "fused_pr_auc": round(float(average_precision_score(labels, fused)), 6),
            "customer_confirmation": operating_point(labels, fused, 0.48),
        },
    }
    if report["chronological_separability"]["perfect_model_ranking"]:
        raise RuntimeError("synthetic corpus still produces perfect model ranking")
    if univariate[0]["separation_auc"] >= 0.98:
        raise RuntimeError("a single synthetic feature remains nearly label-deterministic")
    if not coverage_audit["passed"]:
        raise RuntimeError(
            "an evidence-coverage feature is acting as a label proxy "
            f"(separation AUC {coverage_audit['worst_separation_auc']:.3f})"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
