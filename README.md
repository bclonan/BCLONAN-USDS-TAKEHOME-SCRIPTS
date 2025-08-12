# ECFR Scraper

Download, parse, normalize, index, embed, and analyze eCFR XML titles (1–50).

Features:

* Incremental checksum downloads
* Structured JSON export + lexical stats
* Per‑section normalized artifacts (headings, paragraphs, citations)
* Pluggable pipeline (`--chain step1,step2,...`)
* Full‑text search (SQLite FTS5)
* Section + paragraph embeddings (sentence-transformers)
* FastAPI search + analyzer metrics API
* Analyzer ingestion + primitive metrics (RRD, CCI, ERI, PBI, AMR placeholder, FLI, RSR placeholder)
* Minification / gzip + artifact manifests

---
## Quick Start

```powershell
pip install -r requirements.txt
python -m ecfr_scraper --title 1 --output .\data --verbose
```

### Common CLI Patterns

```powershell
# Single title
python -m ecfr_scraper --title 7 --output .\data
# All titles (5 workers)
python -m ecfr_scraper --all --output .\data
# Only download now, parse later
python -m ecfr_scraper --all --download-only --output .\data
# Parse previously downloaded
python -m ecfr_scraper --parse-existing --output .\data
```

### Pipeline Steps

Current steps:
`download, diff, parse, export, minify, gzipxml, manifest, normalize, enrich, ftsindex, embed, embedparas, analyze_ingest, analyze_metrics, apiserve`

```powershell
# Download + parse
python -m ecfr_scraper --title 3 --chain download,parse --output .\data
# Full export for a title
python -m ecfr_scraper --title 4 --chain download,parse,export,normalize --output .\data
```

---
## Artifacts

Per title N:

* Raw XML `data/titleN.xml`
* Parsed JSON `data/titleN.json`
* Metadata `data/titleN.xml.metadata.json`
* Normalized sections `data/sections/titleN/*.json`

Global:

* `checksums.json` – SHA-256 map
* `ecfr_index.sqlite` – FTS index (after `ftsindex`)
* `analyzer.sqlite` – Analyzer DB (after analyzer steps)
* `artifacts.json` – Manifest of artifacts + checksums
* `ecfr_scraper.log`

---
## Full Pipeline Example

```powershell
# Full (analyzer after embeddings)
python -m ecfr_scraper --all --chain download,diff,parse,export,normalize,enrich,ftsindex,embed,embedparas,minify,gzipxml,analyze_ingest,analyze_metrics,manifest --output .\data
```

Performs:

1. Download changed titles
2. Parse & export JSON
3. Normalize per‑section artifacts
4. Enrich for indexing
5. Build FTS index
6. Section + paragraph embeddings
7. Analyzer ingestion & metrics
8. Minify & gzip XML
9. Write manifests

Minimal (no embeddings/analyzer):

```powershell
python -m ecfr_scraper --all --chain download,diff,parse,export,normalize,minify,gzipxml,manifest --output .\data
```

Force full reprocess (ignore diff):

```powershell
python -m ecfr_scraper --all --chain download,parse,export,normalize,enrich,ftsindex --output .\data
```
Or delete the checksum DB:

```powershell
Remove-Item .\data\checksums.json
```

---
## API Server

After building index (and optionally analyzer DB):

```powershell
python -m ecfr_scraper --title 1 --chain download,parse,export,normalize,enrich,ftsindex,analyze_ingest,analyze_metrics,apiserve --output .\data
```
Endpoints:

* `/health`
* `/search?q=term`
* `/titles`
* `/section/{rowid}`
* `/analyzer/metrics/section/{rowid}?db=data/analyzer.sqlite`
* `/analyzer/metrics/summary/title/{title}?db=data/analyzer.sqlite`

---
## Optional Dependency Groups

```powershell
pip install .[api]       # FastAPI server
pip install .[embed]     # Section + paragraph embeddings
pip install .[analyzer]  # Analyzer ingestion + metrics
pip install .[dev]       # Tests
# Combine
pip install .[api,embed,analyzer,dev]
```

