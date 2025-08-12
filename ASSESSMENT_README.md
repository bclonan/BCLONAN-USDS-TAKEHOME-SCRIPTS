# USDS Engineering Take‑Home Assessment – Solution Summary

This supplemental README maps the delivered implementation to the assessment requirements and provides concise run / review instructions for evaluators.

---
## 1. Purpose & Scope

Goal: Ingest the current eCFR corpus, persist structured regulatory text server‑side, expose APIs & metrics enabling analysis of regulatory volume, density, and obligation characteristics, and surface a foundation for future deregulatory insight tooling.

The project emphasizes:
* Reproducible pipeline from raw XML → normalized JSON → indexed + analyzed SQLite stores.
* Lightweight infra (pure Python + SQLite) for easy local review.
* Extensible metrics layer with clear placeholders for future historical / graph analytics.

---
## 2. High‑Level Architecture

Pipeline (pluggable steps, selectable via `--chain`):

`download → diff → parse → export → normalize → enrich → ftsindex → embed → embedparas → analyze_ingest → analyze_metrics → (minify,gzipxml,manifest) → apiserve`

Data Stores:
* `checksums.json` – Change detection (incremental downloads).
* `ecfr_index.sqlite` – FTS5 full‑text search over sections (title, part, section, heading, content).
* `analyzer.sqlite` – Extended analyzer schema:
  * `sections` (normalized text, hashes, flags, timestamps)
  * `paragraphs` (per‑paragraph text + hash)
  * `references` (normalized cross references: CFR, USC, FR, EO, PubL)
  * `metrics_section` (per‑section metrics)
  * `metrics_part` (roll‑ups by title+part)

Server:
* FastAPI application (mounted pipeline search + analyzer router)
* Simple environment‑based DB discovery (`ECFR_ANALYZER_DB`)

Embeddings (optional):
* SentenceTransformer (MiniLM by default) for semantic similarity and future clustering.

---
## 3. Running the End‑to‑End Pipeline

Minimal (structure + metrics, no embeddings):
```powershell
pip install -r requirements.txt
python -m ecfr_scraper --title 1 --chain download,parse,export,normalize,enrich,ftsindex,analyze_ingest,analyze_metrics --output .\data
```

Full (includes embeddings & artifact compression):
```powershell
python -m ecfr_scraper --all --chain download,diff,parse,export,normalize,enrich,ftsindex,embed,embedparas,analyze_ingest,analyze_metrics,minify,gzipxml,manifest --output .\data
```

Serve APIs:
```powershell
python -m ecfr_scraper --title 1 --chain download,parse,export,normalize,enrich,ftsindex,analyze_ingest,analyze_metrics,apiserve --output .\data
```
Then visit: `http://127.0.0.1:8000/docs`

Optional embedding limits for quick iteration:
```powershell
$env:ECFR_EMBED_LIMIT=300
python -m ecfr_scraper --title 1 --chain download,parse,export,normalize,enrich,ftsindex,embed --output .\data
Remove-Item Env:ECFR_EMBED_LIMIT
```

Cleanup & full rebuild:
```powershell
python scripts\cleanup_artifacts.py --output .\data --reset
```

---
## 4. Implemented APIs

Core Search:
* `/health` – Status
* `/search?q=` – FTS search (snippet highlighting)
* `/titles` – Distinct titles
* `/section/{rowid}` – Raw section content from FTS index

Analyzer (extended):
* `/analyzer/section/{uid}` – Section metadata + metrics
* `/analyzer/parts?title={n}` – List parts (optionally within a title)
* `/analyzer/parts/{title}/{part}` – Aggregated part metrics
* `/analyzer/search/refs?q=40 CFR` – Ranked reference frequency
* `/analyzer/changes` – Recently updated sections (timestamp proxy for volatility)

Semantic (optional):
* `/embed-search?q=` – Vector similarity (if embeddings computed)

---
## 5. Metrics (Delivered vs. Placeholders)

Per Section (`metrics_section`):

| Code | Meaning (Current Implementation) | Type |
|------|----------------------------------|------|
| wc | Word count | volume |
| paragraphs | Paragraph count | structure |
| sentences | Sentence count (naive split) | structure |
| rrd | Readability density (sentences / paragraphs) | readability proxy |
| cci | Compression index (paragraphs / words) | structural density |
| eri | Obligation density ("shall|must|may not|shall not|prohibited|required" / sentence) | obligation |
| dor | Prohibitive density (prohibitive tokens / sentence) | restriction |
| pbi | Prohibitive to obligation ratio | balance |
| amr | Ambiguity ratio (ambiguous adjectives / words) | clarity |
| fli | Feasibility language incidence (feasible/practicable/possible per sentence) | flexibility |
| hvi | Hazard / risk language per sentence | risk salience |
| drs | Small entity reference ratio | impact (small entities) |
| soi | Semantic obligation intensity (obligation tokens / words) – Custom metric | obligation |
| fk_grade | Flesch‑Kincaid grade (naive syllable estimate) | readability |
| rap | Amendment pressure (placeholder NULL) | TODO (history) |
| rsr | Scope / reach (placeholder NULL) | TODO (graph) |
| crnc | Cross‑reference centrality (placeholder NULL) | TODO (graph network) |

Per Part (`metrics_part`): aggregated sums (wc, paragraphs, sentences) + averages (eri, dor, amr, fli, hvi, drs, soi, fk_grade).

