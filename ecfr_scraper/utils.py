import json
import hashlib
import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Optional, Dict, Union

CHECKSUM_DB_PATH = "checksums.json"
LOG_FILE_PATH = "ecfr_scraper.log"


def setup_logging(verbose: bool = False) -> None:
    """Configure root logging with console and rotating file handlers."""
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger()
    logger.setLevel(level)

    # Clear existing handlers to honor verbosity changes
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)

    fh = RotatingFileHandler(LOG_FILE_PATH, maxBytes=1_000_000, backupCount=3)
    fh.setLevel(level)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)


def calculate_checksum(file_path: Optional[str] = None, data: Optional[Union[bytes, str]] = None, algorithm: str = "sha256") -> str:
    """Calculate checksum for a file or data."""
    hash_func = getattr(hashlib, algorithm)()
    if file_path and os.path.exists(file_path):
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                hash_func.update(chunk)
    elif data is not None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        hash_func.update(data)
    else:
        raise ValueError("Either file_path or data must be provided")
    return hash_func.hexdigest()


def load_checksum_db(path: str = CHECKSUM_DB_PATH) -> Dict[str, str]:
    """Load checksum database from file."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
        except json.JSONDecodeError:
            logging.getLogger(__name__).warning("Invalid JSON in checksum file. Resetting.")
            return {}
    return {}


def save_checksum_db(checksum_db: Dict[str, str], path: str = CHECKSUM_DB_PATH) -> None:
    """Save checksum database to file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(checksum_db, f, indent=2)
