# ECFR Scraper

Download, parse, and analyze eCFR XML from govinfo.gov with checksum verification, progress tracking, and metadata extraction.

- Package: `ecfr_scraper` (importable and runnable via `python -m ecfr_scraper`)
- Console script: `ecfr-scraper` (installed via this package)
- Key modules:
  - `ecfr_scraper.scraper` — main scraper and parser (`ECFRScraper`)
  - `ecfr_scraper.metadata` — multi-format metadata extraction (`MetadataExtractor`)
  - `ecfr_scraper.utils` — checksums, logging, persistence
  - `ecfr_scraper.cli` — CLI entrypoint

## Features

- Download eCFR title XMLs (Titles 1–50) with caching via checksums
- Parallel downloads with progress bar
- XML parsing into structured JSON + lexical stats
- Per-file metadata JSON (XML, ZIP, TXT; PDF placeholder)
- Persistent checksum DB for change detection
- Logging to console and file

## Requirements

- Python 3.9+
- Dependencies installed automatically when packaging; or use requirements.txt

Quick install of deps (without packaging):

```powershell
pip install -r requirements.txt
```

## Usage

You can run the tool as a module or via the console script.

- Show help:

```powershell
python -m ecfr_scraper -h
```

- Download and parse a single title:

```powershell
python -m ecfr_scraper --title 21 --output .\data --verbose
```

- Download all titles in parallel (5 workers default, 8 shown):

```powershell
python -m ecfr_scraper --all --workers 8 --output .\data
```

- Generate only metadata (skip XML parsing/JSON export):

```powershell
python -m ecfr_scraper --title 12 --metadata-only
```

After installing the package (editable/development mode):

```powershell
pip install -e .
# Then
ecfr-scraper --help
```

## Outputs

For each downloaded title N:

- XML: .\data\titleN.xml
- Parsed JSON: .\data\titleN.json
- File metadata: .\data\titleN.xml.metadata.json
- Global checksums: .\checksums.json
- Logs: .\ecfr_scraper.log

## How it works

- Downloads from <https://www.govinfo.gov/bulkdata/ECFR/title-N/ECFR-titleN.xml>
- Skips downloads if checksum matches in checksums.json
- Parses XML to extract parts, sections, and text stats
- Writes parsed JSON and file metadata alongside the XML

## Development

- Code lives under the `ecfr_scraper/` package.
- Extend metadata extraction by adding a transformer method to `MetadataExtractor`.
- Improve parsing by adjusting XPaths in `ECFRScraper.parse_xml`.

Run a quick smoke test:

```powershell
python -m ecfr_scraper --title 1 --output .\data --metadata-only --verbose
```

If the document is unchanged 

```
(base) PS C:\Users\bradl\OneDrive\Documents\GitHub\BCLONAN-USDS-TAKEHOME-SCRIPTS> python -m ecfr_scraper --title 1 --output .\data --metadata-only --verbose
2025-08-11 17:52:07,802 - INFO - ecfr_scraper.scraper - Title 1 unchanged. Skipping download.
```

## Troubleshooting

- Force re-download: delete `checksums.json` and rerun.
- Networking errors: check `ecfr_scraper.log` for HTTP status and details.
- Invalid XML: verify remote availability; try another title.

## Utilizing the data from the repository 

You can use the data downloaded and parsed by the ECFR Scraper in various ways, such as:

- Analyzing the JSON output for specific regulatory text or metadata.
- Integrating the data into other applications or workflows.
- Using the metadata for compliance tracking or reporting.
- Visualizing the data for insights or presentations.
