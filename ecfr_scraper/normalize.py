"""Normalization & enrichment utilities for eCFR section data.

Functions here operate on exported title JSON (post `export` step) to:
  * Extract canonical section_number & short_title from legacy heading
  * Normalize whitespace and structure paragraphs & enumerations
  * Extract Federal Register amendment history & FR citations
  * Extract CFR cross-citations ("12 CFR 1026.4" etc.)
  * Produce per-section JSON artifacts (idempotent + cached)
  * Support HTML / Markdown rendering of sections

Caching: normalization_cache.json keyed by anchor_id -> sha256(content) so
repeated runs skip unchanged sections.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import re
import json
import hashlib
from datetime import datetime

HEAD_RE = re.compile(r"^(§\s*(?P<num>[0-9][0-9A-Za-z.\-]*))\s+(?P<title>.+?)\s*$")
FR_BLOCK_RE = re.compile(r"\[(?P<block>[^\]]+?)\]\s*$")
FR_CIT_RE = re.compile(r"(?P<cite>\d+\s+FR\s+\d+)")
DATE_FULL_RE = re.compile(r"(Jan\.|Feb\.|Mar\.|Apr\.|May|Jun\.|Jul\.|Aug\.|Sep\.|Oct\.|Nov\.|Dec\.)\s+\d{1,2},\s+\d{4}")
CFR_CIT_RE = re.compile(r"\b(\d+)\s+CFR\s+(\d+(?:\.\d+)*)")

PARA_SPLIT_RE = re.compile(r"\n\s*\n+", re.MULTILINE)

CACHE_FILENAME = "normalization_cache.json"

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_cache(base: Path) -> Dict[str, str]:
    p = base / CACHE_FILENAME
    if p.exists():
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            return {}
    return {}

def save_cache(base: Path, cache: Dict[str, str]) -> None:
    (base / CACHE_FILENAME).write_text(json.dumps(cache, indent=2), encoding='utf-8')

def _clean_ws(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s.strip())

def extract_heading(section_name: str) -> Dict[str, Optional[str]]:
    m = HEAD_RE.match(section_name.strip())
    if not m:
        return {
            "citation_raw": None,
            "section_number": None,
            "short_title": section_name.strip(),
        }
    title = m.group('title').strip()
    return {
        "citation_raw": m.group(1),
        "section_number": m.group('num'),
        "short_title": title,
    }

def extract_fr_history(content: str) -> Dict[str, Any]:
    out = {"fr_citations": [], "amend_history": []}
    m = FR_BLOCK_RE.search(content)
    if not m:
        return out
    block = m.group('block')
    cites = FR_CIT_RE.findall(block)
    full_dates = DATE_FULL_RE.findall(block)
    out["fr_citations"] = cites
    for i, cite in enumerate(cites):
        date = full_dates[i] if i < len(full_dates) else None
        iso = None
        if date:
            try:
                iso = datetime.strptime(date.replace('.', ''), '%b %d, %Y').date().isoformat()
            except ValueError:
                iso = None
        out["amend_history"].append({"fr_citation": cite, "date": iso})
    return out

def extract_cfr_citations(text: str) -> List[str]:
    cites = []
    for m in CFR_CIT_RE.finditer(text):
        cites.append(f"{m.group(1)} CFR {m.group(2)}")
    return sorted(set(cites))

def split_paragraphs(content: str) -> List[Dict[str, Optional[str]]]:
    content_wo_fr = FR_BLOCK_RE.sub('', content).rstrip()
    raw_paras = PARA_SPLIT_RE.split(content_wo_fr)
    paras: List[Dict[str, Optional[str]]] = []
    for p in raw_paras:
        p = p.strip('\n')
        if not p.strip():
            continue
        first_line = p.splitlines()[0]
        label = None
        m = re.match(r"^\(([a-z0-9ivxlcdmIVXLCDM]+)\)", first_line)
        txt = p
        if m:
            label = f"({m.group(1)})"
            txt = p[len(m.group(0)):].lstrip()
        paras.append({"label": label, "text": _clean_ws(txt)})
    return paras

def build_enumerations(paras: List[Dict[str, Optional[str]]]) -> Dict[str, List[str]]:
    enums: Dict[str, List[str]] = {}
    current_top = None
    for p in paras:
        label = p.get("label")
        if label and re.match(r"^\([a-z]\)$", label):
            current_top = label
            continue
        if label and re.match(r"^\(\d+\)$", label) and current_top:
            enums.setdefault(current_top, []).append(f"{label} {p['text']}")
    return enums

def normalize_section(section: Dict[str, Any], title_number: Optional[str]) -> Dict[str, Any]:
    legacy_name = section.get("section_name") or ""
    heading_parts = extract_heading(legacy_name)
    content = section.get("content") or ""
    content_norm = content.replace('\r', '')
    paras = split_paragraphs(content_norm)
    enumerations = build_enumerations(paras)
    fr_hist = extract_fr_history(content_norm)
    cfr_citations = extract_cfr_citations(content_norm)
    section_number = heading_parts.get("section_number")
    anchor_id = f"title{title_number}-{section_number.replace('.', '-') if section_number else 'unknown'}"
    normalized = {
        **heading_parts,
        **fr_hist,
        "cfr_citations": cfr_citations,
        "paragraphs": paras,
        "enumerations": enumerations,
        "anchor_id": anchor_id,
        "section_name": legacy_name,
        "content": content_norm,
    }
    return normalized

def normalize_title_file(path: Path, output_dir: Optional[Path] = None, cache: Optional[Dict[str, str]] = None) -> int:
    data = json.loads(path.read_text(encoding='utf-8'))
    title_number = data.get('title_number') or path.stem.replace('title', '')
    out_base = (output_dir or path.parent)
    sections_dir = out_base / 'sections' / f'title{title_number}'
    sections_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    modified = False
    for part in data.get('parts', []):
        # Infer part_number if missing by scanning part_name like 'PART 10—...'
        if not part.get('part_number') and part.get('part_name'):
            m_p = re.search(r"PART\s+([0-9A-Za-z]+)", part['part_name'])
            if m_p:
                part['part_number'] = m_p.group(1)
                modified = True
        for section in part.get('sections', []):
            content = section.get('content') or ''
            legacy_name = section.get('section_name') or ''
            # Backfill section_number if null using heading pattern
            if not section.get('section_number') and legacy_name:
                m_s = re.match(r"§\s*([0-9][0-9A-Za-z.\-]*)", legacy_name)
                if m_s:
                    section['section_number'] = m_s.group(1)
                    modified = True
            norm = normalize_section(section, title_number)
            anchor = norm.get('anchor_id')
            payload_hash = _sha256(content + '|' + legacy_name)
            if cache is not None and anchor in cache and cache[anchor] == payload_hash:
                section.update(norm)
                continue
            section.update(norm)
            file_name = f"{(norm.get('section_number') or f'idx{count}').replace('.', '_')}.json"
            (sections_dir / file_name).write_text(json.dumps(norm, indent=2, ensure_ascii=False), encoding='utf-8')
            if cache is not None and anchor:
                cache[anchor] = payload_hash
            count += 1
            modified = True
    if modified:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return count

def render_section_html(section: Dict[str, Any]) -> str:
    title = section.get('section_name', '')
    body_parts = []
    for p in section.get('paragraphs', []):
        label = p.get('label')
        text = p.get('text')
        if label:
            body_parts.append(f"<p><strong>{label}</strong> {text}</p>")
        else:
            body_parts.append(f"<p>{text}</p>")
    return f"<article id='{section.get('anchor_id','')}'><h2>{title}</h2>\n" + "\n".join(body_parts) + "\n</article>"

def render_section_markdown(section: Dict[str, Any]) -> str:
    title = section.get('section_name', '')
    lines = [f"## {title}"]
    for p in section.get('paragraphs', []):
        label = p.get('label')
        text = p.get('text')
        if label:
            lines.append(f"**{label}** {text}")
        else:
            lines.append(text)
        lines.append('')
    return "\n".join(lines).strip() + "\n"
