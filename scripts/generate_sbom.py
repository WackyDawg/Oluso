from __future__ import annotations

import importlib.metadata
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    components = [{"type": "library", "name": item.metadata["Name"], "version": item.version}
                  for item in importlib.metadata.distributions() if item.metadata["Name"]]
    document = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {"timestamp": datetime.now(UTC).isoformat(),
                     "component": {"type": "application", "name": "oluso-ato", "version": "1.4.0"}},
        "components": sorted(components, key=lambda item: item["name"].lower()),
    }
    output = Path("artifacts/sbom.cdx.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"wrote={output} components={len(components)}")


if __name__ == "__main__":
    main()
