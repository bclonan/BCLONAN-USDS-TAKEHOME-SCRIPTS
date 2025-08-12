import os
import re
import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
"""Core scraper logic: download ECFR titles, parse XML, export JSON & metadata.

This module provides ECFRScraper with:
  * resilient HTTP session (retries)
  * checksum tracking to skip unchanged downloads
  * concurrent bulk download with progress (tqdm + as_completed)
  * XML parsing + lightweight lexical stats
  * metadata extraction for each downloaded XML
"""

import os
import re
import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import xml.etree.ElementTree as ET
from tqdm import tqdm

from .metadata import MetadataExtractor
from .utils import calculate_checksum, load_checksum_db, save_checksum_db

logger = logging.getLogger(__name__)


class ECFRScraper:
    """Download, parse, and export ECFR titles with retry + checksum support."""

    def __init__(
        self,
        base_url: str = "https://www.govinfo.gov/bulkdata/ECFR",
        output_dir: str = "./data",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.output_dir = output_dir
        self.session: Optional[requests.Session] = None
        self.checksum_db = load_checksum_db()
        self.metadata_extractor = MetadataExtractor()
        os.makedirs(self.output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Networking / Download
    # ------------------------------------------------------------------
    def _configure_session(self) -> None:
        if self.session is not None:
            return
        session = requests.Session()
        retry = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        self.session = session

    def get_available_titles(self) -> List[int]:
        return list(range(1, 51))

    def download_title_xml(self, title_number: int, output_dir: Optional[str] = None) -> Optional[str]:
        if output_dir is None:
            output_dir = self.output_dir
        os.makedirs(output_dir, exist_ok=True)
        filename = f"title{title_number}.xml"
        path = os.path.join(output_dir, filename)
        url = f"{self.base_url}/title-{title_number}/ECFR-title{title_number}.xml"

        if os.path.exists(path):
            existing = calculate_checksum(file_path=path)
            if existing == self.checksum_db.get(filename):
                logger.info("Title %s unchanged. Skipping download.", title_number)
                return path

        try:
            self._configure_session()
            logger.info("Downloading title %s", title_number)
            resp = self.session.get(url, timeout=60)  # type: ignore[arg-type]
            resp.raise_for_status()
            with open(path, "wb") as f:
                f.write(resp.content)
            self.checksum_db[filename] = calculate_checksum(file_path=path)
            metadata = self.metadata_extractor.extract(path)
            with open(f"{path}.metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            return path
        except requests.RequestException as e:  # pragma: no cover - network
            logger.warning("Failed to download title %s: %s", title_number, e)
            return None

    def download_all_titles(self, output_dir: Optional[str] = None, max_workers: int = 5) -> List[str]:
        if output_dir is None:
            output_dir = self.output_dir
        titles = self.get_available_titles()
        results: List[str] = []
        failures: List[int] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self.download_title_xml, t, output_dir): t for t in titles}
            with tqdm(total=len(future_map), desc="Downloading Titles") as bar:
                for fut in as_completed(future_map):
                    t = future_map[fut]
                    try:
                        path = fut.result()
                        if path:
                            results.append(path)
                        else:
                            failures.append(t)
                    except Exception as e:  # pragma: no cover
                        logger.error("Unexpected error downloading title %s: %s", t, e)
                        failures.append(t)
                    bar.update(1)
        save_checksum_db(self.checksum_db)
        if failures:
            logger.warning("Failed titles: %s", failures)
        logger.info("Downloaded %s/%s titles", len(results), len(titles))
        return results

    def get_resource_file(self, resource_name: str) -> Optional[str]:
        resource_url = f"{self.base_url}/{resource_name}"
        path = os.path.join(self.output_dir, resource_name)
        if os.path.exists(path):
            if calculate_checksum(file_path=path) == self.checksum_db.get(resource_name):
                logger.info("Resource %s unchanged. Skipping.", resource_name)
                return path
        try:
            self._configure_session()
            resp = self.session.get(resource_url, timeout=60)  # type: ignore[arg-type]
            resp.raise_for_status()
            with open(path, "wb") as f:
                f.write(resp.content)
            self.checksum_db[resource_name] = calculate_checksum(file_path=path)
            metadata = self.metadata_extractor.extract(path)
            with open(f"{path}.metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            return path
        except requests.RequestException as e:  # pragma: no cover
            logger.error("Failed resource download %s: %s", resource_name, e)
            return None

    # ------------------------------------------------------------------
    # Parsing / Export
    # ------------------------------------------------------------------
    def parse_xml(self, xml_path: str):
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            title_info = {
                "title_number": self._safe_get_text(root, ".//TITL"),
                "title_name": self._safe_get_text(root, ".//HEAD"),
                "parts": [],
                "stats": {"total_sections": 0, "word_count": 0, "paragraph_count": 0},
            }
            # Parts are DIV5 TYPE="PART"; earlier code incorrectly iterated DIV6 (subparts)
            for part in root.findall(".//DIV5[@TYPE='PART']"):
                raw_part_num = part.get("N")  # attribute holds the numeric part identifier
                part_head_text = self._safe_get_text(part, "./HEAD") or ""
                # Fallback: extract part number from heading like "PART 10—..."
                if not raw_part_num and part_head_text:
                    m_part = re.search(r"PART\s+([0-9A-Za-z]+)", part_head_text)
                    raw_part_num = m_part.group(1) if m_part else None
                pinfo = {
                    "part_number": raw_part_num,
                    "part_name": part_head_text.strip() if part_head_text else None,
                    "sections": [],
                }
                # Sections under a part may be nested within SUBPART (DIV6) containers. We collect DIV8 TYPE="SECTION" beneath this part only.
                for section in part.findall(".//DIV8[@TYPE='SECTION']"):
                    section_text = ET.tostring(section, encoding="unicode", method="text").strip()
                    raw_sec_num = section.get("N")  # attribute like "§ 10.1"
                    if raw_sec_num:
                        # Normalize to bare number without leading symbol § and surrounding spaces
                        m_num = re.search(r"§\s*([0-9][0-9A-Za-z.\-]*)", raw_sec_num)
                        norm_sec_num = m_num.group(1) if m_num else raw_sec_num.strip()
                    else:
                        # Fallback parse from HEAD if attribute missing
                        head_txt = self._safe_get_text(section, "./HEAD") or ""
                        m_head = re.match(r"§\s*([0-9][0-9A-Za-z.\-]*)", head_txt)
                        norm_sec_num = m_head.group(1) if m_head else None
                    sinfo = {
                        "section_number": norm_sec_num,
                        "section_name": self._safe_get_text(section, "./HEAD"),
                        "content": section_text,
                        "word_count": len(re.findall(r"\b\w+\b", section_text)),
                        "paragraph_count": len(section.findall(".//P")),
                    }
                    pinfo["sections"].append(sinfo)
                    title_info["stats"]["total_sections"] += 1
                    title_info["stats"]["word_count"] += sinfo["word_count"]
                    title_info["stats"]["paragraph_count"] += sinfo["paragraph_count"]
                title_info["parts"].append(pinfo)
            all_text = "".join(root.itertext())
            title_info["lexical_analysis"] = self._perform_lexical_analysis(all_text)
            return title_info
        except Exception as e:  # pragma: no cover
            logger.error("Error parsing %s: %s", xml_path, e)
            return None

    def _safe_get_text(self, element, xpath):
        found = element.find(xpath)
        return found.text if found is not None else None

    def _perform_lexical_analysis(self, text: str):
        words = re.findall(r"\b\w+\b", text.lower())
        word_count = len(words)
        sentences = re.split(r"[.!?]+", text)
        sentence_count = len([s for s in sentences if s.strip()])
        return {
            "total_words": word_count,
            "unique_words": len(set(words)),
            "avg_word_length": sum(len(w) for w in words) / word_count if word_count else 0,
            "top_words": Counter(words).most_common(20),
            "sentence_count": sentence_count,
            "avg_sentence_length": word_count / sentence_count if sentence_count else 0,
        }

    def export_to_json(self, data, output_path: str) -> bool:
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("Exported %s", output_path)
            return True
        except Exception as e:  # pragma: no cover
            logger.error("JSON export failed for %s: %s", output_path, e)
            return False

    # ------------------------------------------------------------------
    # High-level processing
    # ------------------------------------------------------------------
    def process_downloaded_files(self, files: List[str]):
        results = []
        for path in tqdm(files, desc="Processing Files"):
            try:
                data = self.parse_xml(path)
                if data:
                    json_path = path.replace(".xml", ".json")
                    self.export_to_json(data, json_path)
                    metadata = self.metadata_extractor.extract(path)
                    with open(f"{path}.metadata.json", "w", encoding="utf-8") as f:
                        json.dump(metadata, f, indent=2)
                    results.append({"file": path, "json": json_path, "metadata": f"{path}.metadata.json", "success": True})
                else:
                    results.append({"file": path, "success": False, "error": "parse failed"})
            except Exception as e:  # pragma: no cover
                logger.error("Processing error %s: %s", path, e)
                results.append({"file": path, "success": False, "error": str(e)})
        return results
