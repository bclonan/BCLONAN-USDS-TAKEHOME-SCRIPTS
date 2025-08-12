"""Validate eCFR XML files for structural and textual anomalies.

Usage (PowerShell):
  python scripts/validate_xml.py "data/title*.xml" > validation_report.json
"""
from __future__ import annotations

import sys
import re
import json
import hashlib
from pathlib import Path
from typing import List

try:
    from lxml import etree  # type: ignore
except ImportError:  # pragma: no cover
    print("lxml is required: pip install lxml", file=sys.stderr)
    sys.exit(2)

WS_MULTI = re.compile(r"[ \t]{2,}")
TRUNC_WORD = re.compile(r"\b[a-zA-Z]\s+[a-z]")
SECTION_HEAD = re.compile(r"^§\s*\d+(\.\d+)?")

TEXT_SAMPLE_LIMIT = 5


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def normalize_text(t: str) -> str:
    t = t.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    t = WS_MULTI.sub(" ", t)
    return t.strip()


def validate_file(path: Path) -> dict:
    raw = path.read_bytes()
    report: dict = {
        "file": path.name,
        "size": len(raw),
        "sha256": sha256_bytes(raw),
        "errors": [],
        "warnings": [],
        "stats": {},
    }
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError as e:
        report["errors"].append(f"XMLSyntaxError: {e}")
        return report

    header = root.find(".//HEADER")
    if header is None:
        report["errors"].append("Missing HEADER element")
    else:
        idno = header.find(".//IDNO")
        if idno is not None and idno.text:
            digits_in_filename = re.findall(r"\d+", path.stem)
            if digits_in_filename:
                if idno.text.strip() != digits_in_filename[0]:
                    report["warnings"].append(
                        f"IDNO {idno.text.strip()} != filename number {digits_in_filename[0]}"
                    )

    # Node id uniqueness
    nodes = root.xpath('//*[@NODE]')
    node_ids = [n.get("NODE") for n in nodes]
    dupes = sorted({nid for nid in node_ids if node_ids.count(nid) > 1})
    if dupes:
        report["warnings"].append(f"Duplicate NODE values: {dupes[:10]}")

    # Section head format
    bad_heads: List[str] = []
    for s in root.findall(".//DIV8"):
        head = s.find("./HEAD")
        if head is not None and head.text:
            txt = normalize_text(head.text)
            if txt.startswith("§") and not SECTION_HEAD.match(txt):
                bad_heads.append(txt)
    if bad_heads:
        report["warnings"].append(
            f"{len(bad_heads)} irregular section heads (sample {bad_heads[:TEXT_SAMPLE_LIMIT]})"
        )

    # Suspicious truncated words
    suspicious: List[str] = []
    for p in root.findall(".//P"):
        txt = normalize_text("".join(p.itertext()))
        if TRUNC_WORD.search(txt):
            suspicious.append(txt[:80])
            if len(suspicious) >= TEXT_SAMPLE_LIMIT:
                break
    if suspicious:
        report["warnings"].append(f"Possible truncations (sample {suspicious})")

    # Non-ascii sample
    all_text = "".join(root.itertext())
    non_ascii = sorted({c for c in all_text if ord(c) > 127})
    report["stats"]["non_ascii_sample"] = non_ascii[:20]

    # Empty metadata tags
    empty_tags = []
    for tag in ["AUTHOR", "PUBLISHER", "PUBPLACE", "DATE", "TITLE"]:
        for el in root.findall(f".//{tag}"):
            if not el.text or not el.text.strip():
                empty_tags.append(tag)
    if empty_tags:
        report["warnings"].append(f"Empty metadata tags: {sorted(set(empty_tags))}")

    # Basic counts
    report["stats"]["sections"] = len(root.findall('.//DIV8'))
    report["stats"]["div_nodes"] = len(nodes)

    return report


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else "data/title*.xml"
    paths = [p for p in Path('.').glob(pattern) if p.is_file()]
    reports = [validate_file(p) for p in paths]
    print(json.dumps(reports, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
