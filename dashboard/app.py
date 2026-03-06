"""NRC Event Dashboard — main entry point and overview page."""

from __future__ import annotations

import streamlit as st
import plotly.express as px

from data_loader import load_events
from components import render_sidebar_filters, kpi_row, partial_year_warning

st.set_page_config(
    page_title="NRC Event Dashboard",
    page_icon="\u2622",  # radioactive symbol
    layout="wide",
)

st.title("\u2622 NRC Event Notification Dashboard")
st.caption("Interactive analysis of U.S. Nuclear Regulatory Commission event reports (1999\u20132026)")


@st.cache_data
def get_data():
    return load_events()


df_all = get_data()
df = render_sidebar_filters(df_all)

partial_year_warning(df)
kpi_row(df)

st.divider()

# ── Events per year stacked area chart ──────────────────────────────────
st.subheader("Events per Year by Category")
yearly = df.groupby(["year", "category"]).size().reset_index(name="count")
fig = px.area(
    yearly,
    x="year",
    y="count",
    color="category",
    labels={"year": "Year", "count": "Event Count", "category": "Category"},
)
fig.update_layout(
    xaxis_title="Year",
    yaxis_title="Number of Events",
    legend_title="Category",
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

# ── Emergency class breakdown ───────────────────────────────────────────
st.subheader("Emergency Class Distribution")
col1, col2 = st.columns(2)

with col1:
    ec_counts = df["emergency_class_normalized"].value_counts().reset_index()
    ec_counts.columns = ["Emergency Class", "Count"]
    fig_ec = px.pie(
        ec_counts,
        values="Count",
        names="Emergency Class",
        hole=0.4,
    )
    fig_ec.update_layout(legend_title="Emergency Class")
    st.plotly_chart(fig_ec, use_container_width=True)

with col2:
    cat_counts = df["category"].value_counts().reset_index()
    cat_counts.columns = ["Category", "Count"]
    fig_cat = px.pie(
        cat_counts,
        values="Count",
        names="Category",
        hole=0.4,
    )
    fig_cat.update_layout(legend_title="Category")
    st.plotly_chart(fig_cat, use_container_width=True)

st.divider()
st.caption("Data sourced from NRC Event Notification Reports. Use sidebar pages for detailed analysis.")
