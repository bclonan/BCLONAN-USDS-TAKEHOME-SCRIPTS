"""Ingest normalized per-section JSON artifacts into extended analyzer DB.

Reads files under output_dir/sections/titleX/*.json produced by normalization.
Populates sections, paragraphs, references (CFR/USC/FR/EO/PubL).
"""
from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from typing import Iterable, Tuple
from . import schema
import re, time, hashlib


def iter_section_files(sections_root: Path) -> Iterable[Path]:
    return sections_root.rglob("*.json")

CFR_REF_RE = re.compile(r"\b(\d+)\s*CFR\s*§?\s*([\d\.]+[a-z\-]*)|\b§\s*([\d\.]+[a-z\-]*)", re.I)
USC_REF_RE = re.compile(r"\b(\d+)\s*U\.S\.C\.\s*§?\s*([\w\.\-\(\)]+)", re.I)
FR_REF_RE  = re.compile(r"\b\d+\s+FR\s+\d+\b")
EO_REF_RE  = re.compile(r"\bE\.?.?O\.?.?\s*\d{4,}\b", re.I)
PUBL_RE    = re.compile(r"\bPub\.\s*L\.\s*\d+\-\d+\b", re.I)
RESERVED_RE = re.compile(r"\[RESERVED\]", re.I)
DEFS_RE = re.compile(r"\bDefinitions\b", re.I)

def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def extract_refs(text: str):
    out: list[Tuple[str,str,str]] = []
    for m in CFR_REF_RE.finditer(text):
        raw = m.group(0)
        sec = m.group(2) or m.group(3)
        if sec:
            out.append(("CFR", raw, sec))
    for m in USC_REF_RE.finditer(text):
        out.append(("USC", m.group(0), f"{m.group(1)} USC {m.group(2)}"))
    for m in FR_REF_RE.finditer(text):
        out.append(("FR", m.group(0), m.group(0)))
    for m in EO_REF_RE.finditer(text):
        out.append(("EO", m.group(0), m.group(0).upper().replace(' ', '').replace('.', '')))
    for m in PUBL_RE.finditer(text):
        out.append(("PubL", m.group(0), m.group(0)))
    return out


def ingest_sections(sections_root: Path, db_path: Path, replace: bool = False, changed_only: bool=False) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        schema.ensure_schema(conn)
        if replace:
            schema.clear_tables(conn)
        c = conn.cursor()
        count = 0
        for sf in iter_section_files(sections_root):
            try:
                data = json.loads(sf.read_text(encoding='utf-8'))
            except Exception:
                continue
            uid = data.get('anchor_id') or sf.stem
            heading = data.get('section_name') or data.get('heading') or ''
            paras = data.get('paragraphs') or []
            text = "\n".join(p.get('text','') for p in paras) or data.get('content') or ''
            text_norm = text.strip()
            chash = hashlib.sha256(text_norm.encode('utf-8')).hexdigest()
            title = data.get('title_number') or data.get('title') or 0
            part = data.get('part_number') or data.get('part')
            section = data.get('section_number') or data.get('section')
            is_reserved = 1 if RESERVED_RE.search(heading) else 0
            is_definition = 1 if DEFS_RE.search(heading) else 0
            if changed_only:
                prev = c.execute("SELECT chash FROM sections WHERE uid=?", (uid,)).fetchone()
                if prev and prev[0] == chash:
                    continue
            paragraph_count = len(paras)
            wc = len(text_norm.split())
            now = _now()
            c.execute("""INSERT OR REPLACE INTO sections(uid,title,part,section,heading,text_norm,word_count,paragraph_count,amend_date,is_reserved,is_definition,chash,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,COALESCE((SELECT created_at FROM sections WHERE uid=?),?),?)""",
                      (uid,title,part,section,heading,text_norm,wc,paragraph_count,None,is_reserved,is_definition,chash,now,now,uid,now,now))
            # paragraphs
            c.execute("DELETE FROM paragraphs WHERE section_uid=?", (uid,))
            for idx, p in enumerate(paras):
                p_txt = (p.get('text') or '').strip()
                p_hash = hashlib.sha256(p_txt.encode('utf-8')).hexdigest()
                c.execute("INSERT INTO paragraphs(section_uid, idx, text_norm, word_count, chash) VALUES (?,?,?,?,?)",
                          (uid, idx, p_txt, len(p_txt.split()), p_hash))
            # references
            c.execute("DELETE FROM references WHERE from_section_uid=?", (uid,))
            for r_type, raw, target in extract_refs(text_norm):
                c.execute("INSERT INTO references(from_section_uid, ref_type, raw, norm_target) VALUES (?,?,?,?)",
                          (uid, r_type, raw, target))
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


__all__ = ["ingest_sections", "extract_refs"]
