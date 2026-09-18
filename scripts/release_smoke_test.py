from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def extracted_root(directory: Path) -> Path:
    candidates = [path for path in directory.iterdir() if path.is_dir()]
    if len(candidates) == 1:
        return candidates[0]
    if (directory / ".env.example").is_file():
        return directory
    raise ValueError("could not identify the extracted source root")


def stage_source(source: Path, destination: Path) -> Path:
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            archive.extractall(destination)
        return extracted_root(destination)

    root = destination / "Oluso_TrackA_Code"
    root.mkdir()
    for name in (".env.example", "app.py", "src", "models"):
        item = source / name
        target = root / name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    return root


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Boot the packaged application using the checked-in environment example"
    )
    parser.add_argument("source", type=Path, help="Project directory or source ZIP")
    args = parser.parse_args()

    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix="oluso-release-smoke-") as temporary:
        root = stage_source(source, Path(temporary))
        shutil.copy2(root / ".env.example", root / ".env")
        (root / "data").mkdir(exist_ok=True)

        inherited_paths = [str(Path(item).resolve()) for item in sys.path if item]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join([str(root / "src"), *inherited_paths])
        command = """
import json
from fastapi.testclient import TestClient
from oluso.config import Settings
from app import app

settings = Settings()
assert settings.allowed_tenants == ["default", "demo-bank", "partner-bank"]
assert settings.cors_origins == ["http://localhost:8501", "http://localhost:3000"]
response = TestClient(app).get("/health")
assert response.status_code == 200, response.text
print(json.dumps({"env_example": "valid", "health": response.status_code}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", command],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "release smoke test failed:\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
