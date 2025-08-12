"""Batch re-normalize all exported title JSON files.

Usage (after export step has produced data/title*.json):
    python -m scripts.batch_normalize [--force]

By default uses the normalization cache to skip unchanged sections.
Use --force to ignore cache (recompute all) by deleting the cache file first.
"""
from __future__ import annotations

from pathlib import Path
import argparse
from ecfr_scraper import normalize as norm


def run(force: bool = False, data_dir: str = 'data') -> int:
    base = Path(data_dir)
    if force:
        cache_file = base / norm.CACHE_FILENAME
        if cache_file.exists():
            cache_file.unlink()
    cache = norm.load_cache(base)
    count = 0
    for tf in sorted(base.glob('title*.json')):
        count += norm.normalize_title_file(tf, output_dir=base, cache=cache)
    norm.save_cache(base, cache)
    return count


def main():
    ap = argparse.ArgumentParser(description="Batch normalize title JSON files")
    ap.add_argument('--data-dir', default='data', help='Directory containing title*.json exports')
    ap.add_argument('--force', action='store_true', help='Recompute all (ignore existing cache)')
    args = ap.parse_args()
    sections = run(force=args.force, data_dir=args.data_dir)
    print(f"Normalized {sections} sections (cached unchanged skipped).", flush=True)


if __name__ == '__main__':  # pragma: no cover
    main()
