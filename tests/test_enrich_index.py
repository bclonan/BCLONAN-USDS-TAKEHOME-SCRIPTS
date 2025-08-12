import os, json, sqlite3, tempfile
from ecfr_scraper.pipeline import run_pipeline
from ecfr_scraper.scraper import ECFRScraper

# Minimal synthetic parsed structure to avoid network

def make_fake_env(tmpdir):
    scraper = ECFRScraper(output_dir=tmpdir)
    # create fake parsed doc
    parsed_doc = {
        "title_number": "1",
        "parts": [
            {"part_number": "1", "sections": [
                {"section_number": "1.1", "section_name": "Intro", "content": "Sample content one", "word_count": 3},
                {"section_number": "1.2", "section_name": "Scope", "content": "Additional sample text", "word_count": 3},
            ]}
        ]
    }
    fake_xml = os.path.join(tmpdir, 'title1.xml')
    with open(fake_xml,'w',encoding='utf-8') as f:
        f.write('<ROOT></ROOT>')  # placeholder
    return scraper, fake_xml, parsed_doc


def test_enrich_and_index():
    with tempfile.TemporaryDirectory() as tmp:
        scraper, fake_xml, parsed_doc = make_fake_env(tmp)
        from ecfr_scraper.pipeline import PipelineContext, enrich, ftsindex
        ctx = PipelineContext(scraper=scraper, titles=[1])
        ctx.xml_files.append(fake_xml)
        ctx.parsed.append({"path": fake_xml, "data": parsed_doc})
        enrich(ctx)
        assert ctx.enriched_sections and len(ctx.enriched_sections) == 2
        ftsindex(ctx)
        assert ctx.db_path and os.path.exists(ctx.db_path)
        # simple FTS query
        con = sqlite3.connect(ctx.db_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT count(*) FROM sections WHERE sections MATCH 'sample'")
            count = cur.fetchone()[0]
            assert count >= 1
        finally:
            con.close()
