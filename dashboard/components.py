"""Shared UI components: sidebar filters, KPI cards, helpers."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from normalizer import SEVERITY_ORDER


def render_sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Render global sidebar filters and return the filtered DataFrame."""
    st.sidebar.header("Filters")

    # Year range
    min_year = int(df["year"].min()) if df["year"].notna().any() else 1999
    max_year = int(df["year"].max()) if df["year"].notna().any() else datetime.now().year
    year_range = st.sidebar.slider("Year Range", min_year, max_year, (min_year, max_year))

    # Category
    all_cats = sorted(df["category"].dropna().unique())
    categories = st.sidebar.multiselect("Category", all_cats, default=all_cats)

    # Emergency class
    all_emergency = [e for e in SEVERITY_ORDER if e in df["emergency_class_normalized"].unique()]
    emergency = st.sidebar.multiselect("Emergency Class", all_emergency, default=all_emergency)

    # Region
    all_regions = sorted(df["region_label"].dropna().unique())
    regions = st.sidebar.multiselect("Region", all_regions, default=[])

    # State
    all_states = sorted(df["state"].dropna().unique())
    states = st.sidebar.multiselect("State", all_states, default=[])

    # Apply filters
    mask = (
        df["year"].between(year_range[0], year_range[1])
        & df["category"].isin(categories)
        & df["emergency_class_normalized"].isin(emergency)
    )
    if regions:
        mask = mask & df["region_label"].isin(regions)
    if states:
        mask = mask & df["state"].isin(states)

    return df[mask].copy()


def kpi_row(df: pd.DataFrame) -> None:
    """Display a row of KPI metric cards."""
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Events", f"{len(df):,}")
    col2.metric("Facilities", f"{df['facility'].dropna().nunique():,}")
    col3.metric("States", f"{df['state'].dropna().nunique():,}")

    min_year = int(df["year"].min()) if df["year"].notna().any() else 0
    max_year = int(df["year"].max()) if df["year"].notna().any() else 0
    col4.metric("Year Range", f"{min_year} - {max_year}")


def partial_year_warning(df: pd.DataFrame) -> None:
    """Show a warning if the current year has incomplete data."""
    current_year = datetime.now().year
    if current_year in df["year"].values:
        st.info(
            f"**Note:** {current_year} data is incomplete (year in progress). "
            "Trend comparisons with prior full years should account for this."
        )
