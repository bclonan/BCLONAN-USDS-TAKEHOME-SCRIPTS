"""Extended analyzer API router.

Provides section + part metrics, reference search, and change listing.
Relies on environment variable ECFR_ANALYZER_DB to locate analyzer.sqlite.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
import os, sqlite3

router = APIRouter(prefix="/analyzer", tags=["analyzer"])

DB_ENV = "ECFR_ANALYZER_DB"

def _connect():
    db = os.getenv(DB_ENV)
    if not db or not os.path.exists(db):
        raise HTTPException(500, detail="Analyzer DB not configured")
    return sqlite3.connect(db)

@router.get("/section/{uid}")
def section(uid: str):  # type: ignore
    conn = _connect()
    try:
        c = conn.cursor()
        row = c.execute("SELECT uid,title,part,section,heading,word_count,paragraph_count FROM sections WHERE uid=?", (uid,)).fetchone()
        if not row:
            raise HTTPException(404, detail="Not found")
        m = c.execute("SELECT wc,paragraphs,sentences,eri,dor,amr,fli,hvi,drs,soi,fk_grade FROM metrics_section WHERE section_uid=?", (uid,)).fetchone()
        metrics = None
        if m:
            metrics = {'wc': m[0],'paragraphs': m[1],'sentences': m[2],'eri': m[3],'dor': m[4],'amr': m[5],'fli': m[6],'hvi': m[7],'drs': m[8],'soi': m[9],'fk_grade': m[10]}
        return {'uid': row[0], 'title': row[1], 'part': row[2], 'section': row[3], 'heading': row[4], 'word_count': row[5], 'paragraph_count': row[6], 'metrics': metrics}
    finally:
        conn.close()

@router.get("/parts")
def parts(title: int | None = None):  # type: ignore
    conn = _connect()
    try:
        c = conn.cursor()
        if title is not None:
            rows = c.execute("SELECT DISTINCT title,part FROM sections WHERE title=? AND part IS NOT NULL ORDER BY part", (title,)).fetchall()
        else:
            rows = c.execute("SELECT DISTINCT title,part FROM sections WHERE part IS NOT NULL ORDER BY title, part").fetchall()
        return [{'title': r[0], 'part': r[1]} for r in rows]
    finally:
        conn.close()

@router.get("/parts/{title}/{part}")
def part_metrics(title: int, part: str):  # type: ignore
    conn = _connect()
    try:
        c = conn.cursor()
        row = c.execute("SELECT title,part,wc,paragraphs,sentences,eri,dor,amr,fli,hvi,drs,soi,fk_grade FROM metrics_part WHERE title=? AND part=?", (title,part)).fetchone()
        if not row:
            raise HTTPException(404, detail="Part metrics not found")
        return {'title': row[0], 'part': row[1], 'wc': row[2], 'paragraphs': row[3], 'sentences': row[4], 'eri': row[5], 'dor': row[6], 'amr': row[7], 'fli': row[8], 'hvi': row[9], 'drs': row[10], 'soi': row[11], 'fk_grade': row[12]}
    finally:
        conn.close()

@router.get("/search/refs")
def search_refs(q: str = Query(..., description="Reference substring"), limit: int = 25):  # type: ignore
    conn = _connect()
    try:
        c = conn.cursor()
        like = f"%{q}%"
        rows = c.execute("""SELECT ref_type, raw, norm_target, COUNT(*) as freq FROM references
                           WHERE raw LIKE ? OR norm_target LIKE ?
                           GROUP BY ref_type, raw, norm_target
                           ORDER BY freq DESC
                           LIMIT ?""", (like, like, limit)).fetchall()
        return [{'type': r[0], 'raw': r[1], 'target': r[2], 'count': r[3]} for r in rows]
    finally:
        conn.close()

@router.get("/changes")
def changes(limit: int = 50):  # type: ignore
    conn = _connect()
    try:
        c = conn.cursor()
        rows = c.execute("SELECT uid,title,part,section,heading,updated_at FROM sections ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [{'uid': r[0],'title': r[1],'part': r[2],'section': r[3],'heading': r[4],'updated_at': r[5]} for r in rows]
    finally:
        conn.close()

__all__ = ["router"]
