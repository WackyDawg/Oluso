from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.source) as source, sqlite3.connect(args.destination) as target:
        source.backup(target)
    with sqlite3.connect(args.destination) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    manifest = {
        "created_at": datetime.now(UTC).isoformat(), "source": args.source.name,
        "backup": args.destination.name, "sha256": digest(args.destination),
        "integrity_check": integrity, "restore_test": integrity == "ok",
    }
    output = args.destination.with_suffix(args.destination.suffix + ".manifest.json")
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
