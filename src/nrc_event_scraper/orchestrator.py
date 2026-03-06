"""Orchestrator: coordinates fetch → archive → detect → parse → store.

Three modes:
- Backfill: discover all year indexes → find all daily pages → fetch/parse any pending
- Incremental: check current year index → fetch/parse only new pages
- Reparse: re-parse all archived HTML without re-fetching (for parser bug fixes)

Idempotent via SQLite state: pages already fetched/parsed are skipped.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from nrc_event_scraper.config import Settings
from nrc_event_scraper.db import ScraperDB
from nrc_event_scraper.parser.detect import detect_format
from nrc_event_scraper.parser.legacy_parser import parse_legacy_page
from nrc_event_scraper.parser.modern_parser import parse_modern_page
from nrc_event_scraper.parser.plaintext_parser import parse_plaintext_page
from nrc_event_scraper.scraper.client import NRCClient
from nrc_event_scraper.scraper.index_scraper import (
    extract_daily_page_urls,
    url_to_report_date,
)
from nrc_event_scraper.storage.html_archive import HTMLArchive
from nrc_event_scraper.storage.jsonl_writer import JSONLWriter

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates the full scrape pipeline."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.db = ScraperDB(self.settings.db_path)
        self.archive = HTMLArchive(self.settings.html_dir)
        self.writer = JSONLWriter(self.settings.events_dir)

    async def backfill(
        self,
        years: list[int] | None = None,
        force: bool = False,
    ) -> dict:
        """Backfill: discover all pages for given years, fetch and parse pending ones.

        Args:
            years: Specific years to backfill. None = all years in config range.
            force: If True, reset already-processed pages and re-fetch.

        Returns summary stats dict.
        """
        if years is None:
            years = list(range(self.settings.start_year, self.settings.end_year + 1))

        run_id = self.db.start_run("backfill")
        stats = {
            "pages_discovered": 0, "pages_fetched": 0,
            "pages_parsed": 0, "events_found": 0, "errors": 0,
        }

        try:
            async with NRCClient(self.settings) as client:
                # Phase 1: Discover daily page URLs from year indexes
                for year in years:
                    logger.info("Discovering pages for year %d", year)
                    discovered = await self._discover_year(client, year)
                    stats["pages_discovered"] += discovered

                    if force:
                        for page in self.db.get_all_pages(year):
                            self.db.reset_page(page["url"])

                # Phase 2: Fetch pending pages
                for year in years:
                    pending = self.db.get_pending_pages(year)
                    logger.info("Year %d: %d pages to fetch", year, len(pending))

                    for page in pending:
                        success = await self._fetch_page(client, page["url"])
                        if success:
                            stats["pages_fetched"] += 1
                        else:
                            stats["errors"] += 1

                # Phase 3: Parse fetched pages
                for year in years:
                    unparsed = self.db.get_fetched_unparsed(year)
                    logger.info("Year %d: %d pages to parse", year, len(unparsed))

                    for page in unparsed:
                        events_count = self._parse_page(page["url"], year)
                        if events_count >= 0:
                            stats["pages_parsed"] += 1
                            stats["events_found"] += events_count
                        else:
                            stats["errors"] += 1

            self.db.finish_run(
                run_id,
                pages_fetched=stats["pages_fetched"],
                pages_parsed=stats["pages_parsed"],
                events_found=stats["events_found"],
                errors=stats["errors"],
            )
        except Exception as e:
            logger.error("Backfill failed: %s", e)
            self.db.finish_run(run_id, errors=stats["errors"], status="failed")
            raise

        return stats

    async def incremental(self) -> dict:
        """Incremental: check current year for new pages, fetch and parse them."""
        current_year = datetime.now(timezone.utc).year
        return await self.backfill(years=[current_year])

    def reparse(self, years: list[int] | None = None) -> dict:
        """Re-parse all archived HTML using current parser code.

        Skips fetch phase entirely. Rewrites JSONL files from scratch.
        Use after fixing parser bugs to regenerate event data from archived HTML.

        Args:
            years: Specific years to reparse. None = all years with archived HTML.

        Returns summary stats dict.
        """
        if years is None:
            years = self._detect_archived_years()

        run_id = self.db.start_run("reparse")
        stats = {
            "pages_reparsed": 0, "events_found": 0,
            "errors": 0, "years_processed": 0,
        }

        try:
            for year in years:
                logger.info("Reparsing year %d", year)
                year_stats = self._reparse_year(year)
                stats["pages_reparsed"] += year_stats["pages"]
                stats["events_found"] += year_stats["events"]
                stats["errors"] += year_stats["errors"]
                stats["years_processed"] += 1

            self.db.finish_run(
                run_id,
                pages_parsed=stats["pages_reparsed"],
                events_found=stats["events_found"],
                errors=stats["errors"],
            )
        except Exception as e:
            logger.error("Reparse failed: %s", e)
            self.db.finish_run(run_id, errors=stats["errors"], status="failed")
            raise

        return stats

    def _detect_archived_years(self) -> list[int]:
        """Scan the HTML archive directory for year subdirectories."""
        if not self.archive.html_dir.exists():
            return []
        years = []
        for child in sorted(self.archive.html_dir.iterdir()):
            if child.is_dir() and child.name.isdigit():
                years.append(int(child.name))
        return years

    def _reparse_year(self, year: int) -> dict:
        """Reparse all archived HTML for a single year.

        Collects all events in memory, then does a single atomic JSONL rewrite.
        """
        year_stats = {"pages": 0, "events": 0, "errors": 0}

        # Reset DB state for this year
        reset_count = self.db.reset_pages_for_reparse(year)
        logger.info("Year %d: reset %d pages to fetched status", year, reset_count)

        # Clear old events from DB for this year
        cleared = self.db.clear_events_for_year(year)
        logger.info("Year %d: cleared %d old event rows from DB", year, cleared)

        # Get archived URLs from disk (source of truth)
        archived_urls = self.archive.list_archived_urls(year, self.settings.nrc_base_url)
        if not archived_urls:
            logger.warning("Year %d: no archived HTML files found", year)
            return year_stats

        # Ensure all archived pages exist in the DB
        for url in archived_urls:
            report_date = url_to_report_date(url)
            self.db.upsert_page(url, year, report_date)
            page = self.db.get_page(url)
            if page and page["status"] == "pending":
                html = self.archive.load(url)
                fmt = detect_format(html) if html else None
                self.db.mark_page_fetched(url, html_sha256="from-archive", html_format=fmt)

        # Parse each page, collecting all events
        all_events: list = []
        now = datetime.now(timezone.utc)

        for url in archived_urls:
            count = self._parse_page_for_reparse(url, year, all_events, now)
            if count >= 0:
                year_stats["pages"] += 1
                year_stats["events"] += count
            else:
                year_stats["errors"] += 1

        # Atomic rewrite of the year's JSONL
        written = self.writer.rewrite_events(all_events, year)
        logger.info(
            "Year %d: reparsed %d pages, %d events (%d unique written)",
            year, year_stats["pages"], year_stats["events"], written,
        )

        return year_stats

    def _parse_page_for_reparse(
        self, url: str, year: int, events_acc: list, now: datetime
    ) -> int:
        """Parse a single archived page for reparse, accumulating events.

        Returns event count or -1 on error.
        """
        html = self.archive.load(url)
        if not html:
            self.db.mark_page_error(url, "Archived HTML not found")
            return -1

        fmt = detect_format(html)

        try:
            if fmt == "modern":
                report = parse_modern_page(html, page_url=url)
            elif fmt == "legacy":
                report = parse_legacy_page(html, page_url=url)
            elif fmt == "plaintext":
                report = parse_plaintext_page(html, page_url=url)
            elif fmt == "empty":
                self.db.mark_page_parsed(url, event_count=0, html_format="empty")
                return 0
            else:
                logger.error("Unknown format for %s: %s", url, fmt)
                self.db.mark_page_error(url, f"Unknown format: {fmt}")
                return -1
        except Exception as e:
            logger.error("Parse error for %s: %s", url, e, exc_info=True)
            self.db.mark_page_error(url, f"Parse error: {e}")
            return -1

        for event in report.events:
            event.scraped_at = now

        events_acc.extend(report.events)

        for event in report.events:
            self.db.upsert_event(event.event_number, url, event.category.value)

        self.db.mark_page_parsed(url, event_count=len(report.events), html_format=fmt)

        if report.parse_errors:
            logger.warning("Parse warnings for %s: %s", url, report.parse_errors)

        return len(report.events)

    async def _discover_year(self, client: NRCClient, year: int) -> int:
        """Fetch year index and register discovered daily page URLs in the DB."""
        index_url = f"{self.settings.nrc_base_url}/{year}/index.html"

        try:
            html, status, _ = await client.fetch(index_url)
        except Exception as e:
            logger.error("Failed to fetch year index %d: %s", year, e)
            return 0

        if status == 404 or not html:
            logger.warning("Year index %d returned %d", year, status)
            return 0

        urls = extract_daily_page_urls(html, self.settings.nrc_base_url, year)
        for url in urls:
            report_date = url_to_report_date(url)
            self.db.upsert_page(url, year, report_date)

        logger.info("Year %d: discovered %d daily pages", year, len(urls))
        return len(urls)

    async def _fetch_page(self, client: NRCClient, url: str) -> bool:
        """Fetch a single page, archive it, and update DB status."""
        try:
            html, status, sha256 = await client.fetch(url)

            if status == 404 or not html:
                logger.warning("Fetch failed for %s: HTTP %d", url, status)
                self.db.mark_page_error(url, f"HTTP {status}")
                return False

            # Archive raw HTML before parsing
            self.archive.save(html, url)

            # Detect format
            fmt = detect_format(html)
            self.db.mark_page_fetched(url, sha256, fmt)
            return True

        except Exception as e:
            logger.error("Failed to fetch %s: %s", url, e)
            self.db.mark_page_error(url, str(e))
            return False

    def _parse_page(self, url: str, year: int) -> int:
        """Parse an archived page and store events. Returns event count or -1 on error."""
        html = self.archive.load(url)
        if not html:
            self.db.mark_page_error(url, "Archived HTML not found")
            return -1

        fmt = detect_format(html)

        try:
            if fmt == "modern":
                report = parse_modern_page(html, page_url=url)
            elif fmt == "legacy":
                report = parse_legacy_page(html, page_url=url)
            elif fmt == "plaintext":
                report = parse_plaintext_page(html, page_url=url)
            elif fmt == "empty":
                self.db.mark_page_parsed(url, event_count=0, html_format="empty")
                return 0
            else:
                logger.error("Unknown format for %s: %s", url, fmt)
                self.db.mark_page_error(url, f"Unknown format: {fmt}")
                return -1
        except Exception as e:
            logger.error("Parse error for %s: %s", url, e, exc_info=True)
            self.db.mark_page_error(url, f"Parse error: {e}")
            return -1

        # Stamp scraped_at on all events
        now = datetime.now(timezone.utc)
        for event in report.events:
            event.scraped_at = now

        # Store events
        written = self.writer.write_events(report.events, year)

        # Register events in DB
        for event in report.events:
            self.db.upsert_event(event.event_number, url, event.category.value)

        self.db.mark_page_parsed(url, event_count=len(report.events), html_format=fmt)

        if report.parse_errors:
            logger.warning("Parse warnings for %s: %s", url, report.parse_errors)

        logger.info(
            "Parsed %s: %d events (%d new written)", url, len(report.events), written
        )
        return len(report.events)