Custom Metric Highlight: **SOI (Semantic Obligation Intensity)** – ratio of obligation tokens to total words; surfaces sections disproportionately imposing mandatory actions.

Checksums / Hashes:
* `sections.chash` SHA‑256 of normalized section text (uniqueness & change detection)
* Paragraph‑level hashes enable duplication / reuse future analysis.

Historical change analysis not fully implemented; current `/analyzer/changes` uses `updated_at` (ingest time) as a proxy. Extending to diff archives would unlock RAP & volatility metrics.

---
## 6. Requirement Mapping

| Requirement | Status | Notes |
|-------------|--------|-------|
| Download current eCFR data | Implemented | Incremental via checksum diff |
| Store server‑side | Implemented | Structured JSON + SQLite stores |
| APIs to retrieve data | Implemented | Search + analyzer endpoints |
| UI to analyze | Partially (API) | Swagger UI (FastAPI docs) acts as review surface; frontend out of scope (time) |
| Word count per agency | Implemented | Title/Part roll‑ups (metrics_part) |
| Historical changes | Partial | Updated timestamps + changes view; no multi‑snapshot history yet |
| Checksum per agency | Implemented at section & paragraph level | Part checksum placeholder (can aggregate) |
| Custom metric | Implemented | SOI + ambiguity, feasibility, risk densities |
| Meaningful analysis | Implemented | Obligation, prohibitive, ambiguity, readability, small entity focus |

---
## 7. Packaging / Submission

Create zip (exclude large caches / virtualenv):
```powershell
Compress-Archive -Path .\ecfr_scraper, .\scripts, .\tests, README.md, ASSESSMENT_README.md, pyproject.toml, requirements.txt -DestinationPath ecfr_submission.zip
```
Include in submission document:
* Feedback (see section 10 placeholder below)
* Time spent
* (Optional) Link to any frontend if later added
* Screenshots: Suggest running `/docs`, a `/search` query, and `/analyzer/section/{uid}` for representative metrics.

---
## 8. Quick Evaluation Script

For a fast smoke run on a single title with metrics:
```powershell
pip install -r requirements.txt
python -m ecfr_scraper --title 1 --chain download,parse,export,normalize,enrich,ftsindex,analyze_ingest,analyze_metrics,apiserve --output .\data
# Open http://127.0.0.1:8000/docs
```

To exercise reference search after a larger run:
```powershell
python -m ecfr_scraper --title 2 --chain download,parse,export,normalize,enrich,ftsindex,analyze_ingest,analyze_metrics --output .\data
curl http://127.0.0.1:8000/analyzer/search/refs?q=40%20CFR
```

---
## 9. Limitations & Future Work

| Area | Next Step |
|------|-----------|
| Historical metrics | Persist per‑run snapshots & compute RAP / volatility deltas |
| Graph centrality | Build directed reference graph → CRNC / RSR actual values |
| Duplication | Paragraph hash reuse frequency & near‑duplicate detection (MinHash / simhash) |
| Part checksum | Aggregate deterministic part hash (ordered section hashes) |
| Readability | Replace naive syllable counter with robust library (textstat) |
| UI | Add lightweight frontend dashboards (word clouds, metric histograms) |
| Performance | Batch ingestion further; optional multiprocessing for parsing |
| Testing | Expand analyzer tests for new endpoints & metric edge cases |

---
## 10. Feedback & Submission Notes (Fill Before Sending)

* Time Spent: `TODO`
* Most valuable metric: `SOI reveals obligation-heavy sections quickly.`
* Trade‑offs: `Focused on breadth of analytical foundation vs. polished UI; deferred historical diff store & network centrality due to time ceiling.`
* Potential Extensions: `Risk ranking combining SOI, ambiguity, and small entity impact; cross‑title duplication heat map; temporal churn dashboards.`
* General Feedback: `TODO`

---
## 11. Repository Guide (At a Glance)

| Path | Purpose |
|------|---------|
| `ecfr_scraper/pipeline.py` | Step registration & orchestration |
| `ecfr_scraper/normalize.py` | Normalization & per‑section artifact generation |
| `ecfr_scraper/analyzer/ingest.py` | Extended ingestion → analyzer.sqlite |
| `ecfr_scraper/analyzer/metrics_ext.py` | Metrics computation (section + part) |
| `ecfr_scraper/analyzer/api.py` | Analyzer FastAPI router |
| `ecfr_scraper/api.py` | App factory / API mounting (search) |
| `tests/` | Unit tests (search, normalization, analyzer primitives) |
| `scripts/cleanup_artifacts.py` | Safe reset of derived outputs |

---
## 12. Custom Metric Rationale (SOI)

Regulatory burden often correlates with prescriptive language density. Counting obligation verbs normalized by word count exposes sections that may merit scrutiny for over‑specification or compliance overhead. Unlike raw word count, SOI highlights intensity rather than volume, enabling prioritization of compact yet directive-heavy rules.

---
## 13. Security / Privacy Considerations

Data is public (eCFR). No PII processed. SQLite kept local; no external network writes beyond source fetch.

---
## 14. Conclusion

This codebase establishes a lean but extensible analytical substrate over the eCFR, pairing deterministic text normalization with emerging semantic / structural heuristics. It is ready to evolve toward historical tracking, network analysis, and richer UI surfaces without large rewrites.

---
_Supplemental document – does not replace primary README._
