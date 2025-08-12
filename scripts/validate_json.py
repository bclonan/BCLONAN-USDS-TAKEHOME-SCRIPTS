"""Validate eCFR JSON files for structural and textual anomalies.

Usage (PowerShell):
  python scripts/validate_json.py "data/title*.json" > validation_report.json
"""

from __future__ import annotations

import sys
import re
import json
import hashlib
from pathlib import Path
from typing import List


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def validate_json(path: Path) -> dict:
    """Validate a single JSON file for structural issues."""
    raw = path.read_bytes()
    report: dict = {
        "file": path.name,
        "size": len(raw),
        "sha256": sha256_bytes(raw),
        "errors": [],
        "warnings": [],
        "stats": {},
    }

    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        report["errors"].append(f"JSON decode error: {e}")
        return report
    except UnicodeDecodeError as e:
        report["errors"].append(f"Unicode decode error: {e}")
        return report

    # Add basic validation logic here
    if not isinstance(data, dict):
        report["errors"].append("Root element is not a JSON object")

    return report


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else "data/title*.json"
    json_files = list(Path(".").glob(pattern))
    if not json_files:
        print("No JSON files found", file=sys.stderr)
        sys.exit(1)

    validation_results = [validate_json(file) for file in json_files]
    print(json.dumps(validation_results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
