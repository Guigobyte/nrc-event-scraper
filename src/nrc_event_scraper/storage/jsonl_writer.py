"""Year-partitioned JSONL output writer.

Writes events to data/events/YYYY.jsonl, one JSON object per line.
Appends to existing files for idempotent re-runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from nrc_event_scraper.models import NRCEvent


class JSONLWriter:
    """Writes NRCEvent objects to year-partitioned JSONL files."""

    def __init__(self, events_dir: Path) -> None:
        self.events_dir = events_dir
        events_dir.mkdir(parents=True, exist_ok=True)

    def write_events(self, events: list[NRCEvent], year: int) -> int:
        """Append events to the JSONL file for the given year.

        Returns the number of events written.
        """
        if not events:
            return 0

        path = self.events_dir / f"{year}.jsonl"
        existing_numbers = self._load_existing_event_numbers(path)

        written = 0
        with open(path, "a") as f:
            for event in events:
                if event.event_number in existing_numbers:
                    continue
                line = event.model_dump_json()
                f.write(line + "\n")
                existing_numbers.add(event.event_number)
                written += 1

        return written

    def _load_existing_event_numbers(self, path: Path) -> set[int]:
        """Load event numbers already in a JSONL file for dedup."""
        numbers: set[int] = set()
        if not path.exists():
            return numbers
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    numbers.add(data["event_number"])
                except (json.JSONDecodeError, KeyError):
                    continue
        return numbers

    def rewrite_events(self, events: list[NRCEvent], year: int) -> int:
        """Rewrite the JSONL file for a year from scratch.

        Replaces the entire file. Deduplicates by event_number
        (last occurrence wins to match chronological scrape order).
        Returns the number of unique events written.
        """
        path = self.events_dir / f"{year}.jsonl"

        # Deduplicate: last occurrence wins
        seen: dict[int, NRCEvent] = {}
        for event in events:
            seen[event.event_number] = event

        with open(path, "w") as f:
            for event in seen.values():
                f.write(event.model_dump_json() + "\n")

        return len(seen)

    def read_events(self, year: int) -> list[NRCEvent]:
        """Read all events from a year's JSONL file."""
        path = self.events_dir / f"{year}.jsonl"
        if not path.exists():
            return []
        events = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(NRCEvent.model_validate_json(line))
                except Exception:
                    continue
        return events
