"""Parser for plaintext NRC format (1999–2003, <pre> tag).

The oldest NRC pages embed event data as fixed-width ASCII text inside
a <pre> tag. Events are delimited by box-drawing characters (+---+, |...|).

Structure of each event block:
    +---...---+
    |Category                |Event Number: XXXXX  |
    +---...---+
    +---...---+
    | FACILITY: ...          |NOTIFICATION DATE: ...|
    | ...field rows...       |...date rows...       |
    +---...---+
                             EVENT TEXT
    +---...---+
    | text content...                               |
    +---...---+
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from nrc_event_scraper.models import DailyReport, NRCEvent
from nrc_event_scraper.parser.common import (
    normalize_whitespace,
    parse_category,
    parse_cfr_sections,
    parse_date,
    parse_reactor_units_from_rows,
    parse_time_with_tz,
)

logger = logging.getLogger(__name__)


def parse_plaintext_page(html: str, page_url: str = "") -> DailyReport:
    """Parse a plaintext-format NRC event notification page.

    Extracts the <pre> tag content and splits it into event blocks
    using the Event Number header pattern.
    """
    soup = BeautifulSoup(html, "lxml")
    report = DailyReport(page_url=page_url, html_format="plaintext")

    pre = soup.find("pre")
    if not pre:
        logger.warning("No <pre> tag found on %s", page_url)
        return report

    text = pre.get_text()

    # Extract report date from header
    date_match = re.search(
        r"Event Reports For\s+[\d/]+\s*-\s*(\d{2}/\d{2}/\d{4})", text
    )
    if date_match:
        report.report_date = parse_date(date_match.group(1))

    # Split into event blocks using the category/event-number header line
    # Each event starts with: |Category...|Event Number: XXXXX  |
    event_pattern = re.compile(
        r"^\|(.+?)\|Event Number:\s*(\d+)\s*\|",
        re.MULTILINE,
    )

    matches = list(event_pattern.finditer(text))
    for i, match in enumerate(matches):
        # Event block runs from this match to the next match (or end of text)
        block_start = match.start()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        # Include some context before the header (the +---+ border line)
        pre_context_start = text.rfind("\n+", 0, block_start)
        if pre_context_start >= 0:
            block_start = pre_context_start

        block = text[block_start:block_end]
        category_text = match.group(1).strip()
        event_number = int(match.group(2))

        try:
            event = _parse_event_block(block, event_number, category_text, page_url)
            event.report_date = report.report_date
            report.events.append(event)
        except Exception as e:
            logger.warning("Failed to parse plaintext event %d: %s", event_number, e)
            report.parse_errors.append(f"Event {event_number}: {e}")

    return report


def _parse_event_block(
    block: str, event_number: int, category_text: str, page_url: str
) -> NRCEvent:
    """Parse a single plaintext event block into an NRCEvent."""
    warnings: list[str] = []
    category = parse_category(category_text)

    event = NRCEvent(
        event_number=event_number,
        category=category,
        page_url=page_url,
        html_format="plaintext",
    )

    # Strip box-drawing characters and split into lines
    lines = block.split("\n")

    # Extract all field values from the pipe-delimited rows
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Lines starting with | contain field data in pipe-delimited columns
        # Lines starting with + may contain field data after a box border:
        #   e.g., "+---...---+EVENT TIME: 10:45[EST]|"
        if stripped.startswith("|"):
            content = stripped.strip("|")
        elif stripped.startswith("+") and re.search(r"\+[A-Z]", stripped):
            # Strip the +---+ prefix, then the trailing |
            content = re.sub(r"^\+[-+]+\+", "", stripped).strip("|").strip()
        else:
            continue

        if not content or content.startswith("-"):
            continue

        cols = _split_columns(content)
        for col in cols:
            _parse_field_text(col, event, warnings)

    # Extract reactor unit table if present
    reactor_rows = _extract_reactor_table(block)
    if reactor_rows:
        event.reactor_units = parse_reactor_units_from_rows(reactor_rows)

    # Extract event text
    event_text = _extract_event_text(block)
    if event_text:
        event.event_text = event_text

    # Extract persons from the right column
    persons = _extract_persons(block)
    if persons:
        event.persons_notified = persons

    # Extract CFR sections
    cfr_sections = _extract_cfr_sections(block)
    if cfr_sections:
        event.cfr_sections = cfr_sections

    event.parse_warnings = warnings
    return event


def _split_columns(content: str) -> list[str]:
    """Split a pipe-delimited row into columns, handling the two-column layout.

    Also handles continuation lines where a +---+ separator precedes a field:
    e.g., '+------------------------------------------------+EVENT TIME: 10:45[EST]'
    """
    # Strip any box-drawing prefix: +---...---+FIELD becomes FIELD
    content = re.sub(r"^\+[-+]+\+", "", content)

    # The plaintext format has two main columns separated by |
    parts = content.split("|")
    return [p.strip() for p in parts if p.strip()]


def _parse_field_text(text: str, event: NRCEvent, warnings: list[str]) -> None:
    """Parse a 'LABEL: VALUE' text fragment and assign to the event.

    Handles multi-field lines like "FACILITY: INDIAN POINT  REGION: 1  STATE: NY"
    by splitting on known label patterns before assignment.
    """
    text = normalize_whitespace(text)
    if not text or text.startswith("+") or text.startswith("-"):
        return

    # Skip header-like lines
    if text in ("PERSON", "ORGANIZATION", "PERSON          ORGANIZATION"):
        return

    # Split multi-field lines: "FACILITY: X  REGION: 1" -> individual assignments
    # Known labels that appear inline together
    known_labels = (
        "FACILITY", "REGION", "STATE", "UNIT", "RXTYPE", "RX TYPE",
        "REP ORG", "LICENSEE", "LICENSE#", "AGREEMENT", "DOCKET",
        "COUNTY", "CITY", "NOTIFICATION DATE", "NOTIFICATION TIME",
        "EVENT DATE", "EVENT TIME", "LAST UPDATE DATE",
        "EMERGENCY CLASS", "NRC NOTIFIED BY", "HQ OPS OFFICER",
        "10 CFR SECTION", "EVENT NUMBER",
    )
    label_pattern = "|".join(re.escape(lb) for lb in known_labels)
    # Split on label boundaries: look for LABEL: at word boundaries
    pairs = re.split(rf"(?<!\w)({label_pattern}):\s*", text, flags=re.IGNORECASE)

    # pairs = ['', 'FACILITY', 'INDIAN POINT', 'REGION', '1', 'STATE', 'NY']
    # Process as (label, value) pairs starting from index 1
    i = 1
    while i < len(pairs) - 1:
        label = pairs[i].strip()
        value = pairs[i + 1].strip()
        _assign_field(event, label, value)
        i += 2


def _assign_field(event: NRCEvent, label: str, value: str) -> None:
    """Map a label-value pair to the NRCEvent field."""
    label_lower = label.lower()

    field_map = {
        "facility": "facility",
        "region": "region",
        "state": "state",
        "unit": "unit",
        "rxtype": "rx_type",
        "rx type": "rx_type",
        "rep org": "rep_org",
        "licensee": "licensee",
        "license#": "license_number",
        "agreement": "agreement",
        "docket": "docket",
        "county": "county",
        "city": "city",
    }

    if label_lower in field_map:
        setattr(event, field_map[label_lower], value if value else None)
    elif label_lower == "notification date":
        event.notification_date = parse_date(value)
    elif label_lower == "notification time":
        time_str, tz = parse_time_with_tz(value)
        event.notification_time = time_str
        event.notification_timezone = tz
    elif label_lower == "event date":
        event.event_date = parse_date(value)
    elif label_lower == "event time":
        time_str, tz = parse_time_with_tz(value)
        event.event_time = time_str
        event.event_timezone = tz
    elif label_lower == "last update date":
        event.last_update_date = parse_date(value)
    elif label_lower == "emergency class":
        event.emergency_class = value
    elif label_lower in ("nrc notified by", "hq ops officer"):
        pass  # Not stored separately
    elif label_lower == "10 cfr section":
        pass  # Handled separately in _extract_cfr_sections
    elif label_lower == "event number":
        pass  # Already extracted from header


def _extract_event_text(block: str) -> str | None:
    """Extract the EVENT TEXT section from a plaintext block."""
    # Find "EVENT TEXT" header line
    m = re.search(r"EVENT TEXT\s*\n\+[-+]+\+\n", block)
    if not m:
        return None

    text_start = m.end()
    # Find the closing +---+ border
    closing = re.search(r"\n\+[-+]+\+", block[text_start:])
    if closing:
        text_block = block[text_start : text_start + closing.start()]
    else:
        text_block = block[text_start:]

    # Strip pipe characters and clean up
    lines = []
    for line in text_block.split("\n"):
        # Remove leading/trailing | and whitespace
        cleaned = line.strip().strip("|").strip()
        if cleaned:
            lines.append(cleaned)

    return "\n".join(lines) if lines else None


def _extract_reactor_table(block: str) -> list[list[str]]:
    """Extract reactor unit rows from the plaintext block.

    Looks for the UNIT/SCRAM CODE/RX CRIT header row pattern.
    """
    # Find reactor table header
    header_match = re.search(
        r"\|UNIT\s*\|SCRAM CODE\|RX CRIT\|INIT PWR\|",
        block,
    )
    if not header_match:
        return []

    # Find the data rows after the header separator
    after_header = block[header_match.end() :]
    # Skip the +---+---+ separator line
    sep_match = re.match(r"[^\n]*\n\+[-+|]+\+\n", after_header)
    if sep_match:
        data_start = sep_match.end()
    else:
        data_start = 0

    rows = []
    for line in after_header[data_start:].split("\n"):
        line = line.strip()
        if line.startswith("+"):
            break  # End of table
        if not line.startswith("|"):
            continue
        # Remove pipes and split
        content = line.strip("|")
        cells = [c.strip() for c in content.split("|") if c.strip()]
        # The plaintext format sometimes has cells with spaces that merge
        # Try splitting by fixed widths if pipe-split doesn't give enough cells
        if len(cells) < 7:
            cells = _split_reactor_row_fixed(content)
        if cells and cells[0] and cells[0][0].isdigit():
            rows.append(cells)

    return rows


def _split_reactor_row_fixed(content: str) -> list[str]:
    """Split a reactor row by approximate fixed-width columns.

    Fallback when pipe splitting doesn't produce enough cells.
    The format uses these approximate column widths:
    |UNIT |SCRAM CODE|RX CRIT|INIT PWR|   INIT RX MODE  |CURR PWR|  CURR RX MODE   |
    """
    # Remove outer pipes
    content = content.strip().strip("|")
    if len(content) < 50:
        return []

    # Split on multiple spaces (the column separator in data rows)
    parts = re.split(r"\s{2,}", content.strip())
    return [p.strip() for p in parts if p.strip()]


def _extract_persons(block: str) -> list:
    """Extract person contacts from the right column of the plaintext block."""
    # Find the PERSON ORGANIZATION header
    m = re.search(r"PERSON\s+ORGANIZATION\s*\|", block)
    if not m:
        return []

    # Collect person lines from the right column after the header
    persons_text_parts = []
    lines_after = block[m.end() :].split("\n")
    for line in lines_after:
        # Stop at separator lines or EVENT TEXT
        if re.match(r"\s*\+[-+]+", line) or "EVENT TEXT" in line:
            break
        # Extract right column content (after the middle |)
        # Person lines are typically at the end of a pipe-delimited row
        if "|" in line:
            parts = line.strip().strip("|").split("|")
            if len(parts) >= 2:
                right = parts[-1].strip()
                if right and not right.startswith("+") and not right.startswith("-"):
                    persons_text_parts.append(right)

    if not persons_text_parts:
        return []

    # Parse person entries: "NAME            ORG"
    persons = []
    for part in persons_text_parts:
        part = part.strip()
        if not part or part == "PERSON          ORGANIZATION":
            continue
        # Split on multiple spaces: "JACK DURR            R1"
        m = re.match(r"^(.+?)\s{2,}(\S+.*)$", part)
        if m:
            from nrc_event_scraper.models import PersonContact

            name = m.group(1).strip().rstrip(",")
            org = m.group(2).strip()
            if name:
                persons.append(PersonContact(name=name, organization=org))

    return persons


def _extract_cfr_sections(block: str) -> list:
    """Extract 10 CFR section references from the plaintext block."""
    # Find lines after "10 CFR SECTION:" that contain CFR codes
    m = re.search(r"10 CFR SECTION:\s*\|", block)
    if not m:
        return []

    sections = []
    lines_after = block[m.end() :].split("\n")
    for line in lines_after:
        # Stop at separator or new section
        if re.match(r"\s*\+[-+]+", line):
            break
        if "|" in line:
            parts = line.strip().strip("|").split("|")
            if parts:
                left = parts[0].strip()
                # Match CFR pattern: CODE DESCRIPTION
                # e.g., "AOUT 50.72(b)(1)(ii)(B)  OUTSIDE DESIGN BASIS"
                # or    "NINF                     INFORMATION ONLY"
                cfr_match = re.match(
                    r"^[A-Z]{3,5}\s+([\d.]+\([^)]*\)(?:\([^)]*\))*)\s+(.*)",
                    left,
                )
                if cfr_match:
                    sections.extend(
                        parse_cfr_sections(
                            f"{cfr_match.group(1)} - {cfr_match.group(2)}"
                        )
                    )
                elif re.match(r"^[A-Z]{3,5}\s+\S+", left):
                    # Short code like "NINF  INFORMATION ONLY"
                    code_match = re.match(r"^([A-Z]{3,5})\s+(.*)", left)
                    if code_match:
                        from nrc_event_scraper.models import CFRSection

                        sections.append(
                            CFRSection(
                                code=code_match.group(1),
                                description=code_match.group(2).strip(),
                            )
                        )

    return sections
