"""Reusable evaluation statistics: interval estimates, ablations and detection attribution.

These helpers exist so that the release evaluation reports uncertainty and explains *which*
component produced each detection, instead of publishing point estimates from small cohorts.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .scoring import FusionBreakdown, fuse_scores_detailed


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion; well-behaved at 0 and 1."""

    if trials <= 0:
        return (0.0, 0.0)
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    centre = (proportion + z * z / (2.0 * trials)) / denominator
    half_width = (
        z * math.sqrt(proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials))
    ) / denominator
    return (round(max(0.0, centre - half_width), 6), round(min(1.0, centre + half_width), 6))


def _operating_metrics(labels: np.ndarray, predictions: np.ndarray) -> dict[str, float]:
    positives = labels == 1
    negatives = ~positives
    true_positives = float((predictions & positives).sum())
    false_positives = float((predictions & negatives).sum())
    recall = true_positives / max(1.0, float(positives.sum()))
    fpr = false_positives / max(1.0, float(negatives.sum()))
    precision = true_positives / max(1.0, true_positives + false_positives)
    return {"recall": recall, "precision": precision, "false_positive_rate": fpr}


def _rank_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    """ROC-AUC by rank statistic; avoids an sklearn dependency inside the bootstrap loop."""

    positives = scores[labels == 1]
    negatives = scores[labels == 0]
    if positives.size == 0 or negatives.size == 0:
        return float("nan")
    order = np.argsort(np.concatenate([positives, negatives]), kind="mergesort")
    ranks = np.empty(order.size, dtype=float)
    ranks[order] = np.arange(1, order.size + 1)
    combined = np.concatenate([positives, negatives])
    # Average ranks for ties so the statistic matches the trapezoidal ROC area.
    _, inverse, counts = np.unique(combined, return_inverse=True, return_counts=True)
    if counts.max() > 1:
        sums = np.zeros(counts.size)
        np.add.at(sums, inverse, ranks)
        ranks = (sums / counts)[inverse]
    positive_rank_sum = ranks[: positives.size].sum()
    return float(
        (positive_rank_sum - positives.size * (positives.size + 1) / 2.0)
        / (positives.size * negatives.size)
    )


