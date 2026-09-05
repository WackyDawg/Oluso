from __future__ import annotations

import argparse
import json
import subprocess
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from aegistwin.config import Settings
from aegistwin.schemas import (
    AccountCreate,
    BehaviorEventIn,
    Channel,
    CoercionSignals,
    EventType,
    TelcoAssurance,
)
from aegistwin.service import AtoService

WIDTH, HEIGHT = 1280, 720
NAVY = "#07182B"
PANEL = "#102A43"
TEAL = "#22D3B6"
CYAN = "#5DD8FF"
WHITE = "#F5F8FC"
MUTED = "#AFC2D4"
AMBER = "#FFBE55"
RED = "#FF6B6B"
GREEN = "#70E1A1"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)


def wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], width: int, *,
            size: int = 28, fill: str = WHITE, bold: bool = False, spacing: int = 10) -> int:
    avg = max(12, int(width / (size * 0.56)))
    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=avg) or [""])
    draw.multiline_text(xy, "\n".join(lines), font=font(size, bold), fill=fill, spacing=spacing)
    return xy[1] + len(lines) * (size + spacing)


def base(title: str, kicker: str, number: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 12), fill=TEAL)
    draw.text((60, 44), kicker.upper(), font=font(18, True), fill=TEAL)
    title_size = 34 if len(title) > 52 else 42
    draw.text((60, 78), title, font=font(title_size, True), fill=WHITE)
    draw.text((60, 675), "AEGISTWIN · ICSC TRACK A · SYNTHETIC DATA ONLY", font=font(15, True), fill=MUTED)
    draw.text((1190, 675), f"{number}/9", font=font(15, True), fill=MUTED)
    return image, draw


def panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str,
          value: str, accent: str = CYAN, detail: str | None = None) -> None:
    draw.rounded_rectangle(box, radius=18, fill=PANEL, outline="#234665", width=2)
    x1, y1, x2, _ = box
    draw.text((x1 + 24, y1 + 22), title.upper(), font=font(16, True), fill=MUTED)
    value_size = 27 if len(value) > 24 else 30 if len(value) > 18 else 34
    draw.text((x1 + 24, y1 + 58), value, font=font(value_size, True), fill=accent)
    if detail:
        wrapped(draw, detail, (x1 + 24, y1 + 105), x2 - x1 - 48, size=18, fill=WHITE, spacing=7)


