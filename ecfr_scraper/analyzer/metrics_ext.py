"""Extended metrics computation for analyzer.

Populates metrics_section and metrics_part. Some metrics are placeholders that
require longitudinal or graph context not yet available; these are stored as NULL.
"""
from __future__ import annotations
import sqlite3, math, statistics, re
from typing import Dict, Any, Iterable

OBLIGATION_PAT = re.compile(r"\b(shall|must|may not|prohibited|required|shall not)\b", re.I)
PROHIBITIVE_PAT = re.compile(r"\b(may not|shall not|prohibited|ban|forbidden)\b", re.I)
AMBIGUOUS_PAT = re.compile(r"\b(reasonable|adequate|appropriate|sufficient|timely)\b", re.I)
FEASIBILITY_PAT = re.compile(r"\b(feasible|practicable|possible)\b", re.I)
RISK_PAT = re.compile(r"\b(risk|hazard|exposure|threat)\b", re.I)
SMALL_ENTITY_PAT = re.compile(r"\b(small entity|small business|micro entity)\b", re.I)

def flesch_kincaid_grade(text: str) -> float | None:
    words = re.findall(r"[A-Za-z]+", text)
    if not words:
        return None
    sentences = re.split(r"[.!?]+", text)
    sentences = [s for s in sentences if s.strip()]
    if not sentences:
        return None
    # naive syllable count
    def syl(w: str) -> int:
        w = w.lower()
        # very naive: groups of vowels
        parts = re.findall(r"[aeiouy]+", w)
        return max(1, len(parts))
    syllables = sum(syl(w) for w in words)
    W = len(words)
    S = len(sentences)
    return 0.39 * (W / S) + 11.8 * (syllables / W) - 15.59

def compute_section_metrics(conn: sqlite3.Connection, limit: int | None = None):
    c = conn.cursor()
    # fetch sections needing metrics (no row in metrics_section or chash changed)
    rows = c.execute("""
        SELECT s.uid,s.text_norm,s.word_count,s.paragraph_count,s.chash
        FROM sections s
        LEFT JOIN metrics_section m ON m.section_uid = s.uid AND m.chash = s.chash
        WHERE m.section_uid IS NULL
        ORDER BY s.uid
        LIMIT ?
    """, (limit if limit else -1,)).fetchall()
    for uid, text, wc, pc, chash in rows:
        words = wc or 0
        paragraphs = pc or 0
        sentences = len([s for s in re.split(r"[.!?]+", text) if s.strip()]) if text else 0
        # basic metrics
        rrd = sentences / paragraphs if paragraphs else None  # regulation readability density (proxy)
        cci = paragraphs / words if words else None  # complexity compression index (proxy)
        eri = len(OBLIGATION_PAT.findall(text)) / sentences if sentences else None
        dor = len(PROHIBITIVE_PAT.findall(text)) / sentences if sentences else None
        pbi = len(PROHIBITIVE_PAT.findall(text)) / (len(OBLIGATION_PAT.findall(text)) + 1)
        amr = len(AMBIGUOUS_PAT.findall(text)) / words if words else None
        fli = len(FEASIBILITY_PAT.findall(text)) / sentences if sentences else None
        rap = None  # requires amendment history
        hvi = len(RISK_PAT.findall(text)) / sentences if sentences else None
        rsr = None  # regulatory scope reach requires cross title graph
        crnc = None # cross reference network centrality requires graph build
        drs = len(SMALL_ENTITY_PAT.findall(text)) / words if words else None
        soi = len(OBLIGATION_PAT.findall(text)) / words if words else None
        fk_grade = flesch_kincaid_grade(text)
        c.execute("""INSERT OR REPLACE INTO metrics_section(
                    section_uid,chash,wc,paragraphs,sentences,rrd,cci,eri,dor,pbi,amr,fli,rap,hvi,rsr,crnc,drs,soi,fk_grade
                  ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (uid,chash,words,paragraphs,sentences,rrd,cci,eri,dor,pbi,amr,fli,rap,hvi,rsr,crnc,drs,soi,fk_grade))
    conn.commit()

def compute_part_metrics(conn: sqlite3.Connection):
    c = conn.cursor()
    # aggregate per part
    parts = c.execute("""SELECT title,part FROM sections WHERE part IS NOT NULL GROUP BY title,part""").fetchall()
    for title, part in parts:
        sec_rows = c.execute("""SELECT m.wc,m.paragraphs,m.sentences,m.eri,m.dor,m.amr,m.fli,m.hvi,m.drs,m.soi,m.fk_grade
                                FROM metrics_section m JOIN sections s ON s.uid=m.section_uid
                                WHERE s.title=? AND s.part=?""", (title,part)).fetchall()
        if not sec_rows:
            continue
        def avg(idx):
            vals = [r[idx] for r in sec_rows if r[idx] is not None]
            return sum(vals)/len(vals) if vals else None
        wc_total = sum(r[0] or 0 for r in sec_rows)
        paragraphs_total = sum(r[1] or 0 for r in sec_rows)
        sentences_total = sum(r[2] or 0 for r in sec_rows)
        eri_avg = avg(3)
        dor_avg = avg(4)
        amr_avg = avg(5)
        fli_avg = avg(6)
        hvi_avg = avg(7)
        drs_avg = avg(8)
        soi_avg = avg(9)
        fk_avg = avg(10)
        c.execute("""INSERT OR REPLACE INTO metrics_part(title,part,wc,paragraphs,sentences,eri,dor,amr,fli,hvi,drs,soi,fk_grade)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (title,part,wc_total,paragraphs_total,sentences_total,eri_avg,dor_avg,amr_avg,fli_avg,hvi_avg,drs_avg,soi_avg,fk_avg))
    conn.commit()

__all__ = ["compute_section_metrics","compute_part_metrics"]
