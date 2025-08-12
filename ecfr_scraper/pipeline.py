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
import sqlite3
import os

from .scraper import ECFRScraper
from .utils import calculate_checksum, load_checksum_db, save_checksum_db
from . import normalize as norm
try:  # optional analyzer import
    from .analyzer import ingest as analyzer_ingest
    from .analyzer import metrics_ext as analyzer_metrics
except Exception:  # pragma: no cover
    analyzer_ingest = None  # type: ignore
    analyzer_metrics = None  # type: ignore

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
    enriched_sections: List[dict] = field(default_factory=list)
    db_path: Optional[str] = None
    paragraph_embeddings: bool = False
    analyzer_db: Optional[str] = None


StepFunc = Callable[[PipelineContext], None]
_EMBED_MODEL = None  # type: ignore


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
def manifest(ctx: PipelineContext) -> None:
    """Generate a unified artifact manifest (artifacts.json) including raw/minified/gzip + json.
    Differs from gzip manifest.json which only lists gz files.
    """
    if not ctx.xml_files:
        logger.warning("manifest step: no xml_files present")
    artifacts = []
    out_dir = Path(ctx.scraper.output_dir)
    for title_xml in ctx.xml_files:
        base = Path(title_xml).name
        stem = base.replace('.xml','')
        candidates = [
            out_dir / f"{stem}.xml",
            out_dir / f"{stem}.min.xml",
            out_dir / f"{stem}.min.xml.gz",
            out_dir / f"{stem}.xml.gz",
            out_dir / f"{stem}.json",
            out_dir / f"{stem}.xml.metadata.json",
        ]
        for c in candidates:
            if c.exists():
                artifacts.append({
                    'file': c.name,
                    'size': c.stat().st_size,
                    'checksum': calculate_checksum(file_path=str(c)),
                    'kind': 'artifact'
                })
    # Section artifacts
    sections_root = out_dir / 'sections'
    if sections_root.exists():
        for sec in sections_root.rglob('*.json'):
            artifacts.append({
                'file': str(sec.relative_to(out_dir)),
                'size': sec.stat().st_size,
                'checksum': calculate_checksum(file_path=str(sec)),
                'kind': 'section'
            })
    doc = {
        'schema_version': '1.0',
        'generated_at': datetime.utcnow().isoformat()+'Z',
        'artifacts': sorted(artifacts, key=lambda a: a['file'])
    }
    with open(out_dir / 'artifacts.json','w',encoding='utf-8') as f:
        json.dump(doc,f,indent=2)
    logger.info("Artifact manifest written: %d entries", len(artifacts))

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

@pipeline_step()
def enrich(ctx: PipelineContext) -> None:
    """Flatten parsed documents into section-level rows for search / index.
    Populates ctx.enriched_sections with dicts: title, part, section, heading, content, word_count.
    Requires parse step beforehand.
    """
    if not ctx.parsed:
        logger.warning("enrich step: parsed data empty; run parse before enrich")
        return
    rows = []
    for doc in ctx.parsed:
        pdata = doc['data']
        title_num = pdata.get('title_number')
        for part in pdata.get('parts', []):
            part_no = part.get('part_number')
            for section in part.get('sections', []):
                rows.append({
                    'title': title_num,
                    'part': part_no,
                    'section': section.get('section_number'),
                    'heading': section.get('section_name'),
                    'content': section.get('content'),
                    'word_count': section.get('word_count'),
                })
    ctx.enriched_sections = rows
    logger.info("Enrich step: %d section rows", len(rows))

@pipeline_step()
def normalize(ctx: PipelineContext) -> None:
    """Normalize title JSON files (add structured fields + per-section artifacts).
    Requires export step. Idempotent with caching.
    """
    out_dir = Path(ctx.scraper.output_dir)
    cache = norm.load_cache(out_dir)
    title_files = sorted(out_dir.glob('title*.json'))
    if not title_files:
        logger.warning("normalize step: no title JSON files found")
        return
    total_sections = 0
    for tf in title_files:
        try:
            total_sections += norm.normalize_title_file(tf, output_dir=out_dir, cache=cache)
        except Exception as e:  # pragma: no cover
            logger.error("Normalization failed for %s: %s", tf.name, e)
    norm.save_cache(out_dir, cache)
    logger.info("Normalize step complete: %d sections processed (cached may be skipped)", total_sections)

