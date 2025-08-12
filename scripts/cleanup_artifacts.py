#!/usr/bin/env python
"""Cleanup helper to remove derived artifacts so the pipeline rebuilds fresh.

Usage (PowerShell):
    python scripts/cleanup_artifacts.py --output .\\data --reset

Flags:
  --output/-o PATH   Root data directory (default: ./data)
  --reset            Also remove checksum DB to force all titles to reprocess
  --yes              Do not prompt for confirmation (non-interactive)

Removes (if present):
  ecfr_index.sqlite, analyzer.sqlite, sections/ directory, artifacts/manifest JSON,
  *.min.xml, *.xml.gz, paragraph/section embedding tables (by dropping DB files),
  optionally checksums.json when --reset supplied.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

TARGETS = [
    'ecfr_index.sqlite',
    'analyzer.sqlite',
    'artifacts.json',
    'manifest.json',
]

GLOB_TARGETS = [
    '*.min.xml',
    '*.xml.gz',
]

SECTION_DIR = 'sections'
CHECKSUM_FILE = 'checksums.json'

def remove_path(p: Path) -> None:
    if not p.exists():
        return
    if p.is_dir():
        for child in p.rglob('*'):
            if child.is_file():
                try:
                    child.unlink()
                except Exception:
                    pass
        try:
            p.rmdir()
        except Exception:
            pass
    else:
        try:
            p.unlink()
        except Exception:
            pass

def main() -> int:
    ap = argparse.ArgumentParser(description='Cleanup derived eCFR artifacts.')
    ap.add_argument('--output','-o', default='data', help='Data/output directory (default: data)')
    ap.add_argument('--reset', action='store_true', help='Also remove checksum DB to force full reprocess')
    ap.add_argument('--yes', action='store_true', help='Skip confirmation prompt')
    args = ap.parse_args()

    root = Path(args.output).resolve()
    if not root.exists():
        print(f"Output directory {root} does not exist", file=sys.stderr)
        return 1

    to_remove = []
    for name in TARGETS:
        to_remove.append(root / name)
    for pattern in GLOB_TARGETS:
        to_remove.extend(root.glob(pattern))
    to_remove.append(root / SECTION_DIR)
    if args.reset:
        to_remove.append(root / CHECKSUM_FILE)

    # filter unique
    uniq = []
    seen = set()
    for p in to_remove:
        if str(p) not in seen:
            uniq.append(p)
            seen.add(str(p))

    existing = [p for p in uniq if p.exists()]
    if not existing:
        print('Nothing to remove.')
        return 0

    print('Will remove:')
    for p in existing:
        print('  -', p)
    if not args.yes:
        resp = input('Proceed? [y/N] ').strip().lower()
        if resp not in {'y','yes'}:
            print('Aborted.')
            return 1

    for p in existing:
        remove_path(p)
    print(f"Removed {len(existing)} paths. Done.")
    return 0

if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
