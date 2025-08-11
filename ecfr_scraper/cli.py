import argparse
import json
import os
import logging

from .scraper import ECFRScraper
from .utils import save_checksum_db, setup_logging
from .storage import build_storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and parse ECFR XML from govinfo.gov")
    parser.add_argument("--title", type=int, help="Title number to download and parse")
    parser.add_argument("--all", action="store_true", help="Download and parse all titles")
    parser.add_argument("--output", type=str, default="./data", help="Output directory for files")
    parser.add_argument("--workers", type=int, default=5, help="Number of worker threads for parallel downloads")
    parser.add_argument("--metadata-only", action="store_true", help="Only generate metadata without parsing XML")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    # Storage / upload options
    parser.add_argument("--storage-backend", choices=["s3", "folder"], help="Optional storage backend (s3 or folder)")
    parser.add_argument("--storage-bucket", help="Bucket name (s3) or target folder path (folder backend)")
    parser.add_argument("--storage-prefix", default="ecfr", help="Prefix/path for remote objects or folder subdirectory")
    parser.add_argument("--no-public", action="store_true", help="Disable public-read ACL (s3 only)")
    parser.add_argument("--upload", action="store_true", help="Upload downloaded XML files using storage backend")
    parser.add_argument("--manifest", type=str, help="Write manifest JSON mapping title -> artifact paths")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    storage = build_storage(
        args.storage_backend,
        bucket=args.storage_bucket,
        prefix=args.storage_prefix,
        public=not args.no_public if args.storage_backend == "s3" else True,
    )
    scraper = ECFRScraper(output_dir=args.output, storage=storage)

    manifest: dict[str, dict] = {}

    if args.all:
        files = scraper.download_all_titles(args.output, max_workers=args.workers, upload=args.upload)
        if args.upload:
            for f in files:
                title_id = os.path.splitext(os.path.basename(f))[0]
                manifest.setdefault(title_id, {})["xml"] = f
        if not args.metadata_only:
            results = scraper.process_downloaded_files(files)
            summary_path = os.path.join(args.output, "processing_summary.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            logger.info(f"Processing summary saved to {summary_path}")
            if args.upload:
                for r in results:
                    if r.get("success"):
                        title_id = os.path.splitext(os.path.basename(r["file"]))[0]
                        manifest.setdefault(title_id, {}).update({
                            "json": r.get("json"),
                            "metadata": r.get("metadata"),
                        })
        save_checksum_db(scraper.checksum_db)
    elif args.title:
        xml_path = scraper.download_title_xml(args.title, args.output, upload=args.upload)
        if xml_path and not args.metadata_only:
            data = scraper.parse_xml(xml_path)
            if data:
                json_path = xml_path.replace(".xml", ".json")
                scraper.export_to_json(data, json_path)
                if args.upload:
                    title_id = os.path.splitext(os.path.basename(xml_path))[0]
                    manifest.setdefault(title_id, {}).update({
                        "xml": xml_path,
                        "json": json_path,
                        "metadata": f"{xml_path}.metadata.json",
                    })
        save_checksum_db(scraper.checksum_db)
    else:
        parser.print_help()
        return 2

    if args.manifest and manifest:
        with open(args.manifest, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in sorted(manifest.items())}, f, indent=2)
        logger.info(f"Manifest written to {args.manifest}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
