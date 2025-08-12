"""FastAPI application factory for eCFR search API.

Separated from pipeline.apiserve so we can unit test endpoints without
launching uvicorn. Analyzer router is mounted automatically if analyzer
DB is present (data/analyzer.sqlite by default) or if provided explicitly.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

try:  # Optional import; the project declares fastapi in extras
    from fastapi import FastAPI, HTTPException
except Exception:  # pragma: no cover
    FastAPI = None  # type: ignore
    HTTPException = Exception  # type: ignore


def create_app(db_path: str, analyzer_db: Optional[str] = None) -> "FastAPI":  # type: ignore
    if FastAPI is None:  # pragma: no cover
        raise RuntimeError("fastapi not installed; install with .[api]")
    if not Path(db_path).exists():
        raise FileNotFoundError(f"SQLite FTS index not found: {db_path}")

    app = FastAPI(title="eCFR Search API")

    def _connect():
        return sqlite3.connect(db_path)

    @app.get('/health')  # type: ignore
    def health():  # pragma: no cover - trivial
        return {'status': 'ok'}

    @app.get('/search')  # type: ignore
    def search(q: str, limit: int = 10):
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT rowid, title, part, section, heading, snippet(sections, 4, '[', ']', '...', 10) FROM sections WHERE sections MATCH ? LIMIT ?", (q, limit))
            rows = cur.fetchall()
            return [
                {'rowid': r[0], 'title': r[1], 'part': r[2], 'section': r[3], 'heading': r[4], 'snippet': r[5]} for r in rows
            ]
        finally:
            conn.close()

    @app.get('/titles')  # type: ignore
    def list_titles():
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT title FROM sections ORDER BY 1")
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    @app.get('/section/{rowid}')  # type: ignore
    def get_section(rowid: int):  # pragma: no cover (logic simple)
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT rowid, title, part, section, heading, content, word_count FROM sections WHERE rowid=?", (rowid,))
            row = cur.fetchone()
            if not row:
                if HTTPException is not Exception:
                    raise HTTPException(status_code=404, detail="Not found")  # type: ignore
                raise RuntimeError("Not found")
            return {
                'rowid': row[0], 'title': row[1], 'part': row[2], 'section': row[3], 'heading': row[4], 'content': row[5], 'word_count': row[6]
            }
        finally:
            conn.close()

    @app.get('/suggest')  # type: ignore
    def suggest(prefix: str, limit: int = 10):
        conn = _connect()
        try:
            cur = conn.cursor()
            like = f"{prefix}%"
            cur.execute("SELECT DISTINCT heading FROM sections WHERE heading LIKE ? ORDER BY heading LIMIT ?", (like, limit))
            return [r[0] for r in cur.fetchall() if r[0]]
        finally:
            conn.close()

    @app.get('/embed-search')  # type: ignore
    def embed_search(q: str, limit: int = 5):  # pragma: no cover heavy
        # Optional semantic similarity if embeddings table present
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception:
            if HTTPException is not Exception:
                raise HTTPException(status_code=400, detail="Embeddings not enabled (install .[embed])")  # type: ignore
            raise RuntimeError("Embeddings not enabled")
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'")
            if not cur.fetchone():
                if HTTPException is not Exception:
                    raise HTTPException(status_code=400, detail="Embeddings table missing; run embed step")  # type: ignore
                raise RuntimeError("Embeddings table missing")
            cur.execute("SELECT section_rowid, vector FROM embeddings")
            rows = cur.fetchall()
            if not rows:
                if HTTPException is not Exception:
                    raise HTTPException(status_code=400, detail="No embeddings present")  # type: ignore
                raise RuntimeError("No embeddings present")
            first = rows[0][1]
            length = int(len(first)/4)
            import struct
            unpack_fmt = f'{length}f'
            stored = [(rid, struct.unpack(unpack_fmt, blob)) for rid, blob in rows]
            model = SentenceTransformer('all-MiniLM-L6-v2')
            qv = model.encode([q], normalize_embeddings=True)[0]
            scores = []
            for rid, vec in stored:
                sim = sum(a*b for a,b in zip(qv, vec))
                scores.append((sim, rid))
            scores.sort(reverse=True)
            out = []
            for sim, rid in scores[:limit]:
                cur.execute("SELECT rowid, title, part, section, heading FROM sections WHERE rowid=?", (rid,))
                srow = cur.fetchone()
                if srow:
                    out.append({'score': sim, 'rowid': srow[0], 'title': srow[1], 'part': srow[2], 'section': srow[3], 'heading': srow[4]})
            return out
        finally:
            conn.close()

    # Attempt analyzer router mount
    if analyzer_db is None:
        candidate = Path(db_path).parent / 'analyzer.sqlite'
        if candidate.exists():
            analyzer_db = str(candidate)
    if analyzer_db:
        try:  # pragma: no cover
            from .analyzer.api import router as analyzer_router
            app.include_router(analyzer_router)
        except Exception:
            pass

    return app

__all__ = ["create_app"]
