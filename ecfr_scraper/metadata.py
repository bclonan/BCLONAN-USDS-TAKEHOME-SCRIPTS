import os
import re
import json
import zipfile
import mimetypes
import logging
from collections import Counter
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Class to extract and parse metadata from various file types"""

    def __init__(self):
        self.transformers = {
            "xml": self.extract_xml_metadata,
            "pdf": self.extract_pdf_metadata,
            "zip": self.extract_zip_metadata,
            "txt": self.extract_text_metadata,
            "default": self.extract_default_metadata,
        }

    def extract(self, file_path: str):
        """Extract metadata based on file type"""
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        transformer = self.transformers.get(ext, self.transformers["default"])
        return transformer(file_path)

    def extract_xml_metadata(self, file_path: str):
        """Extract metadata from XML files"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            metadata = {
                "root_tag": root.tag,
                "namespaces": getattr(root, "nsmap", {}) if hasattr(root, "nsmap") else {},
                "child_elements": [child.tag for child in root],
                "element_count": self._count_elements(root),
                "word_stats": self._analyze_text_content(root),
            }
            return metadata
        except Exception as e:
            logger.error(f"Error extracting XML metadata from {file_path}: {e}")
            return {"error": str(e)}

    def extract_pdf_metadata(self, file_path: str):
        """Extract metadata from PDF files (placeholder)."""
        return {"file_type": "pdf", "path": file_path}

    def extract_zip_metadata(self, file_path: str):
        """Extract metadata from ZIP files including any contained graphics"""
        try:
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                files = zip_ref.namelist()
                image_files = [f for f in files if self._is_image_file(f)]
                return {
                    "file_type": "zip",
                    "file_count": len(files),
                    "contains_images": len(image_files) > 0,
                    "image_files": image_files,
                    "other_files": [f for f in files if f not in image_files],
                }
        except Exception as e:
            logger.error(f"Error extracting ZIP metadata from {file_path}: {e}")
            return {"error": str(e)}

    def extract_text_metadata(self, file_path: str):
        """Extract metadata from text files"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            word_stats = self._analyze_text(content)
            return {"file_type": "text", "word_stats": word_stats}
        except Exception as e:
            logger.error(f"Error extracting text metadata from {file_path}: {e}")
            return {"error": str(e)}

    def extract_default_metadata(self, file_path: str):
        """Default metadata extractor for unsupported file types"""
        return {
            "file_type": "unknown",
            "path": file_path,
            "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        }

    def _count_elements(self, element) -> int:
        count = 1
        for child in element:
            count += self._count_elements(child)
        return count

    def _analyze_text_content(self, element):
        text = "".join(element.itertext()) if hasattr(element, "itertext") else ""
        return self._analyze_text(text)

    def _analyze_text(self, text: str):
        words = re.findall(r"\b\w+\b", text.lower())
        word_count = len(words)
        word_freq = Counter(words).most_common(20)
        return {
            "word_count": word_count,
            "unique_word_count": len(set(words)),
            "top_words": word_freq,
            "avg_word_length": sum(len(word) for word in words) / word_count if word_count > 0 else 0,
        }

    def _is_image_file(self, filename: str) -> bool:
        mime_type, _ = mimetypes.guess_type(filename)
        return bool(mime_type and mime_type.startswith("image"))
