import os, sqlite3, tempfile
from pathlib import Path
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from ecfr_scraper.api import create_app


def build_small_index(tmp: Path) -> str:
    db_path = tmp / 'ecfr_index.sqlite'
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("CREATE VIRTUAL TABLE sections USING fts5(title, part, section, heading, content, word_count UNINDEXED)")
        rows = [
            ("1","1","1.1","Intro","This section introduces the framework.",5),
            ("1","1","1.2","Scope","Scope of regulations and applicability.",6),
            ("2","5","5.10","Definitions","Definitions and terms used herein.",5),
        ]
        cur.executemany("INSERT INTO sections VALUES (?,?,?,?,?,?)", rows)
        con.commit()
    finally:
        con.close()
    return str(db_path)


def test_health_and_titles():
    with tempfile.TemporaryDirectory() as td:
        db = build_small_index(Path(td))
        app = create_app(db)
        client = TestClient(app)
        r = client.get('/health')
        assert r.status_code == 200 and r.json()['status'] == 'ok'
        r = client.get('/titles')
        assert r.status_code == 200
        assert set(r.json()) == {"1","2"}


def test_search_and_section():
    with tempfile.TemporaryDirectory() as td:
        db = build_small_index(Path(td))
        app = create_app(db)
        client = TestClient(app)
        r = client.get('/search', params={'q':'section'})
        assert r.status_code == 200
        results = r.json()
        assert results and any('Intro' in (res['heading'] or '') for res in results)
        rowid = results[0]['rowid']
        sec = client.get(f'/section/{rowid}')
        assert sec.status_code == 200
        body = sec.json()
        assert body['rowid'] == rowid


def test_suggest():
    with tempfile.TemporaryDirectory() as td:
        db = build_small_index(Path(td))
        app = create_app(db)
        client = TestClient(app)
        r = client.get('/suggest', params={'prefix':'Def'})
        assert r.status_code == 200
        assert any(h.startswith('Def') for h in r.json())
