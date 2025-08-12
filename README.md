# ECFR Scraper

Utility to download, parse, and analyze eCFR (Electronic Code of Federal Regulations) XML titles (1–50) from `govinfo.gov`. Provides checksum-based caching, parallel download, structured JSON export, lexical statistics, per-file metadata, and a pluggable pipeline. (Legacy upload / storage & manifest features removed.)

## Quick Start

```powershell
pip install -r requirements.txt  # install deps
python -m ecfr_scraper --title 1 --output .\data --verbose
```

> Earlier versions supported upload & manifest generation; that functionality was removed to keep the core minimal.

### Run the scraper (common patterns)

```powershell
# Single title
python -m ecfr_scraper --title 7 --output .\data

# All titles (default 5 workers)
python -m ecfr_scraper --all --output .\data

# All titles with more workers
python -m ecfr_scraper --all --workers 10 --output .\data

# Metadata only (skip parse/export JSON)
python -m ecfr_scraper --title 12 --metadata-only --output .\data

# Two-stage workflow (currying style): 1) download only now, parse later
python -m ecfr_scraper --all --download-only --output .\data

# Later (separate command / CI step) parse all previously downloaded XML
python -m ecfr_scraper --parse-existing --output .\data

# Parse only a specific previously downloaded title
python -m ecfr_scraper --title 7 --parse-existing --output .\data
```

### Chaining plugin-style steps

Compose the internal pipeline using `--chain` with a comma‑separated list of steps.

Available built-in steps (current): `download`, `diff`, `parse`, `export`, `minify`, `gzipxml`.

```powershell
# Download + parse one title (no JSON export)
python -m ecfr_scraper --title 3 --chain download,parse --output .\data

# Download, parse, and export JSON for a single title
python -m ecfr_scraper --title 4 --chain download,parse,export --output .\data

# Run full pipeline for all titles (can be long!)
python -m ecfr_scraper --all --chain download,parse,export --output .\data
```

Notes:

* `--chain` overrides the basic `--title/--all` flow & executes only the listed steps.
* Steps run in order; duplicates are allowed but seldom useful.
* See `--list-steps` to view all registered steps.
* Add new steps in `ecfr_scraper/pipeline.py` (see Adding a New Pipeline Step below).

## Feature Highlights

* Title XML download with checksum skip (idempotent re-runs)
* Parallel multi-title fetch (`--all`, `--workers N`)
* XML → structured JSON (parts, sections, stats)
* Lexical analysis: word & sentence counts, top words
* Per-artifact metadata sidecar (`*.metadata.json`)
* Logging (console + rotating log file) & progress bars (tqdm)
* Pluggable pipeline (e.g. `--chain download,diff,parse,export,minify,gzipxml`)
* Change detection step (`diff`) to narrow work to modified titles
* Minification + gzip steps for repo-friendly storage (optional)

## CLI Reference

Run `python -m ecfr_scraper -h` (or after installation `ecfr-scraper --help`).

Core options:

* `--title N`                Download & process a single title
* `--all`                    Download & process all titles (1–50)
* `--output PATH`            Output directory (default `./data`)
* `--workers INT`            Parallel download threads (default 5)
* `--metadata-only`          Skip XML parsing / JSON export
* `--download-only`          Perform only downloads; skip parsing/export for later command
* `--parse-existing`         Parse/export already downloaded XML in output directory
* `--chain STEPS`            Comma list of pipeline steps (download,parse,export,...)
* `--list-steps`             Show available pipeline step names and exit
* `--verbose`                Verbose logging

Python API (selected methods):

* `download_title_xml(title, output_dir=None)`
* `download_all_titles(output_dir=None, max_workers=5)`
* `parse_xml(path)` → structured dict
* `export_to_json(data, path)`
* `process_downloaded_files(file_paths)` (batch parse + export)

Artifacts for each title `N`:

* Raw XML: `data/titleN.xml`
* Parsed JSON: `data/titleN.json`
* Metadata: `data/titleN.xml.metadata.json`

Global:

* `checksums.json` — Persistent SHA‑256 map (incremental updates)
* `ecfr_scraper.log` — Log file

## Architecture

### Components & Responsibilities

* `ECFRScraper` — Orchestrates download, checksum validation, parsing, lexical stats.
* `MetadataExtractor` — File-level metadata (size, mtime, hash, format heuristics).
* `utils` — Logging + checksum DB helpers.
* `pipeline` — Registry + runner for pluggable steps (`STEP_REGISTRY`).
* `cli` — Argument parsing; invokes classic or pipeline flows.
* Notebooks (`notebooks/`) — Tutorial & exploratory usage.

### Local Data Flow

1. Parse CLI args → construct `ECFRScraper` (or pipeline context).
2. For each title: checksum check → download if changed.
3. Immediately emit metadata sidecar.
4. Parse XML → structured dict + lexical statistics.
5. Export JSON (if step included).

### Key Design Decisions

* **Checksum Cache** avoids redundant work on re-runs.
* **ThreadPool Downloads** (I/O bound) keep implementation simple vs async.
* **Sidecar Metadata** supports reproducibility & quick introspection.
* **Pipeline Pattern** enables extension without CLI explosion.
* **Scope Reduction** (removed storage/upload) keeps focus on core reliability.

## Extended Ecosystem Workflow (Vision)

Textual version of the provided workflow diagram:

```text
Scraper Repo (pipeline) -> Commit/Pull Request -> GitHub Actions
        |                                               |
        | (XML + JSON + metadata in /data)              v
        |                                   Transform / Compress (optional)
        |                                               |
        +-----------------------------------------------+
                                                        v
                              Supabase (metadata + search/FAAIS tables)
                                                        |
                                                        v
                              Vue 3 Frontend (hybrid search + analysis)
                                                        |
                                                        v
                                       User Queries / Resonance Loader*
```

