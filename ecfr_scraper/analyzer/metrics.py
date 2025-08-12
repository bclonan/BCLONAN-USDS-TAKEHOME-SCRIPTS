"""Primitive metrics computations for analyzer.

Each metric currently uses simple heuristic logic; can be replaced with
more sophisticated algorithms later.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
import re

# Simple regex for CFR citations inside section text (placeholder)
CFR_CITATION = re.compile(r"\b\d+\s+CFR\s+\d+(?:\.\d+)?")
EXTERNAL_REF = re.compile(r"\b(U\.S\.C\.|Stat\.|Pub\. L\.)")


def compute_metrics(conn: sqlite3.Connection) -> int:
    c = conn.cursor()
    c.execute("SELECT rowid, text, paragraph_count, word_count FROM sections")
    rows = c.fetchall()
    now = datetime.utcnow().isoformat() + "Z"
    updated = 0
    for rowid, text, pcount, wcount in rows:
        if not text:
            text = ""
        words = wcount or len(text.split()) or 1
        # RRD: fraction of repeated words among top 20% tokens (very naive)
        tokens = [t.lower() for t in re.findall(r"[A-Za-z]+", text)]
        if tokens:
            freq = {}
            for t in tokens:
                freq[t] = freq.get(t, 0) + 1
            sorted_counts = sorted(freq.values(), reverse=True)
            top_k = max(1, len(sorted_counts) // 5)
            repeat_total = sum(c for c in sorted_counts[:top_k])
            rrd = repeat_total / words
        else:
            rrd = 0.0
        # CCI: citation density per 1000 words
        cci = (len(CFR_CITATION.findall(text)) / words) * 1000 if words else 0.0
        # ERI: external reference density per 1000 words
        eri = (len(EXTERNAL_REF.findall(text)) / words) * 1000 if words else 0.0
        # PBI: paragraph break index (#paragraphs per 1000 words)
        pbi = (pcount / words) * 1000 if words else 0.0
        # AMR: placeholder always 0 until amendment metadata integrated
        amr = 0.0
        # FLI: fragmentation index = paragraphs / max(1, log2(words)) simplified
        import math
        fli = pcount / max(1.0, math.log2(words))
        # RSR: revision stability ratio placeholder 1 (no history yet)
        rsr = 1.0
        c.execute(
            "INSERT OR REPLACE INTO metrics(section_rowid, rrd, cci, eri, pbi, amr, fli, rsr, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (rowid, rrd, cci, eri, pbi, amr, fli, rsr, now),
        )
        updated += 1
    conn.commit()
    return updated


__all__ = ["compute_metrics"]
