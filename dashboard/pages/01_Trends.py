"""Event frequency trends over time."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from data_loader import load_events
from components import render_sidebar_filters, partial_year_warning

st.set_page_config(page_title="Trends | NRC Dashboard", layout="wide")
st.title("Event Frequency Trends")

df_all = load_events()
df = render_sidebar_filters(df_all)
partial_year_warning(df)

# ── 1. Annual event count ───────────────────────────────────────────────
st.subheader("Annual Event Count")
yearly = df.groupby("year").size().reset_index(name="count")
fig = px.line(yearly, x="year", y="count", markers=True,
              labels={"year": "Year", "count": "Events"})
fig.update_layout(hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# ── 2. Annual count by category ─────────────────────────────────────────
st.subheader("Annual Events by Category")
yearly_cat = df.groupby(["year", "category"]).size().reset_index(name="count")
fig2 = px.area(yearly_cat, x="year", y="count", color="category",
               labels={"year": "Year", "count": "Events", "category": "Category"})
fig2.update_layout(hovermode="x unified")
st.plotly_chart(fig2, use_container_width=True)

# ── 3. Monthly heatmap ──────────────────────────────────────────────────
st.subheader("Monthly Event Heatmap")
monthly = df.groupby(["year", "month"]).size().reset_index(name="count")
pivot = monthly.pivot(index="year", columns="month", values="count").fillna(0)
month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
pivot.columns = [month_names[int(m) - 1] for m in pivot.columns]

fig3 = px.imshow(
    pivot,
    labels=dict(x="Month", y="Year", color="Events"),
    aspect="auto",
    color_continuous_scale="YlOrRd",
)
fig3.update_layout(height=600)
st.plotly_chart(fig3, use_container_width=True)

# ── 4. Rolling 12-month average ─────────────────────────────────────────
st.subheader("Rolling 12-Month Average")
# Create a monthly time series
df_ts = df.dropna(subset=["year", "month"]).copy()
df_ts["date"] = pd.to_datetime(df_ts["year"].astype(int).astype(str) + "-" + df_ts["month"].astype(int).astype(str) + "-01")
monthly_ts = df_ts.groupby("date").size().reset_index(name="count")
monthly_ts = monthly_ts.sort_values("date")
monthly_ts["rolling_12m"] = monthly_ts["count"].rolling(12, min_periods=1).mean()

fig4 = go.Figure()
fig4.add_trace(go.Scatter(x=monthly_ts["date"], y=monthly_ts["count"],
                           mode="lines", name="Monthly", opacity=0.3))
fig4.add_trace(go.Scatter(x=monthly_ts["date"], y=monthly_ts["rolling_12m"],
                           mode="lines", name="12-Month Avg", line=dict(width=3)))
fig4.update_layout(xaxis_title="Date", yaxis_title="Events", hovermode="x unified")
st.plotly_chart(fig4, use_container_width=True)

# ── 5. Year-over-year comparison ────────────────────────────────────────
st.subheader("Year-over-Year Comparison")
available_years = sorted(df["year"].dropna().unique())
selected_years = st.multiselect("Select years to compare", available_years,
                                default=available_years[-5:] if len(available_years) >= 5 else available_years)
if selected_years:
    yoy = df[df["year"].isin(selected_years)].groupby(["year", "month"]).size().reset_index(name="count")
    yoy["month_name"] = yoy["month"].apply(lambda m: month_names[int(m) - 1] if pd.notna(m) else "")
    fig5 = px.bar(yoy, x="month_name", y="count", color="year",
                  barmode="group", labels={"month_name": "Month", "count": "Events", "year": "Year"})
    st.plotly_chart(fig5, use_container_width=True)

# ── 6. Day-of-week distribution ─────────────────────────────────────────
st.subheader("Day-of-Week Distribution")
dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
dow = df["day_of_week"].value_counts().reindex(dow_order).reset_index()
dow.columns = ["Day", "Count"]
fig6 = px.bar(dow, x="Day", y="Count", labels={"Count": "Events"})
st.plotly_chart(fig6, use_container_width=True)
