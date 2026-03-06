"""Search and drill-down into individual NRC events."""

from __future__ import annotations

import json

import streamlit as st
import pandas as pd

from data_loader import load_events
from components import render_sidebar_filters, partial_year_warning

st.set_page_config(page_title="Event Explorer | NRC Dashboard", layout="wide")
st.title("Event Explorer")

df_all = load_events()
df = render_sidebar_filters(df_all)
partial_year_warning(df)

# ── Search ──────────────────────────────────────────────────────────────
st.subheader("Search Events")
search_query = st.text_input("Search event text, facility, or licensee", "")

results = df.copy()
if search_query:
    query_lower = search_query.lower()
    mask = (
        results["event_text"].fillna("").str.lower().str.contains(query_lower, regex=False)
        | results["facility"].fillna("").str.lower().str.contains(query_lower, regex=False)
        | results["licensee"].fillna("").str.lower().str.contains(query_lower, regex=False)
    )
    results = results[mask]

st.info(f"**{len(results):,}** events found.")

# ── Results table ───────────────────────────────────────────────────────
display_cols = [
    "event_number", "year", "category", "facility", "licensee", "state",
    "emergency_class_normalized", "event_date",
]
display_cols = [c for c in display_cols if c in results.columns]

# Pagination
page_size = 25
total_pages = max(1, (len(results) + page_size - 1) // page_size)
page = st.number_input("Page", min_value=1, max_value=total_pages, value=1)
start_idx = (page - 1) * page_size
page_results = results.iloc[start_idx : start_idx + page_size]

st.dataframe(
    page_results[display_cols].rename(columns={
        "event_number": "Event #",
        "year": "Year",
        "category": "Category",
        "facility": "Facility",
        "licensee": "Licensee",
        "state": "State",
        "emergency_class_normalized": "Emergency Class",
        "event_date": "Event Date",
    }),
    hide_index=True,
    use_container_width=True,
)
st.caption(f"Page {page} of {total_pages}")

# ── Event detail expander ───────────────────────────────────────────────
st.subheader("Event Detail")
event_numbers = page_results["event_number"].tolist()
if event_numbers:
    selected_event = st.selectbox("Select event to view details", event_numbers)
    event_row = results[results["event_number"] == selected_event].iloc[0]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Basic Information**")
        st.write(f"- **Event Number:** {event_row['event_number']}")
        st.write(f"- **Category:** {event_row['category']}")
        st.write(f"- **Emergency Class:** {event_row['emergency_class_normalized']}")
        st.write(f"- **Event Date:** {event_row.get('event_date', 'N/A')}")
        st.write(f"- **Notification Date:** {event_row.get('notification_date', 'N/A')}")
        if event_row.get("notification_delay_days") is not None and pd.notna(event_row["notification_delay_days"]):
            st.write(f"- **Notification Delay:** {int(event_row['notification_delay_days'])} days")

    with col2:
        st.markdown("**Location & Facility**")
        if pd.notna(event_row.get("facility")):
            st.write(f"- **Facility:** {event_row['facility']}")
        if pd.notna(event_row.get("licensee")):
            st.write(f"- **Licensee:** {event_row['licensee']}")
        st.write(f"- **State:** {event_row.get('state', 'N/A')}")
        st.write(f"- **Region:** {event_row.get('region_label', 'N/A')}")
        if pd.notna(event_row.get("rx_type_clean")):
            st.write(f"- **Reactor Type:** {event_row['rx_type_clean']}")

    # Event text
    st.markdown("**Event Description**")
    st.text_area("", value=event_row.get("event_text", ""), height=300, disabled=True)

    # CFR sections
    cfr = event_row.get("cfr_sections")
    if cfr and isinstance(cfr, list) and len(cfr) > 0:
        st.markdown("**CFR Sections**")
        for section in cfr:
            if isinstance(section, dict):
                st.write(f"- {section.get('code', '')} - {section.get('description', '')}")

    # Persons notified
    persons = event_row.get("persons_notified")
    if persons and isinstance(persons, list) and len(persons) > 0:
        st.markdown("**Persons Notified**")
        for p in persons:
            if isinstance(p, dict):
                st.write(f"- {p.get('name', '')} ({p.get('organization', '')})")

    # Reactor units
    units = event_row.get("reactor_units")
    if units and isinstance(units, list) and len(units) > 0:
        st.markdown("**Reactor Unit Status**")
        units_df = pd.DataFrame(units)
        st.dataframe(units_df, hide_index=True, use_container_width=True)

    # Link to NRC page
    if event_row.get("page_url"):
        st.markdown(f"[View on NRC website]({event_row['page_url']})")

# ── CSV export ──────────────────────────────────────────────────────────
st.divider()
st.subheader("Export")

export_cols = [
    "event_number", "category", "report_date", "event_date", "notification_date",
    "facility", "licensee", "state", "region", "emergency_class_normalized",
    "notification_delay_days", "event_text", "page_url",
]
export_cols = [c for c in export_cols if c in results.columns]
csv = results[export_cols].to_csv(index=False)
st.download_button(
    label=f"Download {len(results):,} events as CSV",
    data=csv,
    file_name="nrc_events_export.csv",
    mime="text/csv",
)
