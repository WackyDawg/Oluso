from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

from oluso.features import FEATURE_NAMES, MODEL_FEATURE_NAMES
from oluso.scoring import AnomalyScorer, fuse_scores


def choose_threshold(y_true: np.ndarray, probabilities: np.ndarray, max_fpr: float = 0.01) -> float:
    false_positive_rates, true_positive_rates, thresholds = roc_curve(y_true, probabilities)
    eligible = [
        (tpr, threshold)
        for fpr, tpr, threshold in zip(false_positive_rates, true_positive_rates, thresholds)
        if fpr <= max_fpr and np.isfinite(threshold)
    ]
    if not eligible:
        return 0.70
    return float(max(eligible, key=lambda item: item[0])[1])


def calculate_metrics(y_true: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict[str, float]:
    predictions = (probabilities >= threshold).astype(int)
    negatives = max(1, int((y_true == 0).sum()))
    false_positives = int(((predictions == 1) & (y_true == 0)).sum())
    true_positives = int(((predictions == 1) & (y_true == 1)).sum())
    false_negatives = int(((predictions == 0) & (y_true == 1)).sum())
    return {
        "roc_auc": round(float(roc_auc_score(y_true, probabilities)), 6),
        "pr_auc": round(float(average_precision_score(y_true, probabilities)), 6),
        "brier_score": round(float(brier_score_loss(y_true, probabilities)), 6),
        "precision": round(float(precision_score(y_true, predictions, zero_division=0)), 6),
        "recall": round(float(recall_score(y_true, predictions, zero_division=0)), 6),
        "f1": round(float(f1_score(y_true, predictions, zero_division=0)), 6),
        "false_positive_rate": round(false_positives / negatives, 6),
        "false_positives": false_positives,
        "true_positives": true_positives,
        "false_negatives": false_negatives,
        "threshold": round(float(threshold), 6),
        "samples": len(y_true),
        "positive_samples": int(y_true.sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate the Oluso population model")
    parser.add_argument("--input", type=Path, default=Path("data/training_features.csv"))
    parser.add_argument("--output", type=Path, default=Path("models/ato_model.joblib"))
    parser.add_argument("--max-model-fpr", type=float, default=0.005)
    args = parser.parse_args()

    frame = pd.read_csv(args.input).sort_values("event_time").reset_index(drop=True)
    missing = sorted(set(FEATURE_NAMES + ["is_takeover"]) - set(frame.columns))
    if missing:
        raise ValueError(f"training data is missing columns: {missing}")

    split_train = int(len(frame) * 0.65)
    split_validation = int(len(frame) * 0.82)
    train = frame.iloc[:split_train]
    validation = frame.iloc[split_train:split_validation]
    test = frame.iloc[split_validation:]

    base_model = RandomForestClassifier(
        n_estimators=160,
        max_depth=12,
        min_samples_leaf=4,
        class_weight="balanced_subsample",
        random_state=2026,
        # Single-threaded inference avoids joblib worker startup on a one-row live request.
        # Training remains laptop-fast at this dataset size and runtime latency is steadier.
        n_jobs=1,
    )
    calibrated_model = CalibratedClassifierCV(base_model, method="sigmoid", cv=3)
    calibrated_model.fit(train[MODEL_FEATURE_NAMES], train["is_takeover"])

    validation_probabilities = calibrated_model.predict_proba(validation[MODEL_FEATURE_NAMES])[:, 1]
    threshold = choose_threshold(
        validation["is_takeover"].to_numpy(),
        validation_probabilities,
        max_fpr=args.max_model_fpr,
    )
    test_probabilities = calibrated_model.predict_proba(test[MODEL_FEATURE_NAMES])[:, 1]
    model_metrics = calculate_metrics(
        test["is_takeover"].to_numpy(), test_probabilities, threshold
    )

    anomaly_scorer = AnomalyScorer()
    fused_scores: list[float] = []
    for (_, row), model_probability in zip(test.iterrows(), test_probabilities):
        features = {name: float(row[name]) for name in FEATURE_NAMES}
        anomaly_score = anomaly_scorer.score(features).score
        fused_scores.append(fuse_scores(float(model_probability), anomaly_score, features)[0])
    fused = np.asarray(fused_scores)
    labels = test["is_takeover"].to_numpy()
    runtime_thresholds = {
        "monitor_or_more": 0.30,
        "customer_confirmation_or_more": 0.48,
        "delay_or_hold": 0.66,
        "hold_and_review": 0.84,
    }
    runtime_metrics = {
        name: calculate_metrics(labels, fused, policy_threshold)
        for name, policy_threshold in runtime_thresholds.items()
    }

    scenario_recall: dict[str, float] = {}
    challenge_predictions = fused >= runtime_thresholds["customer_confirmation_or_more"]
    for scenario, cohort in test[test["is_takeover"] == 1].groupby("scenario"):
        positions = test.index.get_indexer(cohort.index)
        scenario_recall[str(scenario)] = round(float(challenge_predictions[positions].mean()), 6)

    challenge = runtime_metrics["customer_confirmation_or_more"]
    prevalence_projections: dict[str, dict[str, float]] = {}
    for prevalence in (0.001, 0.005, 0.01):
        recall = float(challenge["recall"])
        fpr = float(challenge["false_positive_rate"])
        alerts = 10_000 * (recall * prevalence + fpr * (1.0 - prevalence))
        precision = (recall * prevalence) / max(
            recall * prevalence + fpr * (1.0 - prevalence), 1e-12
        )
        prevalence_projections[f"{prevalence:.3%}"] = {
            "projected_precision": round(precision, 6),
            "projected_alerts_per_10000": round(alerts, 2),
        }

    metrics = {
        "model_only": model_metrics,
        "runtime_policy": runtime_metrics,
        "challenge_recall_by_attack_family": scenario_recall,
        "prevalence_stress": prevalence_projections,
    }

    artifact = {
        "model": calibrated_model,
        "feature_names": MODEL_FEATURE_NAMES,
        "version": "rf-calibrated-longitudinal-ng-7.0",
        "trained_at": datetime.now(UTC).isoformat(),
        "training_data_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "feature_schema_sha256": hashlib.sha256(
            "|".join(MODEL_FEATURE_NAMES).encode("utf-8")
        ).hexdigest(),
        "decision_threshold": threshold,
        "metrics": metrics,
        "training_note": (
            "Development-only model trained on raw longitudinal Nigerian synthetic sessions. "
            "It must be revalidated on consented, representative production data."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, args.output)
    print(f"wrote={args.output}")
    print(f"model_only={model_metrics}")
    for name, result in runtime_metrics.items():
        print(f"runtime_{name}={result}")
    print(f"prevalence_stress={prevalence_projections}")


if __name__ == "__main__":
    main()
