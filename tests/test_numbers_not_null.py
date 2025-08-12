import json, tempfile, os, sys
from pathlib import Path

# Ensure local package path (workspace root) precedes any installed version
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib, importlib.util
try:
    norm = importlib.import_module('ecfr_scraper.normalize')
except ModuleNotFoundError:
    fp = ROOT / 'ecfr_scraper' / 'normalize.py'
    spec = importlib.util.spec_from_file_location('ecfr_scraper.normalize', fp)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
        norm = module  # type: ignore
    else:  # pragma: no cover
        raise

def make_minimal_title(tmp: Path):
    # Build a synthetic title JSON with missing numbers to ensure backfill works
    doc = {
        "title_number": "44",
        "title_name": "Test Title",
        "parts": [
            {"part_number": None, "part_name": "PART 123—TEST PART", "sections": [
                {"section_number": None, "section_name": "§ 123.4   Sample section.", "content": "§ 123.4   Sample section.\nBody text."}
            ]}
        ],
        "stats": {"total_sections": 1, "word_count": 3, "paragraph_count": 1}
    }
    p = tmp / 'title44.json'
    p.write_text(json.dumps(doc), encoding='utf-8')
    return p


def test_numbers_backfilled():
    td = tempfile.TemporaryDirectory()
    try:
        base = Path(td.name)
        title_path = make_minimal_title(base)
        cache = norm.load_cache(base)
        norm.normalize_title_file(title_path, output_dir=base, cache=cache)
        updated = json.loads(title_path.read_text(encoding='utf-8'))
        part = updated['parts'][0]
        section = part['sections'][0]
        assert part['part_number'] == '123'
        assert section['section_number'] == '123.4'
        assert part['part_number']
        assert section['section_number']
    finally:
        td.cleanup()