@pipeline_step()
def ftsindex(ctx: PipelineContext) -> None:
    """Build (or update) a SQLite FTS5 index from enriched sections.
    Produces ecfr_index.sqlite in output_dir; table: sections(title, part, section, heading, content, word_count).
    Requires enrich.
    """
    if not ctx.enriched_sections:
        logger.warning("ftsindex step: no enriched sections; run enrich first")
        return
    db_path = Path(ctx.scraper.output_dir) / 'ecfr_index.sqlite'
    ctx.db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS sections USING fts5(title, part, section, heading, content, word_count UNINDEXED)")
        c.execute("DELETE FROM sections")
        c.executemany(
            "INSERT INTO sections (title, part, section, heading, content, word_count) VALUES (?,?,?,?,?,?)",
            [(
                r['title'], r['part'], r['section'], r.get('heading'), r.get('content'), r.get('word_count')
            ) for r in ctx.enriched_sections]
        )
        conn.commit()
        logger.info("ftsindex step: indexed %d rows", len(ctx.enriched_sections))
    finally:
        conn.close()

@pipeline_step()
def embed(ctx: PipelineContext) -> None:  # pragma: no cover - optional heavy dep
    """Generate sentence-transformer embeddings for sections.

    Enhancements:
      * Model cached globally to avoid repeated load.
      * Environment overrides:
          ECFR_EMBED_MODEL  -> model name (default all-MiniLM-L6-v2)
          ECFR_EMBED_LIMIT  -> int limit of sections (for quick smoke runs)
          ECFR_EMBED_BATCH  -> batch size (default 32)
      * Chunked DB inserts + commit every 500 for lower memory pressure.
      * Graceful KeyboardInterrupt (partial progress kept).
    """
    import os
    try:
        from sentence_transformers import SentenceTransformer
        import struct
    except Exception as e:  # pragma: no cover
        logger.warning("embed step: sentence-transformers not available (%s)", e)
        return
    if not ctx.enriched_sections:
        logger.warning("embed step: requires enrich first")
        return
    if not ctx.db_path:
        logger.warning("embed step: requires ftsindex to create DB path")
        return

    global _EMBED_MODEL
    model_name = os.getenv('ECFR_EMBED_MODEL', 'all-MiniLM-L6-v2')
    if _EMBED_MODEL is None:
        logger.info("embed step: loading model %s", model_name)
        _EMBED_MODEL = SentenceTransformer(model_name)
    model = _EMBED_MODEL

    limit_env = os.getenv('ECFR_EMBED_LIMIT')
    try:
        limit = int(limit_env) if limit_env else None
    except ValueError:
        limit = None
    batch_env = os.getenv('ECFR_EMBED_BATCH')
    try:
        batch_size = int(batch_env) if batch_env else 32
    except ValueError:
        batch_size = 32

    texts = [r.get('content') or '' for r in ctx.enriched_sections]
    if limit:
        texts = texts[:limit]
        logger.info("embed step: limiting to first %d sections via ECFR_EMBED_LIMIT", limit)

    conn = sqlite3.connect(ctx.db_path)  # type: ignore[arg-type]
    inserted = 0
    try:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS embeddings(section_rowid INTEGER PRIMARY KEY, vector BLOB)")
        c.execute("DELETE FROM embeddings")

        # Encode in streaming mini-batches to reduce RAM spikes.
        def batches(seq, n):
            for i in range(0, len(seq), n):
                yield i, seq[i:i+n]

        for start_idx, chunk in batches(texts, batch_size):
            try:
                vectors = model.encode(chunk, show_progress_bar=False, batch_size=batch_size, normalize_embeddings=True)
            except KeyboardInterrupt:  # pragma: no cover
                logger.warning("embed step interrupted at section %d; partial embeddings saved", start_idx)
                break
            import struct
            for offset, vec in enumerate(vectors):
                rowid = start_idx + offset + 1
                blob = struct.pack(f'{len(vec)}f', *vec)
                c.execute("INSERT OR REPLACE INTO embeddings(section_rowid, vector) VALUES (?, ?)", (rowid, blob))
                inserted += 1
            if inserted % 500 == 0:
                conn.commit()
        conn.commit()
        logger.info("embed step: stored %d embeddings (model=%s)", inserted, model_name)
    finally:
        conn.close()

