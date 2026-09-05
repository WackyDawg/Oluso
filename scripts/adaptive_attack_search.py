from __future__ import annotations

import argparse
import itertools
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from aegistwin.features import FeatureEngine
from aegistwin.policy import PolicyEngine
from aegistwin.schemas import BehaviorEventIn, Channel, EventType
from aegistwin.scoring import AnomalyScorer, ModelBundle, fuse_scores


def normal_history(now: datetime) -> list[dict[str, Any]]:
    return [
        BehaviorEventIn(
            event_id=f"adaptive_history_{index:03d}",
            account_id="adaptive_customer",
            occurred_at=now - timedelta(days=36 - index),
            event_type=EventType.PURCHASE,
            channel=Channel.APP,
            amount=2_000 + (index % 4) * 150,
            available_balance_before=40_000,
            recipient_id="merchant_known",
            device_id="device_known",
            sim_id="sim_known",
            ip_prefix="102.88.10.0/24",
            latitude=6.5244,
            longitude=3.3792,
            interaction_ms=20_000,
            menu_depth=5,
            input_method="typed",
            keystroke_interval_ms=188,
            device_tilt_variance=2.3,
            navigation_signature="app_home_pay",
        ).model_dump(mode="json")
        | {"_profile_eligible": True}
        for index in range(36)
    ]


def evaluate(
    event: BehaviorEventIn,
    history: list[dict[str, Any]],
    model: ModelBundle,
    recipient_context: dict[str, float] | None = None,
) -> dict[str, Any]:
    features, _ = FeatureEngine().extract(
        event,
        history,
        {"account_id": event.account_id, "shared_device_allowed": False},
        recipient_context,
    )
    anomaly = AnomalyScorer().score(features)
    model_score = model.predict(features)
    fused, note = fuse_scores(model_score, anomaly.score, features)
    policy = PolicyEngine().decide(fused, features, regret_used=0, regret_limit=3)
    return {
        "score": fused,
        "action": policy.action.value,
        "model_score": model_score,
        "anomaly_score": anomaly.score,
        "reasons": [item["code"] for item in anomaly.reasons],
        "features": features,
        "uncertainty_note": note,
    }


def candidate_event(now: datetime, config: dict[str, Any], index: int) -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=f"adaptive_candidate_{index:05d}",
        account_id="adaptive_customer",
        occurred_at=now + timedelta(hours=config["hour_shift"]),
        event_type=EventType.TRANSFER,
        channel=Channel(config["channel"]),
        amount=config["amount"],
        available_balance_before=52_000,
        recipient_id="mule_hub_adaptive",
        device_id="device_known" if config["reuse_device"] else "device_attacker",
        sim_id="sim_known" if config["reuse_sim"] else "sim_attacker",
        ip_prefix="102.88.10.0/24" if config["reuse_ip"] else "197.210.44.0/24",
        latitude=6.5244,
        longitude=3.3792,
        interaction_ms=config["interaction_ms"],
        menu_depth=5,
        input_method="typed" if config["typed"] else "mixed",
        keystroke_interval_ms=188 if config["typed"] else 70,
        device_tilt_variance=2.3 if config["reuse_device"] else 0.2,
        navigation_signature="app_home_pay" if config["familiar_path"] else "app_new_beneficiary",
    )


