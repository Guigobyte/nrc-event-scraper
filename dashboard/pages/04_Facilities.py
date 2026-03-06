"""Facility and licensee analysis."""

from __future__ import annotations

import streamlit as st
import plotly.express as px

from data_loader import load_events
from components import render_sidebar_filters, partial_year_warning

st.set_page_config(page_title="Facilities | NRC Dashboard", layout="wide")
st.title("Facility & Licensee Analysis")

df_all = load_events()
df = render_sidebar_filters(df_all)
partial_year_warning(df)

# ── 1. Top 20 facilities (Power Reactor) ────────────────────────────────
st.subheader("Top 20 Facilities by Event Count (Power Reactor)")
pr = df[df["category"] == "Power Reactor"]
fac_counts = pr.groupby("facility").size().reset_index(name="count")
top_fac = fac_counts.nlargest(20, "count").sort_values("count", ascending=True)
fig = px.bar(top_fac, x="count", y="facility", orientation="h",
             labels={"count": "Events", "facility": "Facility"})
fig.update_layout(height=600)
st.plotly_chart(fig, use_container_width=True)

# ── 2. Top 20 licensees (Material / Fuel Cycle / Agreement State) ───────
st.subheader("Top 20 Licensees (Material / Fuel Cycle / Agreement State)")
non_pr = df[df["category"].isin(["Material", "Fuel Cycle", "Agreement State"])]
lic_counts = non_pr.groupby("licensee").size().reset_index(name="count")
top_lic = lic_counts.nlargest(20, "count").sort_values("count", ascending=True)
if len(top_lic) > 0:
    fig2 = px.bar(top_lic, x="count", y="licensee", orientation="h",
                  labels={"count": "Events", "licensee": "Licensee"})
    fig2.update_layout(height=600)
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No licensee events in current filter selection.")

# ── 3. Facility event trend ─────────────────────────────────────────────
st.subheader("Facility Event Trend")
all_facilities = sorted(pr["facility"].dropna().unique())
if all_facilities:
    selected_facility = st.selectbox("Select a facility", all_facilities)
    fac_trend = pr[pr["facility"] == selected_facility].groupby("year").size().reset_index(name="count")
    fig3 = px.bar(fac_trend, x="year", y="count",
                  labels={"year": "Year", "count": "Events"})
    fig3.update_layout(title=f"Events at {selected_facility}")
    st.plotly_chart(fig3, use_container_width=True)

# ── 4. Reactor type distribution ────────────────────────────────────────
st.subheader("Reactor Type Distribution")
rx_counts = pr["rx_type_clean"].dropna().value_counts().reset_index()
rx_counts.columns = ["Reactor Type", "Count"]
top_rx = rx_counts.head(20).sort_values("Count", ascending=True)
fig4 = px.bar(top_rx, x="Count", y="Reactor Type", orientation="h",
              labels={"Count": "Events"})
st.plotly_chart(fig4, use_container_width=True)

# ── 5. Facility x year heatmap (top 15) ─────────────────────────────────
st.subheader("Top 15 Facilities Over Time")
top15 = fac_counts.nlargest(15, "count")["facility"].tolist()
fac_year = (pr[pr["facility"].isin(top15)]
            .groupby(["facility", "year"]).size().reset_index(name="count"))
pivot = fac_year.pivot(index="facility", columns="year", values="count").fillna(0)
fig5 = px.imshow(pivot, labels=dict(x="Year", y="Facility", color="Events"),
                 aspect="auto", color_continuous_scale="YlOrRd")
fig5.update_layout(height=500)
st.plotly_chart(fig5, use_container_width=True)

# ── 6. Top reporting organizations ──────────────────────────────────────
st.subheader("Top Reporting Organizations")
rep_counts = df["rep_org"].dropna().value_counts().head(15).reset_index()
rep_counts.columns = ["Organization", "Count"]
rep_counts = rep_counts.sort_values("Count", ascending=True)
fig6 = px.bar(rep_counts, x="Count", y="Organization", orientation="h",
              labels={"Count": "Events"})
st.plotly_chart(fig6, use_container_width=True)
