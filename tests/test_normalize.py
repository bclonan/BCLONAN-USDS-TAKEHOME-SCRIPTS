import sys, importlib, importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    norm = importlib.import_module('ecfr_scraper.normalize')
except ModuleNotFoundError:  # fallback direct load
    fp = ROOT / 'ecfr_scraper' / 'normalize.py'
    spec = importlib.util.spec_from_file_location('ecfr_scraper.normalize', fp)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
        norm = module  # type: ignore
    else:  # pragma: no cover
        raise

def test_extract_heading():
    h = norm.extract_heading("§ 10.2   Scope and sources.")
    assert h["section_number"] == "10.2"
    assert h["short_title"] and "Scope" in h["short_title"]

def test_cfr_citation_extraction():
    text = "This references 12 CFR 1026.4 and 12 CFR 1026.5 in context."
    cites = norm.extract_cfr_citations(text)
    assert "12 CFR 1026.4" in cites and "12 CFR 1026.5" in cites

def test_normalize_section_anchor():
    section = {"section_name": "§ 21.10   Sections.", "content": "§ 21.10   Sections.\n(a) Alpha."}
    out = norm.normalize_section(section, title_number="21")
    assert out["anchor_id"] == "title21-21-10"
    assert out["paragraphs"]