def search(project: Path) -> dict[str, Any]:
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    history = normal_history(now)
    model = ModelBundle(project / "models/ato_model.joblib")
    configurations = (
        {
            "amount": amount,
            "reuse_device": reuse_device,
            "reuse_sim": reuse_sim,
            "reuse_ip": reuse_ip,
            "typed": typed,
            "familiar_path": familiar_path,
            "channel": channel,
            "interaction_ms": interaction_ms,
            "hour_shift": hour_shift,
        }
        for amount, reuse_device, reuse_sim, reuse_ip, typed, familiar_path, channel,
        interaction_ms, hour_shift in itertools.product(
            [8_000, 12_000, 18_000, 24_000, 32_000, 40_000, 48_000],
            [False, True],
            [False, True],
            [False, True],
            [False, True],
            [False, True],
            ["app", "ussd"],
            [2_000, 8_000, 20_000],
            [0, 6],
        )
    )
    pending: list[dict[str, Any]] = []
    for index, config in enumerate(configurations):
        event = candidate_event(now, config, index)
        features, _ = FeatureEngine().extract(
            event,
            history,
            {"account_id": event.account_id, "shared_device_allowed": False},
        )
        anomaly = AnomalyScorer().score(features)
        changed_signals = 1 + sum(
            not config[name]
            for name in ("reuse_device", "reuse_sim", "reuse_ip", "typed", "familiar_path")
        ) + int(config["channel"] != "app") + int(config["interaction_ms"] != 20_000) + int(
            config["hour_shift"] != 0
        )
        pending.append(
            {
                "config": config,
                "changed_signals": changed_signals,
                "event": event,
                "features": features,
                "anomaly_score": anomaly.score,
                "reasons": [item["code"] for item in anomaly.reasons],
            }
        )
    model_scores: list[float | None]
    if model.available:
        frame = pd.DataFrame(
            [[item["features"][name] for name in model.feature_names] for item in pending],
            columns=model.feature_names,
        )
        model_scores = [float(value) for value in model.model.predict_proba(frame)[:, 1]]
    else:
        model_scores = [None] * len(pending)
    evaluated: list[dict[str, Any]] = []
    for item, model_score in zip(pending, model_scores):
        fused, note = fuse_scores(model_score, item["anomaly_score"], item["features"])
        policy = PolicyEngine().decide(fused, item["features"], regret_used=0, regret_limit=3)
        evaluated.append(
            {
                "config": item["config"],
                "changed_signals": item["changed_signals"],
                "event": item["event"],
                "outcome": {
                    "score": fused,
                    "action": policy.action.value,
                    "model_score": model_score,
                    "anomaly_score": item["anomaly_score"],
                    "reasons": item["reasons"],
                    "features": item["features"],
                    "uncertainty_note": note,
                },
            }
        )
    evaders = [item for item in evaluated if item["outcome"]["score"] < 0.48]
    evaders.sort(key=lambda item: (-item["config"]["amount"], item["changed_signals"], item["outcome"]["score"]))
    best = evaders[0] if evaders else min(evaluated, key=lambda item: item["outcome"]["score"])
    mule_context = {
        "unique_senders_24h": 9.0,
        "first_time_sender_ratio_24h": 0.89,
        "inflow_amount_1h": 360_000.0,
        "outflow_amount_1h": 315_000.0,
        "rapid_cashout_ratio_1h": 0.875,
        "current_sender_first_time": 1.0,
        "network_evidence_available": 1.0,
    }
    mitigated = evaluate(best["event"], history, model, mule_context)
    recovery = BehaviorEventIn(
        event_id="adaptive_recovery_precursor",
        account_id="adaptive_customer",
        occurred_at=now - timedelta(minutes=30),
        event_type=EventType.ACCOUNT_RECOVERY,
        channel=Channel.APP,
        amount=0,
    ).model_dump(mode="json") | {"_profile_eligible": False}
    trajectory_mitigated = evaluate(best["event"], [*history, recovery], model, mule_context)
    obvious = candidate_event(
        now,
        {
            "amount": 48_000,
            "reuse_device": False,
            "reuse_sim": False,
            "reuse_ip": False,
            "typed": False,
            "familiar_path": False,
            "channel": "ussd",
            "interaction_ms": 2_000,
            "hour_shift": 6,
        },
        99_999,
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_version": model.version,
        "search_space": len(evaluated),
        "objective": "maximize transferable amount below 0.48, then minimize changed behavioural signals",
        "evasion_found": bool(evaders),
        "obvious_attack": evaluate(obvious, history, model),
        "best_evasion": {
            "config": best["config"],
            "changed_signals": best["changed_signals"],
            "outcome": best["outcome"],
        },
        "recipient_graph_mitigation": mitigated,
        "graph_plus_risk_window_mitigation": trajectory_mitigated,
        "residual_risk": (
            "A patient attacker using a fresh, previously unobserved recipient can still evade graph evidence; "
            "shadow-mode feedback and repeated adaptive search remain necessary."
        ),
    }


def render_markdown(result: dict[str, Any]) -> str:
    best = result["best_evasion"]
    return "\n".join(
        [
            "# Adaptive Attacker Red-Team",
            "",
            "The harness searches valid raw transaction configurations rather than impossible feature vectors.",
            "It is evaluation-only and does not retrain the model on the discovered evasion.",
            "",
            f"- Search space: `{result['search_space']}` valid candidates",
            f"- Model: `{result['model_version']}`",
            f"- Below-threshold evasion found: `{result['evasion_found']}`",
            f"- Obvious attack score: `{result['obvious_attack']['score']:.3f}`",
            f"- Best evasion amount: `NGN {best['config']['amount']:,.0f}`",
            f"- Best evasion score before graph context: `{best['outcome']['score']:.3f}`",
            f"- Score with recipient graph context: `{result['recipient_graph_mitigation']['score']:.3f}`",
            f"- Score with graph plus precursor risk window: `{result['graph_plus_risk_window_mitigation']['score']:.3f}`",
            "",
            "## Residual risk",
            "",
            result["residual_risk"],
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--json-output", type=Path, default=Path("artifacts/adaptive_redteam.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("docs/ADAPTIVE_REDTEAM.md"))
    args = parser.parse_args()
    result = search(args.project.resolve())
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, default=str) + "\n")
    args.markdown_output.write_text(render_markdown(result))
    print(json.dumps({key: result[key] for key in ("search_space", "model_version")}, indent=2))
    print(json.dumps(result["best_evasion"], indent=2, default=str))
    print(f"wrote={args.json_output}")


if __name__ == "__main__":
    main()
