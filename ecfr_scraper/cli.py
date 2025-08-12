import argparse
import json
import os
import logging

from .scraper import ECFRScraper
from .utils import save_checksum_db, setup_logging
from .pipeline import run_pipeline, STEP_REGISTRY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and parse ECFR XML from govinfo.gov")
    parser.add_argument("--title", type=int, help="Title number to download and parse")
    parser.add_argument("--all", action="store_true", help="Download and parse all titles")
    parser.add_argument("--output", type=str, default="./data", help="Output directory for files")
    parser.add_argument("--workers", type=int, default=5, help="Number of worker threads for parallel downloads")
    parser.add_argument("--metadata-only", action="store_true", help="Only generate metadata without parsing XML")
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download (single or all) titles but skip parsing/export so you can run a later command to parse",
    )
    parser.add_argument(
        "--parse-existing",
        action="store_true",
        help="Parse & export JSON for previously downloaded XML files in the output directory (currying mode)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--chain",
        type=str,
        help=(
        "Comma-separated pipeline steps to run (use --list-steps to see all)."
        ),
    )
    parser.add_argument("--list-steps", action="store_true", help="List available pipeline step names and exit (including enrich, ftsindex, embed, apiserve, manifest)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    scraper = ECFRScraper(output_dir=args.output)

    if args.list_steps:
        print("Available steps:")
        for name in sorted(STEP_REGISTRY.keys()):
            print(f"  - {name}")
        return 0
    if args.chain:
        if args.download_only or args.parse_existing:
            parser.error("--chain cannot be combined with --download-only or --parse-existing")
        # Determine titles
        if args.all:
            titles = ECFRScraper().get_available_titles()
        elif args.title:
            titles = [args.title]
        else:
            parser.error("--chain requires either --title or --all")
        steps = [s.strip() for s in args.chain.split(",") if s.strip()]
        unknown = [s for s in steps if s not in STEP_REGISTRY]
        if unknown:
            parser.error(f"Unknown step(s): {unknown}. Use --list-steps to view valid names.")
        run_pipeline(scraper, steps, titles)
        save_checksum_db(scraper.checksum_db)
    elif args.download_only:
        if not (args.all or args.title):
            parser.error("--download-only requires --title or --all")
        if args.all:
            scraper.download_all_titles(args.output, max_workers=args.workers)
        else:
            scraper.download_title_xml(args.title, args.output)
        save_checksum_db(scraper.checksum_db)
        logging.getLogger(__name__).info("Download-only complete. Run again with --parse-existing to process.")
    elif args.parse_existing:
        # Gather XML files in output directory (optionally filtered by title)
        if not os.path.isdir(args.output):
            parser.error(f"Output directory '{args.output}' does not exist")
        xml_files = [
            os.path.join(args.output, f)
            for f in os.listdir(args.output)
            if f.startswith("title") and f.endswith(".xml")
        ]
        if args.title:
            xml_files = [p for p in xml_files if p.endswith(f"title{args.title}.xml")]
            if not xml_files:
                parser.error(f"No downloaded XML found for title {args.title} in {args.output}")
        if not xml_files:
            parser.error("No XML files found to parse. Run with --download-only first.")
        if not args.metadata_only:
            scraper.process_downloaded_files(xml_files)
        else:
            logging.getLogger(__name__).info("--metadata-only provided; nothing to do during parse-existing.")
        save_checksum_db(scraper.checksum_db)
    elif args.all:
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