---
## Primitive Metrics (Initial Analyzer Set)

| Code | Description |
|------|-------------|
| RRD  | Redundancy density heuristic |
| CCI  | CFR citation density per 1k words |
| ERI  | External reference density per 1k words |
| PBI  | Paragraphs per 1k words |
| AMR  | Amendment ratio (placeholder 0) |
| FLI  | Fragmentation (paragraphs / log2(words)) |
| RSR  | Revision stability (placeholder 1) |

Future additions: duplication detection, graph centrality, volatility, composite scores.

---
## Validation & Minification

Scripts:

* `scripts/validate_xml.py` – structural / textual anomaly scan → JSON report
* `scripts/minify_ecfr_xml.py` – whitespace/comment stripping (conservative or aggressive)

Example:

```powershell
python scripts/validate_xml.py "data/title*.xml" > validation_report.json
python scripts/minify_ecfr_xml.py data --aggressive --drop-empty
```

Minimal artifact commit chain:

```powershell
python -m ecfr_scraper --all --chain download,diff,parse,export,normalize,minify,gzipxml,manifest --output .\data
```

---
## Development

Editable install & tests:

```powershell
pip install -e .[dev]
pytest -q
```
Smoke test:

```powershell
python -m ecfr_scraper --title 1 --output .\data --metadata-only --verbose
```

Add a pipeline step:
 
### Embedding Performance Tuning

Environment variables (optional):

* `ECFR_EMBED_MODEL` – Override model name (default `all-MiniLM-L6-v2`).
* `ECFR_EMBED_LIMIT` – Limit number of sections embedded (e.g. `500` for a quick run).
* `ECFR_EMBED_BATCH` – Batch size (default 32).
* `ECFR_EMBEDPARA_LIMIT` – Limit paragraph embeddings count.

Example (PowerShell):

```powershell
$env:ECFR_EMBED_LIMIT=500
python -m ecfr_scraper --title 1 --chain download,parse,export,normalize,enrich,ftsindex,embed --output .\data
Remove-Item Env:ECFR_EMBED_LIMIT
```

### API Testing

Unit tests now cover core search endpoints via FastAPI's TestClient (`tests/test_api_search.py`). Run all tests with:

```powershell
pytest -q
```

1. Edit `ecfr_scraper/pipeline.py`
2. Define `@pipeline_step() def stepname(ctx): ...`
3. Run with `--chain existing,stepname`

---
## Troubleshooting

* All titles skipped: remove `checksums.json` or omit `diff`.
* Missing analyzer endpoints: run `analyze_ingest,analyze_metrics` & install analyzer extra.
* Missing embeddings: install `.[embed]` and include `embed` (and `embedparas`) after `ftsindex`.
* Large runtime: subset `--title` or omit heavy steps during iteration.

---
---
## Fresh Rebuild / Cleanup

Sometimes you want to guarantee you're using only freshly generated artifacts (e.g. after code changes to parsing, normalization, or metrics). Either call the cleanup script below or run the manual PowerShell commands.

Script (recommended):

```powershell
python scripts/cleanup_artifacts.py --output .\data --reset
```

Manual (selective):

```powershell
# Remove checksum DB so all titles are treated as changed
Remove-Item .\data\checksums.json -ErrorAction SilentlyContinue
# Remove indexes & analyzer DB
Remove-Item .\data\ecfr_index.sqlite -ErrorAction SilentlyContinue
Remove-Item .\data\analyzer.sqlite -ErrorAction SilentlyContinue
# Remove section artifacts & manifests
Remove-Item -Recurse -Force .\data\sections -ErrorAction SilentlyContinue
Remove-Item .\data\artifacts.json -ErrorAction SilentlyContinue
Remove-Item .\data\manifest.json -ErrorAction SilentlyContinue
# (Optional) remove derived minified/gzip files
Remove-Item .\data\*.min.xml -ErrorAction SilentlyContinue
Remove-Item .\data\*.xml.gz -ErrorAction SilentlyContinue
```

Then re-run the desired pipeline chain (include normalize/analyzer steps if needed).


