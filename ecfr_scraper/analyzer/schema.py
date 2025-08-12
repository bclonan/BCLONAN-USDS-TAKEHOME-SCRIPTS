"""Extended analyzer schema.

Adds richer tables for sections, paragraphs, references, per-section metrics,
per-part rollups, and part hashes for change detection.
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sections(
    uid TEXT PRIMARY KEY,
    title INTEGER,
    part TEXT,
    section TEXT,
    heading TEXT,
    text_norm TEXT,
    word_count INTEGER,
    paragraph_count INTEGER,
    amend_date TEXT,
    is_reserved INTEGER,
    is_definition INTEGER,
    chash TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS paragraphs(
    section_uid TEXT,
    idx INTEGER,
    text_norm TEXT,
    word_count INTEGER,
    chash TEXT,
    PRIMARY KEY(section_uid, idx)
);

CREATE TABLE IF NOT EXISTS references(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_section_uid TEXT,
    ref_type TEXT,
    raw TEXT,
    norm_target TEXT
);

CREATE TABLE IF NOT EXISTS metrics_section(
    section_uid TEXT PRIMARY KEY,
    rrd REAL, cci REAL, eri REAL, dor REAL, pbi REAL, amr REAL, fli REAL,
    rap REAL, hvi REAL, rsr REAL, crnc REAL, drs REAL, soi REAL, fk_grade REAL,
    wc INTEGER, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS metrics_part(
    title INTEGER,
    part TEXT,
    key TEXT,
    value REAL,
    PRIMARY KEY(title, part, key)
);

CREATE TABLE IF NOT EXISTS part_hash(
    title INTEGER,
    part TEXT,
    chash TEXT,
    PRIMARY KEY(title, part)
);

CREATE INDEX IF NOT EXISTS idx_sections_part ON sections(title, part);
CREATE INDEX IF NOT EXISTS idx_refs_target ON references(norm_target);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def clear_tables(conn: sqlite3.Connection) -> None:
    c = conn.cursor()
    for tbl in ["sections","paragraphs","references","metrics_section","metrics_part","part_hash"]:
        c.execute(f"DELETE FROM {tbl}")
    conn.commit()


__all__ = ["ensure_schema", "clear_tables", "SCHEMA"]
