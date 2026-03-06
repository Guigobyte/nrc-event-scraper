"""Notification delay and response time analysis."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from data_loader import load_events
from components import render_sidebar_filters, partial_year_warning

st.set_page_config(page_title="Response Time | NRC Dashboard", layout="wide")
st.title("Notification Response Time Analysis")

df_all = load_events()
df = render_sidebar_filters(df_all)
partial_year_warning(df)

# Only include rows with valid delay
delay_df = df.dropna(subset=["notification_delay_days"]).copy()

st.info(f"**{len(delay_df):,}** events with computable notification delay "
        f"(median: **{delay_df['notification_delay_days'].median():.0f} days**).")

# ── 1. Notification delay distribution ──────────────────────────────────
st.subheader("Notification Delay Distribution")
# Cap display at 30 days for readability
fig = px.histogram(delay_df, x="notification_delay_days", nbins=50,
                   range_x=[0, min(30, delay_df["notification_delay_days"].max())],
                   labels={"notification_delay_days": "Delay (days)", "count": "Events"})
fig.update_layout(bargap=0.1)
st.plotly_chart(fig, use_container_width=True)

# ── 2. Notification delay trend ─────────────────────────────────────────
st.subheader("Notification Delay Trend (Median by Year)")
yearly_delay = delay_df.groupby("year")["notification_delay_days"].agg(
    median="median", p25=lambda x: x.quantile(0.25), p75=lambda x: x.quantile(0.75)
).reset_index()

fig2 = go.Figure()
fig2.add_trace(go.Scatter(
    x=yearly_delay["year"], y=yearly_delay["p75"],
    fill=None, mode="lines", line=dict(width=0), showlegend=False,
))
fig2.add_trace(go.Scatter(
    x=yearly_delay["year"], y=yearly_delay["p25"],
    fill="tonexty", mode="lines", line=dict(width=0),
    name="25th-75th Percentile", fillcolor="rgba(31,119,180,0.2)",
))
fig2.add_trace(go.Scatter(
    x=yearly_delay["year"], y=yearly_delay["median"],
    mode="lines+markers", name="Median Delay", line=dict(width=2),
))
fig2.update_layout(xaxis_title="Year", yaxis_title="Delay (days)", hovermode="x unified")
st.plotly_chart(fig2, use_container_width=True)

# ── 3. Delay by emergency class ─────────────────────────────────────────
st.subheader("Delay by Emergency Class")
fig3 = px.box(delay_df, x="emergency_class_normalized", y="notification_delay_days",
              labels={"emergency_class_normalized": "Emergency Class",
                      "notification_delay_days": "Delay (days)"},
              category_orders={"emergency_class_normalized": [
                  "N/A", "Non Emergency", "Unusual Event", "Alert",
                  "Site Area Emergency", "General Emergency"]})
fig3.update_layout(yaxis_range=[0, min(30, delay_df["notification_delay_days"].max())])
st.plotly_chart(fig3, use_container_width=True)

# ── 4. Delay by category ────────────────────────────────────────────────
st.subheader("Delay by Category")
fig4 = px.box(delay_df, x="category", y="notification_delay_days",
              labels={"category": "Category", "notification_delay_days": "Delay (days)"})
fig4.update_layout(yaxis_range=[0, min(30, delay_df["notification_delay_days"].max())])
st.plotly_chart(fig4, use_container_width=True)

# ── 5. Outlier events (delay > 7 days) ──────────────────────────────────
st.subheader("Late Reports (Delay > 7 Days)")
outliers = delay_df[delay_df["notification_delay_days"] > 7].sort_values(
    "notification_delay_days", ascending=False
).head(50)
if len(outliers) > 0:
    display_cols = ["event_number", "category", "facility", "licensee", "state",
                    "event_date", "notification_date", "notification_delay_days",
                    "emergency_class_normalized"]
    display_cols = [c for c in display_cols if c in outliers.columns]
    st.dataframe(outliers[display_cols], hide_index=True, use_container_width=True)
else:
    st.info("No events with delay > 7 days in current selection.")

# ── 6. Reporting time-of-day ────────────────────────────────────────────
st.subheader("Notification Time of Day")
time_df = df.dropna(subset=["notification_time"]).copy()
time_df["hour"] = time_df["notification_time"].str.split(":").str[0].astype(int, errors="ignore")
time_df = time_df[time_df["hour"].between(0, 23)]
hour_counts = time_df.groupby("hour").size().reset_index(name="count")
fig6 = px.bar(hour_counts, x="hour", y="count",
              labels={"hour": "Hour of Day (24h)", "count": "Events"})
fig6.update_layout(xaxis=dict(dtick=1))
st.plotly_chart(fig6, use_container_width=True)