*Resonance Loader (experimental)*: on-demand ingestion / embedding path when large titles (e.g. Title 40) exceed embedding or repo size constraints.

### Extended Components

* **GitHub Actions** — Triggers on push; can run scraper, compression, and DB sync.
* **Supabase** — Central metadata + search API; may hold precomputed embeddings.
* **Vue 3 Frontend** — Hybrid lexical/semantic search & analysis UI.
* **Resonance Loader** — Dynamic embedding or streaming loader for oversized content.

### Automated Update Pipeline

1. Developer / cron runs scraper (`--chain download,parse,export`).
2. Commit & push changed artifacts & checksums.
3. GitHub Action filters on `data/**` changes.
4. Action optionally recomputes changed titles, compresses artifacts, transforms to rows.
5. Upsert rows + embeddings into Supabase.
6. Frontend reflects new data via API queries.

### Example GitHub Action Skeleton

```yaml
name: Update Supabase Index
on:
  push:
    branches: [ main ]
    paths:
      - 'data/**'
      - 'checksums.json'
jobs:
  update-index:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install
        run: pip install -r requirements.txt
      - name: Detect Changed Titles
        run: python scripts/diff_changed_titles.py > changed.txt || echo "" > changed.txt
      - name: Export Rows
        run: python scripts/export_sections.py --input data --out rows.csv
      - name: Upload to Supabase
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
        run: python scripts/upsert_supabase.py rows.csv
```

> Helper scripts above are illustrative; implement as needed for your schema.

## Adding a New Pipeline Step

1. Edit `ecfr_scraper/pipeline.py`.
2. Implement: `def step_name(ctx: PipelineContext) -> None`.
3. Register: `STEP_REGISTRY['name'] = step_name`.
4. Run: `--chain existing,name`.

Current extra steps:

* `diff` – Replaces the XML file list with only changed titles based on checksum DB comparison (run after `download`).
* `minify` – Strips redundant whitespace/comments; writes `*.min.xml`.
* `gzipxml` – Gzips (minified if present) XML to `*.xml.gz` and writes `manifest.json`.

Potential future steps: `embed`, `index`, `supabase-sync`.

## Extension Points

* Richer parsing (citations, cross-references) inside `parse_xml`.
* Metadata enhancements (MIME / validation / semantic hashes).
* Retry/backoff or rate limiting for download robustness.
* Pipeline steps for embeddings, diffing, external sync, compression.
* Unit tests (parsing correctness, checksum skip behavior, pipeline sequencing).

## Notebooks

Located in `notebooks/`:

* Tutorial (end-to-end)
* CLI Usage
* API Usage
* Metadata Utilities
* Utils (checksums & logging)

## Development

Editable install:

```powershell
pip install -e .
```

Smoke test:

```powershell
python -m ecfr_scraper --title 1 --output .\data --metadata-only --verbose
```

## Troubleshooting

* Stale data? Delete `checksums.json` to force re-download.
* Slow? Increase `--workers` or limit titles.
* Empty JSON? Ensure you didn't pass `--metadata-only` or omit `parse/export` in the chain.

## Data Validation & Minification

Two helper scripts in `scripts/` help keep XML consistent and smaller:

| Script | Purpose |
|--------|---------|
| `validate_xml.py` | Scan XML for structural/text anomalies (duplicate NODE IDs, irregular section heads, empty metadata tags, non‑ASCII chars, possible truncations). Outputs JSON report. |
| `minify_ecfr_xml.py` | Remove indentation, blank text nodes, comments; optionally collapse extra internal spaces and drop empty metadata elements; writes `*.min.xml`. |

### Examples (PowerShell)

```powershell
# Validate all titles and save report
python scripts/validate_xml.py "data/title*.xml" > validation_report.json

# Conservative minify (structure + whitespace cleanup)
python scripts/minify_ecfr_xml.py data

# Aggressive minify + drop empty metadata
python scripts/minify_ecfr_xml.py data --aggressive --drop-empty
```

Recommended commit workflow:

```powershell
python -m ecfr_scraper --all --chain download --output data
python scripts/validate_xml.py "data/title*.xml" > validation_report.json
python scripts/minify_ecfr_xml.py data --aggressive --drop-empty
# (Optional) replace originals after review
```

If you store only minified versions in git, ensure downstream tools read either `*.min.xml` or rename after verification.

### Data Management & Compression Strategy

Repository intentionally ignores raw unminified XML via `.gitignore` rules:

```gitignore
data/title*.xml        # ignored raw
!data/title*.min.xml   # keep minified
!data/title*.xml.gz    # keep compressed
!data/manifest.json    # keep manifest
```

Suggested chain to produce minimal artifacts for commit:

```powershell
python -m ecfr_scraper --all --chain download,diff,parse,export,minify,gzipxml --output .\data
```

Resulting retained files (after optional manual deletion of raw):

* `titleN.min.xml` (if you choose to keep a readable minimized form)
* `titleN.xml.gz` (compressed for storage)
* `titleN.json` (parsed structure)
* `titleN.xml.metadata.json` (sidecar metadata)
* `manifest.json` (list + checksums of gzipped XML)

### CI Validation

The workflow `.github/workflows/validate.yml` performs:

1. Install dependencies & `lxml`.
2. Run a download (and optionally chained diff/parse/export).
3. Execute XML validation (`scripts/validate_xml.py`).
4. Fail build on any structural errors (warnings allowed).
5. Upload `validation_report.json` as an artifact.

To extend CI: add an additional step after validation to run `minify` + `gzipxml` and push a data branch or release.

