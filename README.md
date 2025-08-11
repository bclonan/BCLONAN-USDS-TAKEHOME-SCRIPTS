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

## Troubleshooting

- Force re-download: delete `checksums.json` and rerun.
- Networking errors: check `ecfr_scraper.log` for HTTP status and details.
- Invalid XML: verify remote availability; try another title.

## License

This repository currently does not specify a license.
