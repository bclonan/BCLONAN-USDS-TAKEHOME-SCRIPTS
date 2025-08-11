# ECFR Scraper

High‑level utility to download, parse, and analyze eCFR (Electronic Code of Federal Regulations) XML titles (1–50) from `govinfo.gov`. Provides checksum-based caching, parallel downloads, structured JSON export, lexical statistics, per-file metadata, and notebooks for exploration. (Former upload/storage features removed.)

## Quick Start

```powershell
pip install -r requirements.txt          # install core deps
python -m ecfr_scraper --title 1 --output .\data --verbose
```

> NOTE: Earlier versions supported upload & manifest generation; that functionality has been deprecated.

## Feature Highlights

- Title XML download with checksum skip (idempotent re-runs)
- Parallel multi-title fetch (`--all`, `--workers N`)
- XML → structured JSON (parts, sections, stats)
- Lexical analysis: word & sentence counts, top words
- Per-artifact metadata sidecar (`*.metadata.json`)
<!-- Storage/manifest features removed -->
- Logging (console + rotating log file) & progress bars (tqdm)

## CLI Reference

Run `python -m ecfr_scraper -h` or `ecfr-scraper --help` after install.

Core options:

- `--title N`                Download & process a single title
- `--all`                    Download & process all titles (1–50)
- `--output PATH`            Local output directory (default `./data`)
- `--workers INT`            Parallel download threads (default 5)
- `--metadata-only`          Skip XML parsing / JSON export (metadata only)
- `--verbose`                Verbose logging

Storage / publication:

- `--storage-backend {folder,s3}`  Select backend (omit for noop)
- `--storage-bucket VALUE`         Folder path (folder) or bucket name (s3)
- `--storage-prefix PREFIX`        Subdirectory/object key prefix (default `ecfr`)
- `--no-public`                    For S3: disable public-read ACL
- `--upload`                       After download, upload each XML (and derived JSON/metadata when processed)
- `--manifest FILE`                Write manifest JSON mapping titles to artifact paths

Examples:

```powershell
# All titles, parallel, produce manifest locally (no upload)
python -m ecfr_scraper --all --workers 8 --manifest manifest.json

# Single title, folder staging
python -m ecfr_scraper --title 10 --upload --storage-backend folder --storage-bucket staged --manifest manifest.json

# Single title, S3 (requires boto3 + credentials configured)
pip install boto3
python -m ecfr_scraper --title 5 --upload --storage-backend s3 --storage-bucket my-bucket --storage-prefix ecfr --manifest manifest.json
```

## Programmatic API

```python
from ecfr_scraper.scraper import ECFRScraper
from ecfr_scraper.storage import build_storage

storage = build_storage('folder', bucket='staged', prefix='ecfr')  # or 's3'
scraper = ECFRScraper(output_dir='data', storage=storage)

xml_path = scraper.download_title_xml(1, upload=True)
data = scraper.parse_xml(xml_path)
scraper.export_to_json(data, xml_path.replace('.xml', '.json'))
```

Key methods:

- `download_title_xml(title, output_dir=None, upload=False)`
- `download_all_titles(output_dir=None, max_workers=5, upload=False)`
- `parse_xml(path)` → structured dict
- `export_to_json(data, path)`
- `process_downloaded_files(file_paths)` batch parse + export

## Output Artifacts

For each title `N`:

- Raw XML: `data/titleN.xml`
- Parsed JSON: `data/titleN.json`
- Metadata: `data/titleN.xml.metadata.json`
- (Optional) Staged copy or S3 object if `--upload` used

Global:

- `checksums.json` — Persistent SHA‑256 map for incremental updates
- `ecfr_scraper.log` — Log file
- `manifest.json` (optional) — Summary of artifact locations

### Manifest Format

Example (folder backend):

```json
{
  "title1": {
    "xml": "data/title1.xml",
    "json": "data/title1.json",
    "metadata": "data/title1.xml.metadata.json"
  }
}
```

If S3 + public, values can be HTTPS URLs; otherwise `s3://bucket/key` style.

## Architecture Overview

```text
          +--------------------+
          |  CLI (argparse)    |
          +----------+---------+
                     |
                     v
        +------------+-------------+
        |  ECFRScraper (core)      |
        |  - download_title_xml    |
        |  - download_all_titles   |
        |  - parse_xml             |
        +------------+-------------+
                     |
        +------------+-------------+
        |  MetadataExtractor       |
        +------------+-------------+
                     |
        +------------+-------------+
        |  Storage Backend         |
        | (Noop | Folder | S3)     |
        +------------+-------------+
                     |
        +------------+-------------+
        |  Outputs / Manifest      |
        +--------------------------+
```

### Components & Responsibilities

- `ECFRScraper` — Orchestrates download, checksum validation, parsing, lexical analysis, storage upload hooks.
- `MetadataExtractor` — File-level metadata (size, mtime, hash, format heuristics) with pluggable extractors per extension.
- `utils` — Logging setup, checksum helpers, load/save checksum DB.
- `storage` — Strategy abstraction (`StorageBackend` protocol) with `NoopStorage`, `FolderStorage`, `S3Storage` + factory `build_storage`.
- `cli` — User-facing argument parsing, high-level workflow (download, process, upload, manifest assembly).
- Notebooks (`notebooks/`) — Guided usage (CLI, API, metadata, utilities, tutorial).

### Data Flow

1. CLI parses arguments → constructs storage backend + `ECFRScraper`.
2. For each title: check checksum; skip or download.
3. On fresh download: write XML, compute & persist checksum; extract metadata sidecar.
4. If parsing enabled: parse XML → structured dict → JSON export + lexical stats.
5. If `--upload`: each new artifact passed to storage backend.
6. Manifest (if requested) accumulates artifact references.

### Key Design Decisions

- **Checksum Cache**: Avoid redundant network / parsing to speed iterative runs.
- **Threaded Downloads**: Simple `ThreadPoolExecutor` suffices (I/O bound); avoids heavier async complexity.
- **Sidecar Metadata**: Keeps original XML untouched while enabling quick file introspection & reproducibility metadata.
- **Scope Simplification**: Removed prior storage/upload features to keep focus on reliable acquisition & parsing.

### Extension Points

- Add new storage: implement `upload(local_path, remote_path=None)` and wire into `build_storage`.
- Add richer parsing (citations, cross-references) inside `parse_xml`.
- Enhance metadata: extend `MetadataExtractor.extract_*` methods.
- Introduce retries/backoff or rate limiting in download logic.
- Add testing: unit tests for parsing, checksum skipping, storage strategies.

## Notebooks

Located in `notebooks/`:

- Tutorial (end-to-end)
- CLI Usage
- API Usage
- Metadata Utilities
- Utils (checksums & logging)

Open in VS Code or Jupyter Lab to experiment.

## Development & Contributing

Editable install:

```powershell
pip install -e .
```
Run a smoke test:

```powershell
python -m ecfr_scraper --title 1 --output .\data --metadata-only --verbose
```
Format / lint (add your preferred tools; none enforced yet).


## Troubleshooting

- Stale data? Delete `checksums.json` to force re-download.
- Large runs slow? Increase `--workers`, or restrict to needed titles.

## Roadmap (Ideas)

- Incremental diff export (changed sections only)
- Structured citation graph
- Optional SQLite catalog of parsed sections

## Utilizing this repository

You can use the data downloaded and parsed by the ECFR Scraper in various ways, such as:

- Analyzing the JSON output for specific regulatory text or metadata.
- Integrating the data into other applications or workflows.
- Using the metadata for compliance tracking or reporting.
- Visualizing the data for insights or presentations.