@pipeline_step()
def embedparas(ctx: PipelineContext) -> None:  # pragma: no cover - optional heavy
    """Generate paragraph-level embeddings.

    Respects optional limits via ECFR_EMBEDPARA_LIMIT (paragraphs) and uses the
    same cached model as section embeddings if already loaded.
    """
    import os
    try:
        from sentence_transformers import SentenceTransformer
        import struct
    except Exception as e:
        logger.warning("embedparas step: sentence-transformers not available (%s)", e)
        return
    if not ctx.db_path or not os.path.exists(ctx.db_path):
        logger.error("embedparas step: database not found; run ftsindex first")
        return

    global _EMBED_MODEL
    model_name = os.getenv('ECFR_EMBED_MODEL', 'all-MiniLM-L6-v2')
    if _EMBED_MODEL is None:
        logger.info("embedparas step: loading model %s", model_name)
        _EMBED_MODEL = SentenceTransformer(model_name)
    model = _EMBED_MODEL

    para_limit_env = os.getenv('ECFR_EMBEDPARA_LIMIT')
    try:
        para_limit = int(para_limit_env) if para_limit_env else None
    except ValueError:
        para_limit = None

    conn = sqlite3.connect(ctx.db_path)
    inserted = 0
    try:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS paragraph_embeddings(section_rowid INTEGER, para_index INTEGER, vector BLOB, PRIMARY KEY(section_rowid, para_index))")
        out_dir = Path(ctx.scraper.output_dir)
        section_dir_root = out_dir / 'sections'
        if not section_dir_root.exists():
            logger.error("embedparas step: sections directory missing; run normalize")
            return
        c.execute("SELECT rowid, title, part, section FROM sections")
        rows = c.fetchall()
        texts = []
        meta = []
        for rowid, title, part, section in rows:
            candidates = list((section_dir_root / f"title{title}").glob(f"{(section or '').replace('.', '_')}*.json"))
            if not candidates:
                continue
            try:
                sec_data = json.loads(candidates[0].read_text(encoding='utf-8'))
            except Exception:
                continue
            paragraphs = sec_data.get('paragraphs', [])
            for idx, para in enumerate(paragraphs):
                txt = (para.get('text') or '')[:1000]
                if not txt:
                    continue
                texts.append(txt)
                meta.append((rowid, idx))
                if para_limit and len(texts) >= para_limit:
                    break
            if para_limit and len(texts) >= para_limit:
                break
        if not texts:
            logger.warning("embedparas step: no paragraphs to embed")
            return
        try:
            vectors = model.encode(texts, show_progress_bar=False, batch_size=64, normalize_embeddings=True)
        except KeyboardInterrupt:  # pragma: no cover
            logger.warning("embedparas step interrupted; partial paragraph embeddings saved")
            return
        import struct
        for (rowid, idx), vec in zip(meta, vectors):
            blob = struct.pack(f'{len(vec)}f', *vec)
            c.execute("INSERT OR REPLACE INTO paragraph_embeddings(section_rowid, para_index, vector) VALUES (?,?,?)", (rowid, idx, blob))
            inserted += 1
        conn.commit()
        logger.info("embedparas step: stored %d paragraph embeddings (model=%s)", inserted, model_name)
    finally:
        conn.close()

