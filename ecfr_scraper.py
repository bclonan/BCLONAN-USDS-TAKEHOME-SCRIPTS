"""
Legacy wrapper that delegates to the ecfr_scraper package CLI.

Kept for backward compatibility with existing scripts or instructions
that call `python ecfr_scraper.py ...`.
"""

from ecfr_scraper.cli import main

if __name__ == "__main__":
    raise SystemExit(main())