import requests
import xml.etree.ElementTree as ET
import os
import argparse
import json
import hashlib
import zipfile
import re
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import logging
from collections import Counter
import mimetypes
from io import BytesIO

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("ecfr_scraper.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

CHECKSUM_DB_PATH = "checksums.json"

class MetadataExtractor:
    """Class to extract and parse metadata from various file types"""
    
    def __init__(self):
        self.transformers = {
            'xml': self.extract_xml_metadata,
            'pdf': self.extract_pdf_metadata,
            'zip': self.extract_zip_metadata,
            'txt': self.extract_text_metadata,
            'default': self.extract_default_metadata
        }
    
    def extract(self, file_path):
        """Extract metadata based on file type"""
        ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        transformer = self.transformers.get(ext, self.transformers['default'])
        return transformer(file_path)
    
    def extract_xml_metadata(self, file_path):
        """Extract metadata from XML files"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            metadata = {
                'root_tag': root.tag,
                'namespaces': root.nsmap if hasattr(root, 'nsmap') else {},
                'child_elements': [child.tag for child in root],
                'element_count': self._count_elements(root),
                'word_stats': self._analyze_text_content(root)
            }
            return metadata
        except Exception as e:
            logger.error(f"Error extracting XML metadata from {file_path}: {e}")
            return {'error': str(e)}

    def extract_pdf_metadata(self, file_path):
        """Extract metadata from PDF files"""
        # Placeholder for PDF metadata extraction
        # Would typically use a library like PyPDF2 or pdfminer
        return {'file_type': 'pdf', 'path': file_path}
    
    def extract_zip_metadata(self, file_path):
        """Extract metadata from ZIP files including any contained graphics"""
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                files = zip_ref.namelist()
                image_files = [f for f in files if self._is_image_file(f)]
                return {
                    'file_type': 'zip',
                    'file_count': len(files),
                    'contains_images': len(image_files) > 0,
                    'image_files': image_files,
                    'other_files': [f for f in files if f not in image_files]
                }
        except Exception as e:
            logger.error(f"Error extracting ZIP metadata from {file_path}: {e}")
            return {'error': str(e)}
    
    def extract_text_metadata(self, file_path):
        """Extract metadata from text files"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            word_stats = self._analyze_text(content)
            return {
                'file_type': 'text',
                'word_stats': word_stats
            }
        except Exception as e:
            logger.error(f"Error extracting text metadata from {file_path}: {e}")
            return {'error': str(e)}
    
    def extract_default_metadata(self, file_path):
        """Default metadata extractor for unsupported file types"""
        return {
            'file_type': 'unknown',
            'path': file_path,
            'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
        }
    
    def _count_elements(self, element):
        """Count elements in an XML tree recursively"""
        count = 1
        for child in element:
            count += self._count_elements(child)
        return count
    
    def _analyze_text_content(self, element):
        """Analyze text content of XML elements"""
        text = "".join(element.itertext()) if hasattr(element, 'itertext') else ""
        return self._analyze_text(text)
    
    def _analyze_text(self, text):
        """Analyze text content for word statistics"""
        words = re.findall(r'\b\w+\b', text.lower())
        word_count = len(words)
        word_freq = Counter(words).most_common(20)
        return {
            'word_count': word_count,
            'unique_word_count': len(set(words)),
            'top_words': word_freq,
            'avg_word_length': sum(len(word) for word in words) / word_count if word_count > 0 else 0
        }
    
    def _is_image_file(self, filename):
        """Check if a file is an image based on extension"""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type and mime_type.startswith('image')


def calculate_checksum(file_path=None, data=None, algorithm="sha256"):
    """Calculate checksum for a file or data"""
    hash_func = getattr(hashlib, algorithm)()
    if file_path and os.path.exists(file_path):
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hash_func.update(chunk)
    elif data:
        hash_func.update(data if isinstance(data, bytes) else data.encode('utf-8'))
    else:
        raise ValueError("Either file_path or data must be provided")
    return hash_func.hexdigest()

def load_checksum_db():
    """Load checksum database from file"""
    if os.path.exists(CHECKSUM_DB_PATH):
        try:
            with open(CHECKSUM_DB_PATH, "r") as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in checksum file. Resetting. Error: {e}")
            return {}
    return {}

def save_checksum_db(checksum_db):
    """Save checksum database to file"""
    with open(CHECKSUM_DB_PATH, "w") as f:
        json.dump(checksum_db, f, indent=2)

class ECFRScraper:
    """Enhanced scraper for ECFR data with support for various file types and metadata extraction"""
    
    def __init__(self, base_url="https://www.govinfo.gov/bulkdata/ECFR", output_dir="./data"):
        self.base_url = base_url
        self.output_dir = output_dir
        self.session = requests.Session()
        self.checksum_db = load_checksum_db()
        self.metadata_extractor = MetadataExtractor()
        os.makedirs(output_dir, exist_ok=True)
    
    def get_resource_file(self, resource_name):
        """Download a resource file with checksum verification and metadata extraction"""
        resource_url = f"{self.base_url}/{resource_name}"
        resource_path = os.path.join(self.output_dir, resource_name)
        
        # Check if we already have a valid file
        if os.path.exists(resource_path):
            existing_checksum = calculate_checksum(file_path=resource_path)
            if existing_checksum == self.checksum_db.get(resource_name):
                logger.info(f"Resource {resource_name} unchanged. Skipping download.")
                return resource_path

        try:
            logger.info(f"Downloading resource {resource_name} from {resource_url}")
            response = self.session.get(resource_url)
            response.raise_for_status()
            
            # Save content and calculate checksum
            with open(resource_path, 'wb') as f:
                f.write(response.content)
            
            new_checksum = calculate_checksum(file_path=resource_path)
            self.checksum_db[resource_name] = new_checksum
            
            # Extract and store metadata
            metadata = self.metadata_extractor.extract(resource_path)
            metadata_path = f"{resource_path}.metadata.json"
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Downloaded and saved: {resource_path}")
            return resource_path
        except requests.RequestException as e:
            logger.error(f"Failed to download resource {resource_name}: {e}")
            return None
    
    def get_available_titles(self):
        """Get available ECFR titles"""
        return list(range(1, 51))  # Titles 1–50
    
    def download_title_xml(self, title_number, output_dir=None):
        """Download an ECFR title XML with advanced error handling and retry logic"""
        if output_dir is None:
            output_dir = self.output_dir
            
        os.makedirs(output_dir, exist_ok=True)
        url = f"{self.base_url}/title-{title_number}/ECFR-title{title_number}.xml"
        output_path = os.path.join(output_dir, f"title{title_number}.xml")
        
        # Check if file exists and is valid
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
                
                # Save content
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                
                # Calculate and store checksum
                new_checksum = calculate_checksum(file_path=output_path)
                self.checksum_db[f"title{current_title}.xml"] = new_checksum
                
                # Extract and store metadata
                metadata = self.metadata_extractor.extract(output_path)
                metadata_path = f"{output_path}.metadata.json"
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
                
                logger.info(f"Downloaded and saved: {output_path}")
                return output_path
            except requests.RequestException as e:
                logger.warning(f"Title {current_title} not available. Trying next title. Error: {e}")
                current_title += 1
                url = f"{self.base_url}/title-{current_title}/ECFR-title{current_title}.xml"
                output_path = os.path.join(output_dir, f"title{current_title}.xml")
        
        logger.error(f"Failed to download any titles starting from {title_number}.")
        return None
    
    def parse_xml(self, xml_path):
        """Parse XML file with enhanced error handling and content analysis"""
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Basic information
            title_info = {
                "title_number": self._safe_get_text(root, ".//TITL"),
                "title_name": self._safe_get_text(root, ".//HEAD"),
                "parts": [],
                "stats": {
                    "total_sections": 0,
                    "word_count": 0,
                    "paragraph_count": 0
                }
            }
            
            # Process parts
            for part in root.findall(".//DIV6"):
                part_info = {
                    "part_number": self._safe_get_text(part, "./N"),
                    "part_name": self._safe_get_text(part, "./HEAD"),
                    "sections": []
                }
                
                # Process sections
                for section in part.findall(".//DIV8"):
                    section_text = ET.tostring(section, encoding='unicode', method='text').strip()
                    section_info = {
                        "section_number": self._safe_get_text(section, "./N"),
                        "section_name": self._safe_get_text(section, "./HEAD"),
                        "content": section_text,
                        "word_count": len(re.findall(r'\b\w+\b', section_text)),
                        "paragraph_count": len(section.findall(".//P"))
                    }
                    part_info["sections"].append(section_info)
                    
                    # Update statistics
                    title_info["stats"]["total_sections"] += 1
                    title_info["stats"]["word_count"] += section_info["word_count"]
                    title_info["stats"]["paragraph_count"] += section_info["paragraph_count"]
                
                title_info["parts"].append(part_info)
            
            # Add lexical analysis
            all_text = "".join(root.itertext())
            title_info["lexical_analysis"] = self._perform_lexical_analysis(all_text)
            
            return title_info
        except Exception as e:
            logger.error(f"Error parsing {xml_path}: {e}")
            return None
    
    def _safe_get_text(self, element, xpath):
        """Safely get text from an element"""
        found = element.find(xpath)
        return found.text if found is not None else None
    
    def _perform_lexical_analysis(self, text):
        """Perform lexical analysis on text content"""
        words = re.findall(r'\b\w+\b', text.lower())
        word_count = len(words)
        sentences = re.split(r'[.!?]+', text)
        sentence_count = len([s for s in sentences if s.strip()])
        
        return {
            "total_words": word_count,
            "unique_words": len(set(words)),
            "avg_word_length": sum(len(word) for word in words) / word_count if word_count > 0 else 0,
            "top_words": Counter(words).most_common(20),
            "sentence_count": sentence_count,
            "avg_sentence_length": word_count / sentence_count if sentence_count > 0 else 0
        }
    
    def export_to_json(self, data, output_path):
        """Export data to JSON with enhanced error handling"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Exported to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
            return False
    
    def download_all_titles(self, output_dir=None, max_workers=5):
        """Download all titles with enhanced progress tracking"""
        if output_dir is None:
            output_dir = self.output_dir
            
        titles = self.get_available_titles()
        downloaded_files = []
        failed_titles = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.download_title_xml, title, output_dir): title
                for title in titles
            }
            
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
        
        # Save checksum database
        save_checksum_db(self.checksum_db)
        
        # Report results
        logger.info(f"Downloaded {len(downloaded_files)} titles successfully")
        if failed_titles:
            logger.warning(f"Failed to download {len(failed_titles)} titles: {failed_titles}")
        
        return downloaded_files
    
    def process_downloaded_files(self, files):
        """Process downloaded files and generate comprehensive metadata"""
        results = []
        
        for file_path in tqdm(files, desc="Processing Files"):
            try:
                # Parse XML
                data = self.parse_xml(file_path)
                if data:
                    # Export to JSON
                    json_path = file_path.replace(".xml", ".json")
                    self.export_to_json(data, json_path)
                    
                    # Generate detailed metadata
                    metadata = self.metadata_extractor.extract(file_path)
                    metadata_path = f"{file_path}.metadata.json"
                    with open(metadata_path, 'w') as f:
                        json.dump(metadata, f, indent=2)
                    
                    results.append({
                        "file": file_path,
                        "json": json_path,
                        "metadata": metadata_path,
                        "success": True
                    })
                else:
                    results.append({
                        "file": file_path,
                        "success": False,
                        "error": "Failed to parse XML"
                    })
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                results.append({
                    "file": file_path,
                    "success": False,
                    "error": str(e)
                })
        
        return results


def main():
    parser = argparse.ArgumentParser(description="Download and parse ECFR XML from govinfo.gov")
    parser.add_argument("--title", type=int, help="Title number to download and parse")
    parser.add_argument("--all", action="store_true", help="Download and parse all titles")
    parser.add_argument("--output", type=str, default="./data", help="Output directory for files")
    parser.add_argument("--workers", type=int, default=5, help="Number of worker threads for parallel downloads")
    parser.add_argument("--metadata-only", action="store_true", help="Only generate metadata without parsing XML")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Set logging level based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    scraper = ECFRScraper(output_dir=args.output)
    
    if args.all:
        files = scraper.download_all_titles(args.output, max_workers=args.workers)
        if not args.metadata_only:
            results = scraper.process_downloaded_files(files)
            summary_path = os.path.join(args.output, "processing_summary.json")
            with open(summary_path, 'w') as f:
                json.dump(results, f, indent=2)
            logger.info(f"Processing summary saved to {summary_path}")
    elif args.title:
        xml_path = scraper.download_title_xml(args.title, args.output)
        if xml_path and not args.metadata_only:
            data = scraper.parse_xml(xml_path)
            if data:
                scraper.export_to_json(data, xml_path.replace(".xml", ".json"))
        save_checksum_db(scraper.checksum_db)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()