import os, json, sqlite3, tempfile, sys
from pathlib import Path

# Ensure local import (workspace root first)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ecfr_scraper.pipeline import PipelineContext, enrich, ftsindex, analyze_ingest, analyze_metrics
from ecfr_scraper.scraper import ECFRScraper

# Synthetic normalized section artifact builder

def build_normalized_section(dir_root: Path, title: str, part: str, section: str, text: str, paragraphs=None):
    tdir = dir_root / 'sections' / f'title{title}'
    tdir.mkdir(parents=True, exist_ok=True)
    if paragraphs is None:
        paragraphs = [{"index": 0, "text": text}]
    data = {
        "title_number": title,
        "part_number": part,
        "section_number": section,
        "heading": f"§ {section} Heading",
        "paragraphs": paragraphs,
        "word_count": len(text.split()),
    }
    fname = section.replace('.', '_') + '.json'
    (tdir / fname).write_text(json.dumps(data), encoding='utf-8')


def test_analyzer_ingest_and_metrics():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        # Build two fake normalized sections with simple text & one citation
        build_normalized_section(out, '1', '1', '1.1', 'Sample text with 12 CFR 1000.1 reference.')
        build_normalized_section(out, '1', '1', '1.2', 'Another section referencing U.S.C. statute and 12 CFR 1000.2')

        # Run analyzer ingest + metrics steps directly
        scraper = ECFRScraper(output_dir=str(out))
        ctx = PipelineContext(scraper=scraper, titles=[1])
        # Instead of full pipeline, just set context so steps can locate sections dir
        analyze_ingest(ctx)
        assert ctx.analyzer_db and os.path.exists(ctx.analyzer_db)

        analyze_metrics(ctx)
        # Inspect metrics table
        con = sqlite3.connect(ctx.analyzer_db)
        try:
            cur = con.cursor()
            cur.execute('SELECT count(*) FROM metrics')
            count = cur.fetchone()[0]
            assert count == 2
            # Basic sanity: metric numeric columns not null
            cur.execute('PRAGMA table_info(metrics)')
            cols = [r[1] for r in cur.fetchall()]
            cur.execute('SELECT rrd, cci, eri, pbi, fli FROM metrics LIMIT 1')
            row = cur.fetchone()
            assert all(isinstance(v, (int, float)) for v in row)
        finally:
            con.close()
