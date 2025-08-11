import argparse
import json
import os
import logging

from .scraper import ECFRScraper
from .utils import save_checksum_db, setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and parse ECFR XML from govinfo.gov")
    parser.add_argument("--title", type=int, help="Title number to download and parse")
    parser.add_argument("--all", action="store_true", help="Download and parse all titles")
    parser.add_argument("--output", type=str, default="./data", help="Output directory for files")
    parser.add_argument("--workers", type=int, default=5, help="Number of worker threads for parallel downloads")
    parser.add_argument("--metadata-only", action="store_true", help="Only generate metadata without parsing XML")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    scraper = ECFRScraper(output_dir=args.output)

    if args.all:
        files = scraper.download_all_titles(args.output, max_workers=args.workers)
        if not args.metadata_only:
            results = scraper.process_downloaded_files(files)
            summary_path = os.path.join(args.output, "processing_summary.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            logger.info(f"Processing summary saved to {summary_path}")
        save_checksum_db(scraper.checksum_db)
    elif args.title:
        xml_path = scraper.download_title_xml(args.title, args.output)
        if xml_path and not args.metadata_only:
            data = scraper.parse_xml(xml_path)
            if data:
                json_path = xml_path.replace(".xml", ".json")
                scraper.export_to_json(data, json_path)
        save_checksum_db(scraper.checksum_db)
    else:
        parser.print_help()
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
