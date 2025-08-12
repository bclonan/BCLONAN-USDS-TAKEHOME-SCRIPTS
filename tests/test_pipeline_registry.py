import types
from ecfr_scraper.pipeline import STEP_REGISTRY

def test_expected_steps_registered():
    # Core + extended analyzer / embedding steps
    expected = {"download","diff","parse","export","minify","gzipxml","manifest","enrich","ftsindex","embed","embedparas","analyze_ingest","analyze_metrics","apiserve"}
    missing = expected.difference(STEP_REGISTRY.keys())
    assert not missing, f"Missing steps: {missing}"
    # All registered are callables
    for name, func in STEP_REGISTRY.items():
        assert callable(func), f"Step {name} not callable"