def build_results(project: Path, output: Path) -> dict:
    database = output / "demo_runtime.db"
    if database.exists():
        database.unlink()
    service = AtoService(
        Settings(database_path=database, model_path=project / "models/ato_model.joblib")
    )
    account_id = "aegistwin_demo_customer"
    service.create_account(
        AccountCreate(
            account_id=account_id,
            display_name="Synthetic Demo Customer",
            regret_limit_30d=3,
            trusted_contact_masked="+234 *** *** 104",
        )
    )
    now = datetime(2026, 8, 24, 11, 30, tzinfo=UTC)
    for index in range(36):
        service.score_event(
            BehaviorEventIn(
                event_id=f"demo_history_{index:03d}",
                account_id=account_id,
                occurred_at=now - timedelta(days=40 - index),
                event_type=EventType.PAYBILL if index % 3 == 0 else EventType.PURCHASE,
                channel=Channel.USSD if index % 2 else Channel.APP,
                amount=2_000 + (index % 4) * 150,
                available_balance_before=28_000,
                recipient_id=["power_company", "food_merchant", "family_contact"][index % 3],
                device_id="device_primary",
                sim_id="sim_primary",
                ip_prefix="102.88.10.0/24",
                latitude=6.5244,
                longitude=3.3792,
                interaction_ms=19_500 + (index % 3) * 700,
                menu_depth=5,
                input_method="typed" if index % 2 == 0 else "unknown",
                keystroke_interval_ms=188 if index % 2 == 0 else None,
                device_tilt_variance=2.3 if index % 2 == 0 else None,
                navigation_signature="app_home_pay" if index % 2 == 0 else "ussd_1_2_1",
            )
        )

    verified = service.score_event(
        BehaviorEventIn(
            event_id="demo_verified_sim_replacement",
            account_id=account_id,
            occurred_at=now - timedelta(minutes=10),
            event_type=EventType.PAYBILL,
            channel=Channel.USSD,
            amount=2_150,
            available_balance_before=28_000,
            recipient_id="power_company",
            sim_id="sim_customer_replacement",
            interaction_ms=20_000,
            menu_depth=5,
            navigation_signature="ussd_1_2_1",
            sim_change_verified=True,
            telco_assurance=TelcoAssurance(
                imsi_changed=True,
                iccid_changed=True,
                sim_activation_age_hours=2,
                sim_changes_30d=1,
                previous_sim_tenure_days=800,
                otp_to_sim_change_minutes=15,
                otp_sim_geo_distance_km=2,
                gateway_attested=True,
            ),
        )
    )
    attack = service.score_event(
        BehaviorEventIn(
            event_id="demo_attested_sim_swap_attack",
            account_id=account_id,
            occurred_at=now,
            event_type=EventType.TRANSFER,
            channel=Channel.USSD,
            amount=48_000,
            available_balance_before=52_000,
            recipient_id="recipient_never_seen",
            device_id="device_unknown",
            sim_id="sim_attacker_swap",
            ip_prefix="197.210.44.0/24",
            latitude=9.0765,
            longitude=7.3986,
            interaction_ms=2_400,
            menu_depth=7,
            navigation_signature="ussd_9_3_1",
            telco_assurance=TelcoAssurance(
                imsi_changed=True,
                iccid_changed=True,
                sim_type_changed=True,
                sim_activation_age_hours=1.5,
                sim_changes_30d=2,
                previous_sim_tenure_days=640,
                otp_to_sim_change_minutes=12,
                otp_sim_geo_distance_km=510,
                gateway_attested=True,
            ),
        )
    )
    coercion = service.score_event(
        BehaviorEventIn(
            event_id="demo_coercion_assisted_transfer",
            account_id=account_id,
            occurred_at=now - timedelta(minutes=20),
            event_type=EventType.TRANSFER,
            channel=Channel.APP,
            amount=18_000,
            available_balance_before=52_000,
            recipient_id="recipient_directed_by_caller",
            device_id="device_primary",
            sim_id="sim_primary",
            ip_prefix="102.88.10.0/24",
            latitude=6.5244,
            longitude=3.3792,
            interaction_ms=120_000,
            menu_depth=5,
            input_method="typed",
            keystroke_interval_ms=188,
            device_tilt_variance=2.3,
            navigation_signature="app_home_pay",
            coercion_signals=CoercionSignals(
                active_call=True,
                screen_sharing_detected=True,
                recipient_replacements=3,
                confirmation_backtracks=4,
                amount_edits=2,
                pause_before_confirmation_ms=120_000,
                recipient_pasted_during_call=True,
                on_device_coercion_score=0.91,
                consented_device_attested=True,
            ),
        )
    )
    evaluation = json.loads((project / "artifacts/evaluation.json").read_text())
    latency = json.loads((project / "artifacts/latency.json").read_text())
    adaptive = json.loads((project / "artifacts/adaptive_redteam.json").read_text())
    v5_live_proof = json.loads((project / "artifacts/v5_feature_demo.json").read_text())
    v1_platform_proof = json.loads((project / "artifacts/v1_platform_demo.json").read_text())
    load_evidence = json.loads((project / "artifacts/concurrent_load.json").read_text())
    outage_evidence = json.loads((project / "artifacts/outage_resilience.json").read_text())
    agent_terminal_evidence = json.loads(
        (project / "artifacts/agent_terminal_demo.json").read_text()
    )
    fraud_sketch_evidence = json.loads(
        (project / "artifacts/fraud_sketch_exchange.json").read_text()
    )
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "actual local AtoService scoring run; all identities and events are synthetic",
        "verified_replacement": verified.model_dump(mode="json"),
        "attested_sim_swap": attack.model_dump(mode="json"),
        "coercion_assisted_transfer": coercion.model_dump(mode="json"),
        "audit_verification": service.audit.verify(),
        "evaluation": evaluation,
        "latency": latency,
        "adaptive_redteam": adaptive,
        "v5_live_proof": v5_live_proof,
        "v1_platform_proof": v1_platform_proof,
        "load_evidence": load_evidence,
        "outage_evidence": outage_evidence,
        "agent_terminal_evidence": agent_terminal_evidence,
        "fraud_sketch_evidence": fraud_sketch_evidence,
    }
    (output / "demo_results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def make_frames(result: dict, output: Path) -> list[Path]:
    verified = result["verified_replacement"]
    attack = result["attested_sim_swap"]
    evaluation = result["evaluation"]
    operating = evaluation["operating_points"]["Customer confirmation or stronger"]
    latency = result["latency"]
    load = result["load_evidence"]
    outage = result["outage_evidence"]
    agent = result["agent_terminal_evidence"]
    sketch = result["fraud_sketch_evidence"]
    frames: list[Image.Image] = []

    img, draw = base("AegisTwin: prove the human, not only the secret", "Working prototype", 1)
    wrapped(draw, "Behavioural account-takeover defence for Nigerian app, USSD and agency banking.",
            (60, 165), 760, size=30, fill=WHITE, bold=True)
    panel(draw, (60, 300, 405, 575), "Decision speed", f"p99 {latency['p99_ms']:.0f} ms", GREEN,
          "Measured end-to-end through FastAPI, feature retrieval, model, policy, persistence and audit.")
    panel(draw, (435, 300, 780, 575), "Feature phones", "USSD ready", TEAL,
          "Server behaviour plus an optional attested telco envelope—no phone sensors required.")
    panel(draw, (810, 300, 1220, 575), "Response", "Reversible", AMBER,
          "Monitor, confirm, delay, hold, or privately safety-pause—with actionable recourse.")
    frames.append(img)

    img, draw = base("Same scary SIM change. Different decision.", "Live comparison", 2)
    panel(draw, (60, 170, 610, 590), "Verified customer replacement",
          verified["policy"]["action"].replace("_", " ").title(), GREEN,
          f"Risk {verified['score']['fused_score']:.3f}. {verified['customer_explanation']}")
    panel(draw, (670, 170, 1220, 590), "Unverified takeover sequence",
          attack["policy"]["action"].replace("_", " ").title(), RED,
          f"Risk {attack['score']['fused_score']:.3f}. {attack['customer_explanation']}")
    frames.append(img)

    img, draw = base("The evidence ladder degrades gracefully", "USSD answer", 3)
    items = [
        ("APP", "typing, paste, handling, navigation", CYAN),
        ("USSD", "menu rhythm, SIM, recipient, velocity", TEAL),
        ("TELCO", "attested lifecycle flags—not raw IDs", GREEN),
        ("CORE", "amount, time, recovery, beneficiary", AMBER),
    ]
    for index, (name, detail, color) in enumerate(items):
        y = 170 + index * 105
        draw.rounded_rectangle((80, y, 1200, y + 78), radius=16, fill=PANEL)
        draw.text((105, y + 21), name, font=font(22, True), fill=color)
        draw.text((270, y + 22), detail, font=font(22), fill=WHITE)
    frames.append(img)

    img, draw = base("Twelve lenses, one accountable decision", "AI architecture", 4)
    items = [
        ("HUMAN", "Sender twin + separate decision confidence", CYAN),
        ("NETWORK", "Mule graph + agent-terminal integrity", TEAL),
        ("SEQUENCE", "Risk window + cross-channel transition twin", GREEN),
        ("CONTEXT", "Calendar rhythm + coercion safety", AMBER),
        ("ACTION", "Population AI + personalised friction cost", RED),
    ]
    for index, (name, detail, color) in enumerate(items):
        y = 158 + index * 88
        draw.rounded_rectangle((80, y, 1200, y + 64), radius=16, fill=PANEL)
        draw.text((105, y + 16), name, font=font(20, True), fill=color)
        draw.text((300, y + 17), detail, font=font(20), fill=WHITE)
    frames.append(img)

    img, draw = base("Held-out proof, including what the model misses", "v1.4 honest evaluation", 5)
    panel(draw, (60, 175, 355, 535), "Recall", f"{operating['recall']:.1%}", GREEN,
          f"{operating['true_positives']} of {operating['takeover_events']} takeover events challenged.")
    panel(draw, (382, 175, 677, 535), "False-positive rate", f"{operating['false_positive_rate']:.3%}", CYAN,
          f"{operating['false_positives']} of {operating['normal_events']} normal held-out sessions.")
    robust = json.loads((Path(__file__).resolve().parents[1] / "artifacts/robustness.json").read_text())
    panel(draw, (704, 175, 999, 535), "Non-perfect AUC",
          f"{evaluation['model_only_roc_auc']:.3f} / {evaluation['fused_roc_auc']:.3f}", TEAL,
          f"Model / fused. Zero-overlap accounts: {robust['account_disjoint']['customer_confirmation']['recall']:.1%} recall. Low-and-slow remains a disclosed miss.")
    panel(draw, (1026, 175, 1220, 535), "Latency", f"{latency['p99_ms']:.0f} ms", AMBER,
          "Under the one-second live-transfer requirement on this laptop benchmark.")
    frames.append(img)

    img, draw = base("One compromised agent terminal. Many protected customers.", "v1.2 live proof", 6)
    busy = agent["busy_legitimate_terminal"]
    compromised = agent["compromised_terminal"]
    quarantine = agent["quarantine_proof"]
    panel(draw, (60, 175, 390, 545), "Busy legitimate agent", f"{busy['risk_score']:.3f}", GREEN,
          "High customer volume alone is not a campaign. The terminal remains available.")
    panel(draw, (475, 175, 805, 545), "Cross-customer campaign", f"{compromised['risk_score']:.3f}", RED,
          f"Concentrated recipient plus authentication failures triggers a reversible delay in {compromised['detection_ms']:.0f} ms.")
    panel(draw, (890, 175, 1220, 545), "Independent feedback", f"{quarantine['risk_score']:.3f}", TEAL,
          "One victim monitors. Two elevate. Three quarantine. A forged unattested claim is ignored.")
    frames.append(img)

    img, draw = base("Banks collaborate without exposing customer data", "v1.3 private exchange", 7)
    one = sketch["one_institution"]
    two = sketch["two_institutions_without_local_corroboration"]
    corroborated = sketch["two_institutions_with_local_corroboration"]
    panel(draw, (60, 160, 390, 570), "One institution", f"{one['other_account_score']:.3f}", CYAN,
          "Signed rotating sketch. Observe only: one bank cannot interrupt the customer.")
    panel(draw, (475, 160, 805, 570), "Two banks, no local proof", f"{two['risk_score']:.3f}", GREEN,
          "Independent match still caps at monitoring. Raw recipient and institution identifiers are absent from shared rows.")
    panel(draw, (890, 160, 1220, 570), "Locally corroborated", f"{corroborated['risk_score']:.3f}", AMBER,
          "The same private signal plus local anomaly produces a reversible delay; revocation and outage cache are live.")
    frames.append(img)

    img, draw = base("Power fails. Safety does not.", "v1.3 outage drill", 8)
    panel(draw, (60, 160, 600, 350), "Signed operating state",
          "DEGRADED → ISOLATED", CYAN,
          f"Edge capsule valid. Known-recipient confidence falls to {outage['degraded_known_recipient']['decision_confidence']:.0%}; outage activity cannot teach the twin.")
    panel(draw, (680, 160, 1220, 350), "Customer-safe isolation",
          outage["isolated_payment"]["offline_reference"], AMBER,
          "The payment remains held. The receipt states that no money moved and avoids a false success claim.")
    panel(draw, (60, 380, 600, 590), "Tamper-evident queue",
          "ALTERED → DETECTED", RED,
          f"All {outage['journal']['entries_before_recovery']} outage decisions are hash-chained with original timestamps.")
    panel(draw, (680, 380, 1220, 590), "Bounded reconciliation",
          f"{outage['reconciliation']['processed']} replayed · 0 duplicates", GREEN,
          "Risk-prioritised re-scoring returns ONLINE without automatic settlement.")
    frames.append(img)

    img, draw = base("Ready to inspect, rerun and challenge", "Final handoff", 9)
    audit = result["audit_verification"]
    wrapped(draw, "The package includes the four-page report, this demo, full source, synthetic data, model, 53 tests, clean-copy startup proof, robustness gates, private exchange, agent and outage evidence, SBOM and failure cases.",
            (80, 185), 1120, size=31, fill=WHITE, bold=True, spacing=12)
    panel(draw, (80, 350, 1200, 555), "Audit + reproduce",
          f"CHAIN {'VALID' if audit['valid'] else 'INVALID'} · pytest", TEAL,
          f"Run demo_v1_platform.py and the adaptive search. Concurrent proof: {load['successes']}/{load['requests']} requests, audit valid.")
    frames.append(img)

    paths: list[Path] = []
    for index, frame in enumerate(frames, start=1):
        path = output / f"frame_{index:02d}.png"
        frame.save(path, optimize=True)
        paths.append(path)
    return paths


def encode_video(frames: list[Path], output: Path) -> Path:
    concat = output / "frames.txt"
    lines: list[str] = []
    for frame in frames:
        lines.extend([f"file '{frame.as_posix()}'", "duration 4"])
    lines.append(f"file '{frames[-1].as_posix()}'")
    concat.write_text("\n".join(lines) + "\n")
    video = output / "AegisTwin_TrackA_Demo.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
            "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium",
            "-crf", "22", "-movflags", "+faststart", str(video),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return video


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = build_results(args.project.resolve(), args.output.resolve())
    video = encode_video(make_frames(result, args.output.resolve()), args.output.resolve())
    print(f"video={video}")
    print(f"verified_action={result['verified_replacement']['policy']['action']}")
    print(f"attack_action={result['attested_sim_swap']['policy']['action']}")
    print(f"audit_valid={result['audit_verification']['valid']}")


if __name__ == "__main__":
    main()
