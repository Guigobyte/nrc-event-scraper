"""Load all JSONL event files into cached pandas DataFrames."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from normalizer import normalize_dataframe

# Resolve data directory relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data" / "events"


@st.cache_data(ttl=3600)
def load_events(data_dir: str | None = None) -> pd.DataFrame:
    """Read every YYYY.jsonl file and return a normalized DataFrame."""
    events_path = Path(data_dir) if data_dir else _DEFAULT_DATA_DIR
    rows: list[dict] = []

    for jsonl_file in sorted(events_path.glob("*.jsonl")):
        with open(jsonl_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                # Flatten counts for nested arrays before dropping them
                record["cfr_count"] = len(record.get("cfr_sections") or [])
                record["reactor_unit_count"] = len(record.get("reactor_units") or [])
                # Keep nested arrays as-is for now; we flatten them separately
                rows.append(record)

    df = pd.DataFrame(rows)
    df = normalize_dataframe(df)
    return df


@st.cache_data(ttl=3600)
def load_cfr_sections(data_dir: str | None = None) -> pd.DataFrame:
    """Flatten cfr_sections into (event_number, code, description) rows."""
    events_path = Path(data_dir) if data_dir else _DEFAULT_DATA_DIR
    rows: list[dict] = []

    for jsonl_file in sorted(events_path.glob("*.jsonl")):
        with open(jsonl_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                for cfr in record.get("cfr_sections") or []:
                    rows.append({
                        "event_number": record["event_number"],
                        "cfr_code": cfr.get("code", ""),
                        "cfr_description": cfr.get("description", ""),
                    })

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["event_number", "cfr_code", "cfr_description"])


@st.cache_data(ttl=3600)
def load_reactor_units(data_dir: str | None = None) -> pd.DataFrame:
    """Flatten reactor_units into per-unit rows."""
    events_path = Path(data_dir) if data_dir else _DEFAULT_DATA_DIR
    rows: list[dict] = []

    for jsonl_file in sorted(events_path.glob("*.jsonl")):
        with open(jsonl_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                for ru in record.get("reactor_units") or []:
                    rows.append({
                        "event_number": record["event_number"],
                        "unit": ru.get("unit"),
                        "scram_code": ru.get("scram_code", ""),
                        "rx_crit": ru.get("rx_crit", ""),
                        "initial_power": ru.get("initial_power"),
                        "initial_rx_mode": ru.get("initial_rx_mode", ""),
                        "current_power": ru.get("current_power"),
                        "current_rx_mode": ru.get("current_rx_mode", ""),
                    })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["event_number", "unit", "scram_code", "rx_crit",
                 "initial_power", "initial_rx_mode", "current_power", "current_rx_mode"]
    )
