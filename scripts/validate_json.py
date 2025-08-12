from __future__ import annotations

"""Validate exported JSON files for structural and content expectations.

Checks performed:
    * Required top-level keys present
    * Stats integrity (word_count >= sum child counts, non-negative)
    * Section objects required fields
    * Duplicate section numbers within a part
    * Optional lexical_analysis consistency

Exit code 0 on success, 1 if any errors.
"""

import json
import glob
import sys
from pathlib import Path


REQUIRED_TOP = {"title_number", "title_name", "parts", "stats"}
REQUIRED_SECTION = {"section_number", "section_name", "content", "word_count"}


def load_json(path: Path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_doc(path: Path):
    errors = []
    try:
        data = load_json(path)
    except Exception as e:
        return [f"Failed to parse JSON: {e}"]
    missing = REQUIRED_TOP - data.keys()
    if missing:
        errors.append(f"Missing top-level keys: {sorted(missing)}")
    stats = data.get('stats', {})
    for k in ('total_sections','word_count','paragraph_count'):
        v = stats.get(k)
        if v is None or not isinstance(v, int) or v < 0:
            errors.append(f"Invalid stats.{k}: {v}")
    counted_sections = 0
    sum_word = 0
    for p in data.get('parts', []):
        if p.get('part_number') in (None, ""):
            errors.append("Null/empty part_number not allowed")
        seen_sections = set()
        for s in p.get('sections', []):
            counted_sections += 1
            for rk in REQUIRED_SECTION:
                if rk not in s:
                    errors.append(f"Section missing {rk} in part {p.get('part_number')} section {s.get('section_number')}")
            if s.get('section_number') in (None, ""):
                errors.append(f"Null/empty section_number in part {p.get('part_number')}")
            num = s.get('section_number')
            if num in seen_sections:
                errors.append(f"Duplicate section_number {num} in part {p.get('part_number')}")
            else:
                seen_sections.add(num)
            wc = s.get('word_count')
            if isinstance(wc, int):
                sum_word += wc
    if stats.get('total_sections') is not None and counted_sections != stats.get('total_sections'):
        errors.append(f"stats.total_sections={stats.get('total_sections')} mismatch counted={counted_sections}")
    if stats.get('word_count') is not None and sum_word > stats.get('word_count'):
        errors.append(f"stats.word_count={stats.get('word_count')} less than sum(section.word_count)={sum_word}")
    lex = data.get('lexical_analysis')
    if lex:
        if lex.get('total_words') and lex.get('total_words') < stats.get('word_count', 0):
            errors.append("lexical_analysis.total_words < stats.word_count")
    return errors


def main(argv: list[str] | None = None):
    if argv is None:
        argv = sys.argv
    pattern = argv[1] if len(argv) > 1 else 'data/title*.json'
    paths = [Path(p) for p in glob.glob(pattern)]
    report = []
    total_errors = 0
    for p in paths:
        errs = validate_doc(p)
        if errs:
            total_errors += len(errs)
        report.append({'file': p.name, 'errors': errs})
    print(json.dumps(report, indent=2))
    return 1 if total_errors else 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main(sys.argv))
