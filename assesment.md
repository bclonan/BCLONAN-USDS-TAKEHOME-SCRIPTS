# USDS Engineering Take‑Home Assessment – Submission

## About Me
I’m Bradley Clonan, a software architect & full‑stack engineer focused on:
- Deterministic, reproducible data pipelines
- Regulatory / compliance data normalization & analytics
- Extensible architectures (plugin & step‑driven pipelines)
- Applied NLP / embeddings for semantic enrichment
- Fast iterative delivery with maintainability

## Assessment Fit
The eCFR corpus requires: structured ingestion, durable storage, metric derivation, and actionable surfacing. This project delivers a modular foundation that can expand into historical, network, and semantic analyses without large refactors.

## Delivered System(s) (Summary)

1. Primary deliverable
Pipeline from raw XML → normalized per‑section JSON → search + embeddings → analyzer DB + metrics → API.
Key characteristics:
- Idempotent, chainable steps (`--chain download,parse,...`)
- Incremental diff & normalization cache (checksums + content hash)
- Per‑section artifacts + manifest for deep linking
- FTS (SQLite FTS5) + optional embeddings (sentence-transformers)
- Paragraph‑level embeddings (optional)
- Analyzer database with multi‑metric rollups
- Robust enrichment (citations, references, paragraph structuring)
- Structured metrics API (FastAPI) + OpenAPI/Swagger UI

## Core Pipeline Steps
`download` → `diff` → `parse` → `export` → `normalize` → `enrich` → `ftsindex` → `embed` / `embedparas` (optional) → `analyze_ingest` → `analyze_metrics` → `manifest` → `apiserve`

## How to Run (Fresh Rebuild)
```powershell
# (Optional) clean
python scripts/cleanup_artifacts.py --output .\data --reset

# Install (full extras)
pip install -e .[api,embed,analyzer,dev]

# Full pipeline (analysis + API ready)
python -m ecfr_scraper --all --chain download,diff,parse,export,normalize,enrich,ftsindex,embed,embedparas,analyze_ingest,analyze_metrics,manifest --output .\data

# Serve API (Swagger at /docs)
python -m ecfr_scraper --chain apiserve --output .\data
```

Optional faster embedding run:
```powershell
$env:ECFR_EMBED_LIMIT=400
python -m ecfr_scraper --chain embed --output .\data
```

## APIs
Search / content:
- `GET /health`
- `GET /search?q=...`
- `GET /titles`
- `GET /section/{rowid}`
- `GET /suggest?q=...`
- `GET /embed-search?q=...` (if embeddings)

Analysis:
- `GET /api/parts`
- `GET /api/parts/{title}/{part}`
- `GET /api/changes`
- `GET /api/search/refs?q=...`
(Extended endpoints for section detail or additional metrics can mount similarly.)

## Metrics Implemented
Section & part rollups (densities per 1k words unless noted):
| Key | Meaning | Notes |
|-----|---------|-------|
| wc | Word count | Base size signal |
| chash | SHA-256 section hash | Change detection |
| rrd | Restriction density | shall, must, may not, prohibit*, require* |
| cci | Conditional complexity | if, unless, except, provided that... |
| eri | Enforcement / remedy intensity | penalty, sanction, violation... |
| dor | Discretion vs obligation ratio | Actor tokens vs restriction hits |
| pbi | Procedural burden | submit, report, notify, within N days... |
| amr | Ambiguity markers | reasonable, as necessary, significant... |
| fli | Fragmentation | Paragraph count scaled |
| soi | Semantic obligation intensity (custom) | Actor‑weighted restriction proximity |
| drs | Duplication / reuse | Paragraph hash reuse proxy |
| fk_grade | Flesch–Kincaid grade | Readability |
| rap | Regulatory age profile | Placeholder (AMDDATE pending) |
| hvi | Historical volatility | Placeholder (multi-snapshot) |
| rsr | Reserved surface ratio | Placeholder improved once reserved tagging expanded |
| crnc | Cross-ref centrality | Placeholder (graph/PageRank future) |

Custom highlight: SOI (Semantic Obligation Intensity)
- Weights restriction hits by nearby actor tokens (external = 1.0, internal = 0.5) within ±8 tokens.
- Distinguishes outward-facing regulatory burden from internal procedural text.

## Data Model (Analyzer DB)
Tables:
- `sections` (structural + hashes + flags)
- `paragraphs` (per-paragraph hash, future minhash)
- `references` (CFR / USC / EO / PubL / FR)
- `metrics_section`
- `metrics_part`
- `part_hash`
Manifest adds `analyzer.sqlite`, section JSON artifacts, title JSON, compressed XML.

## Change Detection
- Section hash (`chash`) and part composite hash (concatenate section hashes).
- `/api/changes` exposes latest updated sections (supports diff feeds).

## Extensibility Hooks
Planned or scaffolded:
- Historical snapshot ingestion → HVI, RAP real values.
- Reference graph centrality (PageRank) for CRNC.
- Minhash / Jaccard engine for robust DRS (currently hash reuse heuristic).
- Authority concentration (ACI) from `<AUTH>` parsing.
- True age & volatility metrics via AMDDATE extraction.

## Testing
`pytest -q` covers:
- Normalization (heading extraction, paragraph structuring)
- Analyzer ingestion & metrics rollup
- API endpoints (search + analysis)
- Number backfill (no null section/part numbers)
- Embedding steps (non-execution path guarded)

## Feedback on Assignment
Pros:
- Realistic scope; encourages thoughtful metric selection over raw scraping.
- Open‑ended enough to demonstrate architecture (pipelines, plugins, metrics).
Improvements:
- Allow explicit prompt for historical dataset to evaluate volatility.
- Clarify expected breadth of “UI” (API vs visual front-end).

## Time Allocation (≈4 Hours)
- ~1.5h pipeline + normalization scaffolding
- ~1.0h metrics + analyzer DB + API exposing rollups
- ~1.0h enrichment (refs, duplication heuristics) + tests
- ~0.5h documentation & tuning

## Additional Customization Ideas (If Extended)
- Graph-based CRNC (directed CFR/USC edge PageRank)
- Definition drift tracking across snapshots
- Hybrid lexical + embedding semantic similarity search
- Dashboard (radar plots per part; driver attribution)

## Submission Checklist
Include:
- Source ZIP
- This assessment document
- (Optional) Screenshots: Swagger `/docs`, `/api/parts`, `/api/parts/{t}/{p}`, `/search`, `/api/changes`
- Links (replace placeholders):
  - Repo: [ADD LINK]
  - Live API (if hosted): [ADD LINK]
  - UI / Mock: [ADD LINK]

## Closing
Delivered a modular, production‑oriented baseline that:
- Meets core ingestion + analysis requirements
- Adds meaningful custom metric (SOI)
- Positions project for rapid expansion into historical & graph analytics

## Additional Deliverables