def bootstrap_operating_point(
    labels: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    *,
    resamples: int = 2000,
    seed: int = 2026,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Stratified percentile bootstrap of recall, precision, FPR and ROC-AUC at one threshold.

    Resampling is stratified by label so every replicate keeps the observed number of
    takeovers; with 40-ish positives an unstratified bootstrap would frequently draw none.
    """

    labels = np.asarray(labels).astype(int)
    scores = np.asarray(scores, dtype=float)
    predictions = scores >= threshold
    point = _operating_metrics(labels, predictions)
    point["roc_auc"] = _rank_auc(labels, scores)

    rng = np.random.default_rng(seed)
    positive_index = np.flatnonzero(labels == 1)
    negative_index = np.flatnonzero(labels == 0)
    draws: dict[str, list[float]] = {name: [] for name in point}
    for _ in range(resamples):
        sample = np.concatenate(
            [
                rng.choice(positive_index, positive_index.size, replace=True),
                rng.choice(negative_index, negative_index.size, replace=True),
            ]
        )
        sample_labels = labels[sample]
        sample_scores = scores[sample]
        metrics = _operating_metrics(sample_labels, sample_scores >= threshold)
        metrics["roc_auc"] = _rank_auc(sample_labels, sample_scores)
        for name, value in metrics.items():
            draws[name].append(value)

    lower_q = (1.0 - confidence) / 2.0
    upper_q = 1.0 - lower_q
    intervals: dict[str, Any] = {}
    for name, values in draws.items():
        array = np.asarray(values)
        intervals[name] = {
            "point": round(float(point[name]), 6),
            "ci_lower": round(float(np.nanquantile(array, lower_q)), 6),
            "ci_upper": round(float(np.nanquantile(array, upper_q)), 6),
        }
    positives = int((labels == 1).sum())
    negatives = int((labels == 0).sum())
    true_positives = int((predictions & (labels == 1)).sum())
    false_positives = int((predictions & (labels == 0)).sum())
    intervals["recall"]["wilson"] = wilson_interval(true_positives, positives)
    intervals["false_positive_rate"]["wilson"] = wilson_interval(false_positives, negatives)
    return {
        "threshold": threshold,
        "method": "stratified percentile bootstrap",
        "resamples": resamples,
        "confidence": confidence,
        "seed": seed,
        "metrics": intervals,
    }


def fusion_breakdowns(
    probabilities: np.ndarray,
    anomaly_scores: np.ndarray,
    feature_rows: list[dict[str, float]],
) -> list[FusionBreakdown]:
    return [
        fuse_scores_detailed(
            None if probability is None or (isinstance(probability, float) and math.isnan(probability)) else float(probability),
            float(anomaly),
            features,
        )
        for probability, anomaly, features in zip(probabilities, anomaly_scores, feature_rows)
    ]


def ablation_table(
    labels: np.ndarray,
    breakdowns: list[FusionBreakdown],
    threshold: float,
) -> dict[str, dict[str, Any]]:
    """Recall/FPR at one threshold for each scoring component in isolation and combined.

    The `floors_only` row answers the question "how much of the detection is rules?";
    the `blend_without_floors` row answers "what do the learned and heuristic scorers add?".
    """

    labels = np.asarray(labels).astype(int)
    variants: dict[str, np.ndarray] = {
        "model_only": np.asarray(
            [b.model_score if b.model_score is not None else 0.0 for b in breakdowns]
        ),
        "anomaly_only": np.asarray([b.anomaly_score for b in breakdowns]),
        "blend_without_floors": np.asarray([b.blended_score for b in breakdowns]),
        "floors_only": np.asarray([b.security_floor for b in breakdowns]),
        "fused_live": np.asarray([b.fused_score for b in breakdowns]),
    }
    output: dict[str, dict[str, Any]] = {}
    for name, scores in variants.items():
        predictions = scores >= threshold
        metrics = _operating_metrics(labels, predictions)
        output[name] = {
            "recall": round(metrics["recall"], 6),
            "precision": round(metrics["precision"], 6),
            "false_positive_rate": round(metrics["false_positive_rate"], 6),
            "true_positives": int((predictions & (labels == 1)).sum()),
            "false_positives": int((predictions & (labels == 0)).sum()),
            "roc_auc": round(_rank_auc(labels, scores), 6) if np.unique(scores).size > 1 else None,
        }
    return output


def detection_attribution(
    labels: np.ndarray,
    breakdowns: list[FusionBreakdown],
    threshold: float,
) -> dict[str, Any]:
    """Explain each alert at `threshold`: did the blend reach it alone, or did a floor lift it?

    Categories for true positives:
    - `blend_alone`: the model/anomaly blend already exceeded the threshold.
    - `floor_required`: the blend was below threshold and a security floor lifted it above.
    - `both`: blend and floor each independently exceeded the threshold.
    The same partition is reported for false positives so rule-driven false alarms are visible.
    """

    labels = np.asarray(labels).astype(int)
    summary: dict[str, dict[str, Any]] = {}
    floor_counts_tp: dict[str, int] = {}
    floor_counts_fp: dict[str, int] = {}
    for outcome in ("true_positives", "false_positives"):
        summary[outcome] = {"blend_alone": 0, "floor_required": 0, "both": 0, "total": 0}
    for label, breakdown in zip(labels, breakdowns):
        alerted = breakdown.fused_score >= threshold
        if not alerted:
            continue
        outcome = "true_positives" if label == 1 else "false_positives"
        blend_hit = breakdown.blended_score >= threshold
        floor_hit = breakdown.security_floor >= threshold
        if blend_hit and floor_hit:
            category = "both"
        elif blend_hit:
            category = "blend_alone"
        else:
            category = "floor_required"
        summary[outcome][category] += 1
        summary[outcome]["total"] += 1
        if floor_hit:
            counter = floor_counts_tp if label == 1 else floor_counts_fp
            for code in breakdown.security_floor_codes:
                counter[code] = counter.get(code, 0) + 1
    tp_total = max(1, summary["true_positives"]["total"])
    summary["true_positives"]["floor_required_share"] = round(
        summary["true_positives"]["floor_required"] / tp_total, 6
    )
    summary["true_positives"]["blend_alone_share"] = round(
        summary["true_positives"]["blend_alone"] / tp_total, 6
    )
    summary["floor_codes_among_true_positives"] = dict(
        sorted(floor_counts_tp.items(), key=lambda item: -item[1])
    )
    summary["floor_codes_among_false_positives"] = dict(
        sorted(floor_counts_fp.items(), key=lambda item: -item[1])
    )
    return summary


def leakage_audit(
    frame_columns: dict[str, np.ndarray],
    labels: np.ndarray,
    *,
    max_separation_auc: float = 0.75,
) -> dict[str, Any]:
    """Check that evidence-availability features are not proxies for the label.

    Coverage and confidence features describe *which telemetry was present*, not fraud.
    If any of them separates the classes strongly, the generator (or a real feed) is
    revealing labels through missingness, and the model would learn to detect the feed
    rather than the behaviour.
    """

    labels = np.asarray(labels).astype(int)
    rows: list[dict[str, Any]] = []
    worst = 0.0
    for name, values in frame_columns.items():
        values = np.nan_to_num(np.asarray(values, dtype=float))
        negatives = values[labels == 0]
        positives = values[labels == 1]
        if np.unique(values).size < 2:
            auc = 0.5
        else:
            auc = _rank_auc(labels, values)
        separation = max(auc, 1.0 - auc)
        worst = max(worst, separation)
        rows.append(
            {
                "feature": name,
                "mean_normal": round(float(negatives.mean()), 6) if negatives.size else None,
                "mean_takeover": round(float(positives.mean()), 6) if positives.size else None,
                "present_rate_normal": round(float((negatives > 0).mean()), 6) if negatives.size else None,
                "present_rate_takeover": round(float((positives > 0).mean()), 6) if positives.size else None,
                "separation_auc": round(float(separation), 6),
            }
        )
    rows.sort(key=lambda item: -item["separation_auc"])
    return {
        "max_allowed_separation_auc": max_separation_auc,
        "worst_separation_auc": round(float(worst), 6),
        "passed": bool(worst < max_separation_auc),
        "features": rows,
    }
