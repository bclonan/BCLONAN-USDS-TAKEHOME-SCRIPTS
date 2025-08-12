"""Simple pluggable pipeline for chaining scraper operations.

Steps are lightweight callables that accept a context dict and mutate it.
Users select steps via CLI: --chain download,parse,export

Context keys:
  titles: list[int]
  xml_files: list[str]
  parsed: list[dict]

New steps can be added by registering in STEP_REGISTRY.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Any, Optional
import gzip
import json
from pathlib import Path
from datetime import datetime
import logging

from .scraper import ECFRScraper
from .utils import calculate_checksum, load_checksum_db, save_checksum_db

# Decorator-based registration -------------------------------------------------
STEP_REGISTRY: Dict[str, "StepFunc"] = {}

def pipeline_step(name: Optional[str] = None):
    """Decorator to register a pipeline step.

    Usage:
        @pipeline_step()
        def step_foo(ctx): ...
    or   @pipeline_step("custom_name")
    """
    def wrapper(func: StepFunc):
        key = name or func.__name__.removeprefix("step_")
        STEP_REGISTRY[key] = func
        return func
    return wrapper

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    scraper: ECFRScraper
    titles: List[int] = field(default_factory=list)
    xml_files: List[str] = field(default_factory=list)
    parsed: List[dict] = field(default_factory=list)


StepFunc = Callable[[PipelineContext], None]


@pipeline_step()
def download(ctx: PipelineContext) -> None:
    if not ctx.titles:
        logger.error("No titles specified for download step.")
        return
    xml_files: List[str] = []
    for t in ctx.titles:
        path = ctx.scraper.download_title_xml(t)
        if path:
            xml_files.append(path)
    ctx.xml_files.extend(xml_files)
    logger.info("Download step complete: %d files", len(xml_files))


@pipeline_step()
def parse(ctx: PipelineContext) -> None:
    if not ctx.xml_files:
        logger.warning("No XML files available to parse. Skipping parse step.")
        return
    for path in ctx.xml_files:
        data = ctx.scraper.parse_xml(path)
        if data:
            ctx.parsed.append({"path": path, "data": data})
    logger.info("Parse step complete: %d parsed documents", len(ctx.parsed))


@pipeline_step()
def export(ctx: PipelineContext) -> None:
    if not ctx.parsed:
        logger.warning("No parsed data to export. Skipping export step.")
        return
    exported = 0
    for item in ctx.parsed:
        xml_path = item["path"]
        json_path = xml_path.replace(".xml", ".json")
        if ctx.scraper.export_to_json(item["data"], json_path):
            exported += 1
    logger.info("Export step complete: %d JSON files", exported)


# Additional steps -------------------------------------------------------------

@pipeline_step()
def minify(ctx: PipelineContext) -> None:
    """Minify downloaded XML (produces *.min.xml) using whitespace/comment stripping.
    Simple inline implementation to avoid external deps beyond stdlib.
    """
    import xml.etree.ElementTree as ET
    count = 0
    for xml_path in list(ctx.xml_files):
        if not xml_path.endswith('.xml'):
            continue
        min_path = xml_path.replace('.xml', '.min.xml')
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            # Remove blank text nodes (ElementTree already collapses formatting)
            # Strip leading/trailing whitespace in text
            for el in root.iter():
                if el.text:
                    t = el.text.strip()
                    el.text = t if t else None
                if el.tail:
                    tail = el.tail.strip()
                    el.tail = tail if tail else None
            ET.ElementTree(root).write(min_path, encoding='utf-8', xml_declaration=True, method='xml')
            count += 1
        except Exception as e:  # pragma: no cover
            logger.error("Minify failed for %s: %s", xml_path, e)
    logger.info("Minify step complete: %d files", count)

@pipeline_step()
def gzipxml(ctx: PipelineContext) -> None:
    """Gzip minified XML files (*.min.xml -> *.xml.gz) and build manifest."""
    manifest = []
    for xml_path in ctx.xml_files:
        min_path = xml_path.replace('.xml', '.min.xml')
        src = Path(min_path if Path(min_path).exists() else xml_path)
        if not src.exists():
            continue
        gz_path = src.with_suffix(src.suffix + '.gz')
        try:
            data = src.read_bytes()
            with gzip.open(gz_path, 'wb', compresslevel=9) as fh:
                fh.write(data)
            manifest.append({
                'file': gz_path.name,
                'size': gz_path.stat().st_size,
                'checksum': calculate_checksum(file_path=str(gz_path)),
            })
        except Exception as e:  # pragma: no cover
            logger.error("Gzip failed for %s: %s", src, e)
    # Write manifest
    if ctx.scraper.output_dir:
        manifest_path = Path(ctx.scraper.output_dir) / 'manifest.json'
        manifest_doc = {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'files': sorted(manifest, key=lambda m: m['file'])
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_doc, f, indent=2)
        logger.info("Wrote manifest with %d entries", len(manifest))

@pipeline_step()
def diff(ctx: PipelineContext) -> None:
    """Reduce ctx.xml_files to only changed XML based on checksum comparison.
    Compares current checksum_db (already updated by downloads) to saved on disk.
    """
    previous = load_checksum_db()
    changed = []
    for path in ctx.xml_files:
        fname = Path(path).name
        current_hash = ctx.scraper.checksum_db.get(fname)
        prev_hash = previous.get(fname)
        if current_hash != prev_hash:
            changed.append(path)
    ctx.xml_files = changed
    logger.info("Diff step: %d changed files retained", len(changed))


def run_pipeline(scraper: ECFRScraper, steps: List[str], titles: List[int]) -> PipelineContext:
    ctx = PipelineContext(scraper=scraper, titles=titles)
    for name in steps:
        func = STEP_REGISTRY.get(name)
        if not func:
            logger.error("Unknown step '%s'", name)
            continue
        logger.info("Running step: %s", name)
        func(ctx)
    return ctx
