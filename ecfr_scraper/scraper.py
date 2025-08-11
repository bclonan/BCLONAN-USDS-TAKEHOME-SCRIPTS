import os
import re
import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests
import xml.etree.ElementTree as ET
from tqdm import tqdm

from .metadata import MetadataExtractor
from .utils import calculate_checksum, load_checksum_db, save_checksum_db

logger = logging.getLogger(__name__)


class ECFRScraper:
    """Enhanced scraper for ECFR data with support for various file types and metadata extraction"""

    def __init__(self, base_url: str = "https://www.govinfo.gov/bulkdata/ECFR", output_dir: str = "./data"):
        self.base_url = base_url
        self.output_dir = output_dir
        self.session = requests.Session()
        self.checksum_db = load_checksum_db()
        self.metadata_extractor = MetadataExtractor()
        os.makedirs(output_dir, exist_ok=True)

    def get_resource_file(self, resource_name: str):
        """Download a resource file with checksum verification and metadata extraction"""
        resource_url = f"{self.base_url}/{resource_name}"
        resource_path = os.path.join(self.output_dir, resource_name)

        if os.path.exists(resource_path):
            existing_checksum = calculate_checksum(file_path=resource_path)
            if existing_checksum == self.checksum_db.get(resource_name):
                logger.info(f"Resource {resource_name} unchanged. Skipping download.")
                return resource_path

        try:
            logger.info(f"Downloading resource {resource_name} from {resource_url}")
            response = self.session.get(resource_url)
            response.raise_for_status()

            with open(resource_path, "wb") as f:
                f.write(response.content)

            new_checksum = calculate_checksum(file_path=resource_path)
            self.checksum_db[resource_name] = new_checksum

            metadata = self.metadata_extractor.extract(resource_path)
            metadata_path = f"{resource_path}.metadata.json"
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Downloaded and saved: {resource_path}")
            return resource_path
        except requests.RequestException as e:
            logger.error(f"Failed to download resource {resource_name}: {e}")
            return None

    def get_available_titles(self):
        return list(range(1, 51))

    def download_title_xml(self, title_number: int, output_dir: str | None = None):
        if output_dir is None:
            output_dir = self.output_dir

        os.makedirs(output_dir, exist_ok=True)
        url = f"{self.base_url}/title-{title_number}/ECFR-title{title_number}.xml"
        output_path = os.path.join(output_dir, f"title{title_number}.xml")

        if os.path.exists(output_path):
            existing_checksum = calculate_checksum(file_path=output_path)
            if existing_checksum == self.checksum_db.get(f"title{title_number}.xml"):
                logger.info(f"Title {title_number} unchanged. Skipping download.")
                return output_path

        max_title = 50
        current_title = title_number

        while current_title <= max_title:
            try:
                logger.info(f"Attempting to download title {current_title} from {url}")
                response = self.session.get(url)
                response.raise_for_status()

                with open(output_path, "wb") as f:
                    f.write(response.content)

                new_checksum = calculate_checksum(file_path=output_path)
                self.checksum_db[f"title{current_title}.xml"] = new_checksum

                metadata = self.metadata_extractor.extract(output_path)
                metadata_path = f"{output_path}.metadata.json"
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)

                logger.info(f"Downloaded and saved: {output_path}")
                return output_path
            except requests.RequestException as e:
                logger.warning(
                    f"Title {current_title} not available. Trying next title. Error: {e}"
                )
                current_title += 1
                url = f"{self.base_url}/title-{current_title}/ECFR-title{current_title}.xml"
                output_path = os.path.join(output_dir, f"title{current_title}.xml")

        logger.error(f"Failed to download any titles starting from {title_number}.")
        return None

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

            for part in root.findall(".//DIV6"):
                part_info = {
                    "part_number": self._safe_get_text(part, "./N"),
                    "part_name": self._safe_get_text(part, "./HEAD"),
                    "sections": [],
                }

                for section in part.findall(".//DIV8"):
                    section_text = ET.tostring(section, encoding="unicode", method="text").strip()
                    section_info = {
                        "section_number": self._safe_get_text(section, "./N"),
                        "section_name": self._safe_get_text(section, "./HEAD"),
                        "content": section_text,
                        "word_count": len(re.findall(r"\b\w+\b", section_text)),
                        "paragraph_count": len(section.findall(".//P")),
                    }
                    part_info["sections"].append(section_info)

                    title_info["stats"]["total_sections"] += 1
                    title_info["stats"]["word_count"] += section_info["word_count"]
                    title_info["stats"]["paragraph_count"] += section_info["paragraph_count"]

                title_info["parts"].append(part_info)

            all_text = "".join(root.itertext())
            title_info["lexical_analysis"] = self._perform_lexical_analysis(all_text)

            return title_info
        except Exception as e:
            logger.error(f"Error parsing {xml_path}: {e}")
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
            "avg_word_length": sum(len(word) for word in words) / word_count if word_count > 0 else 0,
            "top_words": Counter(words).most_common(20),
            "sentence_count": sentence_count,
            "avg_sentence_length": word_count / sentence_count if sentence_count > 0 else 0,
        }

    def export_to_json(self, data, output_path: str) -> bool:
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Exported to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
            return False

    def download_all_titles(self, output_dir: str | None = None, max_workers: int = 5):
        if output_dir is None:
            output_dir = self.output_dir

        titles = self.get_available_titles()
        downloaded_files: list[str] = []
        failed_titles: list[int] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.download_title_xml, title, output_dir): title for title in titles}

            with tqdm(total=len(futures), desc="Downloading Titles") as progress_bar:
                for future in futures:
                    title = futures[future]
                    try:
                        result = future.result()
                        if result:
                            downloaded_files.append(result)
                        else:
                            failed_titles.append(title)
                    except Exception as e:
                        logger.error(f"Download error for title {title}: {e}")
                        failed_titles.append(title)
                    finally:
                        progress_bar.update(1)

        save_checksum_db(self.checksum_db)

        logger.info(f"Downloaded {len(downloaded_files)} titles successfully")
        if failed_titles:
            logger.warning(f"Failed to download {len(failed_titles)} titles: {failed_titles}")

        return downloaded_files

    def process_downloaded_files(self, files):
        results = []

        for file_path in tqdm(files, desc="Processing Files"):
            try:
                data = self.parse_xml(file_path)
                if data:
                    json_path = file_path.replace(".xml", ".json")
                    self.export_to_json(data, json_path)

                    metadata = self.metadata_extractor.extract(file_path)
                    metadata_path = f"{file_path}.metadata.json"
                    with open(metadata_path, "w", encoding="utf-8") as f:
                        json.dump(metadata, f, indent=2)

                    results.append({
                        "file": file_path,
                        "json": json_path,
                        "metadata": metadata_path,
                        "success": True,
                    })
                else:
                    results.append({"file": file_path, "success": False, "error": "Failed to parse XML"})
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                results.append({"file": file_path, "success": False, "error": str(e)})

        return results
