"""Minify ECFR XML while preserving semantics.

Conservative by default: removes indentation, blank text nodes, comments.
Optional flags:
  --aggressive   collapse multiple internal spaces in text nodes
  --drop-empty   remove empty metadata elements (AUTHOR, PUBLISHER, PUBPLACE, DATE, TITLE, KEYWORDS)

Usage (PowerShell):
  python scripts/minify_ecfr_xml.py data --aggressive --drop-empty
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

from lxml import etree  # type: ignore

TEXT_ELEMENTS = {
    "HEAD","P","PG","CITA","AUTH","SOURCE","HED","PSPACE",
    "FP-1","HD2","HD3","EXTRACT","SUBJECT","EDNOTE","IDNO","AMDDATE"
}
EMPTY_METADATA = {"AUTHOR","PUBLISHER","PUBPLACE","DATE","TITLE","KEYWORDS"}

WS_MULTI = re.compile(r'[ \t]+')
MULTI_SPACES = re.compile(r' {2,}')


def normalize_text(t: str, aggressive: bool) -> str | None:
    if t is None:
        return None
    t = t.replace('\r',' ').replace('\n',' ').replace('\t',' ')
    t = WS_MULTI.sub(' ', t)
    if aggressive:
        t = MULTI_SPACES.sub(' ', t)
    t = t.strip()
    return t or None


def process_element(el: etree._Element, aggressive: bool) -> None:
    # Recurse first
    for child in list(el):
        if isinstance(child, (etree._Comment, etree._ProcessingInstruction)):
            el.remove(child)
        else:
            process_element(child, aggressive)
    # Strip whitespace-only text/tail
    if el.text and el.text.strip() == '':
        el.text = None
    if el.tail and el.tail.strip() == '':
        el.tail = None
    # Normalize text
    if el.tag in TEXT_ELEMENTS and el.text:
        el.text = normalize_text(el.text, aggressive)
    # Tail: reduce indentation to single space if meaningful
    if el.tail:
        el.tail = ' ' if el.tail.strip() else None


def drop_empty_metadata(root: etree._Element) -> int:
    removed = 0
    for el in list(root.iter()):
        if el.tag in EMPTY_METADATA:
            if (el.text is None or el.text.strip() == '') and len(el) == 0:
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
                    removed += 1
    return removed


def minify_file(path: Path, out: Path, aggressive: bool, drop_empty: bool) -> tuple[int,int,int]:
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()
    process_element(root, aggressive)
    removed = drop_empty_metadata(root) if drop_empty else 0
    data = etree.tostring(
        root,
        encoding='UTF-8',
        xml_declaration=True,
        pretty_print=False,
    )
    out.write_bytes(data)
    return path.stat().st_size, out.stat().st_size, removed


def iter_input(xml_input: Path) -> Iterable[Path]:
    if xml_input.is_dir():
        yield from sorted(xml_input.glob('*.xml'))
    else:
        yield xml_input


def main():
    ap = argparse.ArgumentParser(description="Minify ECFR XML files")
    ap.add_argument('input', help='XML file or directory')
    ap.add_argument('-o','--output', help='Output file/dir (default: in-place *.min.xml or same dir)')
    ap.add_argument('--aggressive', action='store_true', help='Collapse multiple internal spaces')
    ap.add_argument('--drop-empty', action='store_true', help='Remove empty metadata elements')
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        raise SystemExit(f"Input path not found: {in_path}")

    total_before = total_after = total_removed = 0
    if in_path.is_dir():
        out_dir = Path(args.output) if args.output else in_path
        out_dir.mkdir(parents=True, exist_ok=True)
        for xml_file in iter_input(in_path):
            out_file = out_dir / (xml_file.stem + '.min.xml')
            before, after, removed = minify_file(xml_file, out_file, args.aggressive, args.drop_empty)
            total_before += before; total_after += after; total_removed += removed
            pct = (1 - after / before) * 100 if before else 0
            print(f"{xml_file.name}: {before/1024:.1f}KB -> {after/1024:.1f}KB ({pct:.1f}% saved) removed={removed}")
        overall = (1 - total_after / total_before) * 100 if total_before else 0
        print(f"TOTAL: {total_before/1024:.1f}KB -> {total_after/1024:.1f}KB ({overall:.1f}% saved) empty_removed={total_removed}")
    else:
        out_file = Path(args.output) if args.output else in_path.with_suffix('.min.xml')
        before, after, removed = minify_file(in_path, out_file, args.aggressive, args.drop_empty)
        pct = (1 - after / before) * 100 if before else 0
        print(f"{in_path.name}: {before/1024:.1f}KB -> {after/1024:.1f}KB ({pct:.1f}% saved) removed={removed} -> {out_file}")

if __name__ == '__main__':
    main()
