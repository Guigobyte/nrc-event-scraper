"""Normalize 27 years of NRC event data inconsistencies."""

from __future__ import annotations

import re

import pandas as pd

# ── Emergency class: unify abbreviations, casing, and legacy codes ──────────
_EMERGENCY_CLASS_MAP: dict[str, str] = {
    "": "N/A",
    "N/A": "N/A",
    "NON EMERGENCY": "Non Emergency",
    "NON-EMERGENCY": "Non Emergency",
    "NOT": "Non Emergency",
    "UNUSUAL EVENT": "Unusual Event",
    "UNU": "Unusual Event",
    "ALERT": "Alert",
    "ALE": "Alert",
    "SITE AREA EMERGENCY": "Site Area Emergency",
    "SAE": "Site Area Emergency",
    "GENERAL EMERGENCY": "General Emergency",
    "GEN": "General Emergency",
}

EMERGENCY_SEVERITY: dict[str, int] = {
    "N/A": 0,
    "Non Emergency": 1,
    "Unusual Event": 2,
    "Alert": 3,
    "Site Area Emergency": 4,
    "General Emergency": 5,
}

SEVERITY_ORDER = ["N/A", "Non Emergency", "Unusual Event", "Alert", "Site Area Emergency", "General Emergency"]

# Reactor type extraction: "[1] GE-4,[2] GE-4" → "GE-4"
_RX_TYPE_RE = re.compile(r"\]\s*([A-Za-z0-9&/\-]+(?:\s*\([^)]*\))?)")


def normalize_emergency_class(raw: str | None) -> str:
    """Map raw emergency_class to a canonical value."""
    if raw is None:
        return "N/A"
    key = raw.strip().upper()
    return _EMERGENCY_CLASS_MAP.get(key, raw.strip() or "N/A")


def extract_reactor_types(rx_type: str | None) -> list[str]:
    """Extract reactor type codes from the bracketed rx_type string."""
    if not rx_type:
        return []
    return list(dict.fromkeys(_RX_TYPE_RE.findall(rx_type)))


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all normalizations to the main events DataFrame in-place and return it."""
    # Emergency class
    df["emergency_class_normalized"] = df["emergency_class"].fillna("").apply(normalize_emergency_class)
    df["emergency_severity"] = df["emergency_class_normalized"].map(EMERGENCY_SEVERITY).fillna(0).astype(int)

    # Date columns → datetime
    for col in ("report_date", "event_date", "notification_date", "last_update_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Temporal derived columns (from report_date, falling back to event_date)
    date_col = df["report_date"].fillna(df["event_date"])
    df["year"] = date_col.dt.year.astype("Int64")
    df["month"] = date_col.dt.month.astype("Int64")
    df["quarter"] = date_col.dt.quarter.astype("Int64")
    df["day_of_week"] = date_col.dt.day_name()

    # Clamp years to valid NRC reporting range (data quality fix)
    valid_year = df["year"].between(1999, 2030, inclusive="both")
    df.loc[~valid_year, ["year", "month", "quarter", "day_of_week"]] = pd.NA

    # Notification delay (days)
    df["notification_delay_days"] = (
        (df["notification_date"] - df["event_date"]).dt.days.clip(lower=0)
    )

    # Event text length
    df["event_text_length"] = df["event_text"].fillna("").str.len()

    # CFR count (stored during loading as cfr_count)
    # Reactor unit count (stored during loading as reactor_unit_count)

    # County encoding fix (Unicode replacement chars in 2026 data)
    if "county" in df.columns:
        df["county"] = df["county"].fillna("").str.replace("\ufffd", "", regex=False)

    # Reactor type extraction → first type found
    def _first_rx_type(x):
        types = extract_reactor_types(x)
        return types[0] if types else None
    df["rx_type_clean"] = df["rx_type"].apply(_first_rx_type)

    # Region label
    df["region_label"] = df["region"].apply(
        lambda x: f"Region {x}" if x and x != "0" else "HQ / Non-Regional" if x == "0" else "Unknown"
    )

    return df