@pipeline_step()
def apiserve(ctx: PipelineContext) -> None:  # pragma: no cover - runtime server
    """Launch a simple FastAPI server exposing /search endpoint over FTS index.
    Requires prior ftsindex (and optional embed for future semantic search).
    """
    try:
        from fastapi import FastAPI, HTTPException
        import uvicorn
    except Exception as e:
        logger.error("apiserve step: fastapi/uvicorn missing (%s)", e)
        return
    if not ctx.db_path or not os.path.exists(ctx.db_path):
        logger.error("apiserve step: database not found; run ftsindex first")
        return
    app = FastAPI(title="eCFR Search API")

    def _connect():
        return sqlite3.connect(ctx.db_path)  # type: ignore[arg-type]

    @app.get('/health')
    def health():  # type: ignore
        return {'status': 'ok'}

    @app.get('/search')
    def search(q: str, limit: int = 10):  # type: ignore
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT rowid, title, part, section, heading, snippet(sections, 4, '[', ']', '...', 10) FROM sections WHERE sections MATCH ? LIMIT ?", (q, limit))
            rows = cur.fetchall()
            return [
                {
                    'rowid': r[0], 'title': r[1], 'part': r[2], 'section': r[3], 'heading': r[4], 'snippet': r[5]
                } for r in rows
            ]
        finally:
            conn.close()

    @app.get('/titles')
    def list_titles():  # type: ignore
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT title FROM sections ORDER BY 1")
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    @app.get('/section/{rowid}')
    def get_section(rowid: int):  # type: ignore
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT rowid, title, part, section, heading, content, word_count FROM sections WHERE rowid=?", (rowid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, detail="Not found")
            return {
                'rowid': row[0], 'title': row[1], 'part': row[2], 'section': row[3], 'heading': row[4], 'content': row[5], 'word_count': row[6]
            }
        finally:
            conn.close()

    @app.get('/suggest')
    def suggest(prefix: str, limit: int = 10):  # type: ignore
        conn = _connect()
        try:
            cur = conn.cursor()
            like = f"{prefix}%"
            cur.execute("SELECT DISTINCT heading FROM sections WHERE heading LIKE ? ORDER BY heading LIMIT ?", (like, limit))
            return [r[0] for r in cur.fetchall() if r[0]]
        finally:
            conn.close()

    @app.get('/embed-search')
    def embed_search(q: str, limit: int = 5):  # type: ignore
        # Optional semantic similarity if embeddings table present
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            import struct, math
        except Exception:
            raise HTTPException(400, detail="Embeddings not enabled (install .[embed])")
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'")
            if not cur.fetchone():
                raise HTTPException(400, detail="Embeddings table missing; run embed step")
            # Load vectors
            cur.execute("SELECT section_rowid, vector FROM embeddings")
            rows = cur.fetchall()
            if not rows:
                raise HTTPException(400, detail="No embeddings present")
            # Determine vector length from first row
            first = rows[0][1]
            length = int(len(first)/4)
            unpack_fmt = f'{length}f'
            import struct
            stored = [(rid, struct.unpack(unpack_fmt, blob)) for rid, blob in rows]
            model = SentenceTransformer('all-MiniLM-L6-v2')
            qv = model.encode([q], normalize_embeddings=True)[0]
            # Cosine similarity (vectors are normalized)
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

    # Mount analyzer router if analyzer DB present
    try:  # pragma: no cover - optional
        from .analyzer.api import router as analyzer_router
        a_db = Path(ctx.scraper.output_dir) / 'analyzer.sqlite'
        if a_db.exists():
            os.environ.setdefault('ECFR_ANALYZER_DB', str(a_db))
            app.include_router(analyzer_router)
    except Exception:
        pass

    logger.info("Starting API server at http://127.0.0.1:8000 ... (Ctrl+C to stop)")
    uvicorn.run(app, host='127.0.0.1', port=8000, log_level='info')


@pipeline_step()
def analyze_ingest(ctx: PipelineContext) -> None:
    """Ingest normalized section JSON artifacts into analyzer DB (extended schema)."""
    if analyzer_ingest is None:
        logger.error("analyze_ingest: analyzer modules not available")
        return
    out_dir = Path(ctx.scraper.output_dir)
    sections_root = out_dir / 'sections'
    if not sections_root.exists():
        logger.error("analyze_ingest: sections directory missing; run normalize step first")
        return
    db_path = out_dir / 'analyzer.sqlite'
    try:
        # For now always replace (future: incremental detection)
        count = analyzer_ingest.ingest_sections(sections_root, db_path, replace=True)
        ctx.analyzer_db = str(db_path)
        logger.info("analyze_ingest: ingested %d sections", count)
    except Exception as e:  # pragma: no cover
        logger.error("analyze_ingest failed: %s", e)


@pipeline_step()
def analyze_metrics(ctx: PipelineContext) -> None:
    """Compute extended metrics for ingested sections and parts."""
    if analyzer_metrics is None:
        logger.error("analyze_metrics: analyzer modules not available")
        return
    if not ctx.analyzer_db:
        default_db = Path(ctx.scraper.output_dir) / 'analyzer.sqlite'
        if default_db.exists():
            ctx.analyzer_db = str(default_db)
    if not ctx.analyzer_db or not Path(ctx.analyzer_db).exists():
        logger.error("analyze_metrics: analyzer DB not found; run analyze_ingest first")
        return
    conn = sqlite3.connect(ctx.analyzer_db)
    try:
        analyzer_metrics.compute_section_metrics(conn)
        analyzer_metrics.compute_part_metrics(conn)
        logger.info("analyze_metrics: extended metrics computed")
    finally:
        conn.close()


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
