"""HTML archive: gzip raw HTML snapshots for reprocessing.

Saves raw HTML before any parsing, so format drift never loses data.
Files are stored as data/html/YYYY/YYYYMMDDen.html.gz with sha256 tracking.
"""

from __future__ import annotations

import gzip
import hashlib
import re
from pathlib import Path


class HTMLArchive:
    """Archives raw HTML pages as gzipped files."""

    def __init__(self, html_dir: Path) -> None:
        self.html_dir = html_dir

    def save(self, html: str, url: str) -> tuple[Path, str]:
        """Save HTML content to gzipped archive.

        Returns (file_path, sha256_hash).
        """
        year, filename = self._url_to_path_parts(url)
        year_dir = self.html_dir / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        gz_path = year_dir / f"{filename}.html.gz"
        content_bytes = html.encode("utf-8")
        sha256 = hashlib.sha256(content_bytes).hexdigest()

        with gzip.open(gz_path, "wb") as f:
            f.write(content_bytes)

        return gz_path, sha256

    def load(self, url: str) -> str | None:
        """Load archived HTML for a URL, or None if not archived."""
        year, filename = self._url_to_path_parts(url)
        gz_path = self.html_dir / str(year) / f"{filename}.html.gz"
        if not gz_path.exists():
            return None
        with gzip.open(gz_path, "rb") as f:
            return f.read().decode("utf-8")

    def exists(self, url: str) -> bool:
        year, filename = self._url_to_path_parts(url)
        gz_path = self.html_dir / str(year) / f"{filename}.html.gz"
        return gz_path.exists()

    def list_archived_urls(self, year: int, base_url: str) -> list[str]:
        """List all archived URLs for a year, reconstructed from filenames.

        Returns sorted list of URLs like '{base_url}/2026/20260303en'.
        """
        year_dir = self.html_dir / str(year)
        if not year_dir.exists():
            return []
        urls = []
        for gz_file in sorted(year_dir.glob("*.html.gz")):
            # 20260303en.html.gz -> 20260303en
            filename = gz_file.stem.removesuffix(".html")
            urls.append(f"{base_url}/{year}/{filename}")
        return urls

    def _url_to_path_parts(self, url: str) -> tuple[int, str]:
        """Extract year and filename from URL.

        URL: .../event/2026/20260303en -> (2026, '20260303en')
        """
        m = re.search(r"/(\d{4})/(\d{8}en)", url)
        if m:
            return int(m.group(1)), m.group(2)

        # Fallback: try to extract year from URL path
        m = re.search(r"/(\d{4})/", url)
        year = int(m.group(1)) if m else 0
        filename = url.rstrip("/").split("/")[-1]
        return year, filename
