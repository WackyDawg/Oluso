"""Assemble the ICSC Track A submission package from this repository.

Inputs are versioned under submission/ (cover text, report, demo) plus artifacts/ and docs/.
Output goes to submission/dist/ (git-ignored): a flat package with Documentation/, Evidence/,
the source ZIP and a SHA256SUMS manifest, then an outer ZIP. The packaged source must pass
scripts/release_smoke_test.py before the manifest is written.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SUBMISSION = PROJECT / "submission"
PACKAGE_TEXT = SUBMISSION / "package_text"   # hand-maintained cover documents
REPORT = SUBMISSION / "report"               # write-up from tools/build_technical_writeup.py
DEMO = SUBMISSION / "demo"                   # MP4 + demo_results.json from tools/build_demo_video.py
DIST = SUBMISSION / "dist"                   # generated, git-ignored
FINAL_ROOT = DIST / "Oluso_TrackA_Final"
OUTER_ZIP = DIST / "Oluso_TrackA_Final.zip"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def source_files() -> list[Path]:
    individual = [
        ".env.example",
        ".dockerignore",
        "Dockerfile",
        "LICENSE",
        "README.md",
        "SECURITY.md",
        "app.py",
        "docker-compose.yml",
        "pyproject.toml",
        "requirements.txt",
    ]
    directories = [
        ".github",
        "artifacts",
        "config",
        "dashboard",
        "data",
        "docs",
        "models",
        "scripts",
        "src",
        "tests",
        "tools",
    ]
    files = [PROJECT / name for name in individual if (PROJECT / name).is_file()]
    for directory in directories:
        root = PROJECT / directory
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(PROJECT)
            if any(
                part in {"__pycache__", ".pytest_cache", ".ruff_cache"}
                or part.endswith(".egg-info")
                for part in relative.parts
            ):
                continue
            if path.suffix in {".pyc", ".db"} or path.name.endswith((".db-wal", ".db-shm")):
                continue
            if directory == "artifacts" and path.suffix not in {".json"}:
                continue
            files.append(path)
    return sorted(set(files), key=lambda item: item.as_posix())


def build_source_zip(destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in source_files():
            relative = path.relative_to(PROJECT)
            archive.write(path, Path("Oluso_TrackA_Code") / relative)


def build() -> None:
    if FINAL_ROOT.parent.exists():
        shutil.rmtree(FINAL_ROOT.parent)
    FINAL_ROOT.mkdir(parents=True)

    report = REPORT
    demo = DEMO
    copy_file(report / "Oluso_TrackA_Technical_Writeup.pdf", FINAL_ROOT / "Oluso_TrackA_Technical_Writeup.pdf")
    copy_file(report / "Oluso_TrackA_Technical_Writeup.docx", FINAL_ROOT / "Oluso_TrackA_Technical_Writeup.docx")
    copy_file(demo / "Oluso_TrackA_Demo.mp4", FINAL_ROOT / "Oluso_TrackA_Demo.mp4")

    for name in ("README_FIRST.md", "PACKAGE_CONTENTS.md", "SUBMISSION_CHECKLIST.md", "CODE_LINK.md"):
        copy_file(PACKAGE_TEXT / name, FINAL_ROOT / name)

    documentation = FINAL_ROOT / "Documentation"
    for path in sorted((PROJECT / "docs").glob("*.md")):
        copy_file(path, documentation / path.name)
    copy_file(PROJECT / "SECURITY.md", documentation / "SECURITY.md")

    evidence_names = [
        "adaptive_redteam.json",
        "agent_terminal_demo.json",
        "concurrent_load.json",
        "coverage.json",
        "evaluation.json",
        "fraud_sketch_exchange.json",
        "latency.json",
        "outage_resilience.json",
        "robustness.json",
        "sbom.cdx.json",
        "v1_platform_demo.json",
        "v1_platform_demo_backup.db",
        "v1_platform_demo_backup.db.manifest.json",
        "v5_feature_demo.json",
    ]
    for name in evidence_names:
        copy_file(PROJECT / "artifacts" / name, FINAL_ROOT / "Evidence" / name)
    copy_file(demo / "demo_results.json", FINAL_ROOT / "Evidence" / "demo_results.json")

    build_source_zip(FINAL_ROOT / "Oluso_TrackA_Code.zip")
    subprocess.run(
        [
            sys.executable,
            str(PROJECT / "scripts/release_smoke_test.py"),
            str(FINAL_ROOT / "Oluso_TrackA_Code.zip"),
        ],
        check=True,
        cwd=PROJECT,
    )

    manifest_lines = []
    for path in sorted(FINAL_ROOT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            manifest_lines.append(f"{digest(path)}  {path.relative_to(FINAL_ROOT).as_posix()}")
    (FINAL_ROOT / "SHA256SUMS.txt").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    if OUTER_ZIP.exists():
        OUTER_ZIP.unlink()
    with zipfile.ZipFile(OUTER_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(FINAL_ROOT.rglob("*")):
            if path.is_file():
                archive.write(path, Path(FINAL_ROOT.name) / path.relative_to(FINAL_ROOT))

    print(f"final_root={FINAL_ROOT}")
    print(f"outer_zip={OUTER_ZIP}")
    print(f"outer_sha256={digest(OUTER_ZIP)}")


if __name__ == "__main__":
    build()
