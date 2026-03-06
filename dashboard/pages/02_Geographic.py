"""Geographic analysis of NRC events."""

from __future__ import annotations

import streamlit as st
import plotly.express as px

from data_loader import load_events
from components import render_sidebar_filters, partial_year_warning

st.set_page_config(page_title="Geographic | NRC Dashboard", layout="wide")
st.title("Geographic Analysis")

df_all = load_events()
df = render_sidebar_filters(df_all)
partial_year_warning(df)

# ── 1. US choropleth map ────────────────────────────────────────────────
st.subheader("Events by State")
category_toggle = st.radio("Show", ["All Categories", "Power Reactor Only", "Material / Fuel Cycle / Agreement State"],
                           horizontal=True)
df_map = df.copy()
if category_toggle == "Power Reactor Only":
    df_map = df_map[df_map["category"] == "Power Reactor"]
elif category_toggle == "Material / Fuel Cycle / Agreement State":
    df_map = df_map[df_map["category"].isin(["Material", "Fuel Cycle", "Agreement State"])]

state_counts = df_map.groupby("state").size().reset_index(name="count")
state_counts = state_counts[state_counts["state"].notna() & (state_counts["state"] != "")]

fig = px.choropleth(
    state_counts,
    locations="state",
    locationmode="USA-states",
    color="count",
    scope="usa",
    color_continuous_scale="YlOrRd",
    labels={"state": "State", "count": "Events"},
)
fig.update_layout(geo=dict(bgcolor="rgba(0,0,0,0)"), margin=dict(l=0, r=0, t=0, b=0), height=500)
st.plotly_chart(fig, use_container_width=True)

# ── 2. Events by NRC Region ────────────────────────────────────────────
st.subheader("Events by NRC Region")
col1, col2 = st.columns(2)

with col1:
    region_counts = df.groupby("region_label").size().reset_index(name="count")
    region_counts = region_counts.sort_values("count", ascending=True)
    fig2 = px.bar(region_counts, x="count", y="region_label", orientation="h",
                  labels={"count": "Events", "region_label": "Region"})
    st.plotly_chart(fig2, use_container_width=True)

# ── 3. Top 15 states ───────────────────────────────────────────────────
with col2:
    st.subheader("Top 15 States")
    top_states = state_counts.nlargest(15, "count").sort_values("count", ascending=True)
    fig3 = px.bar(top_states, x="count", y="state", orientation="h",
                  labels={"count": "Events", "state": "State"})
    st.plotly_chart(fig3, use_container_width=True)

# ── 4. State trend over time ───────────────────────────────────────────
st.subheader("State Trend Over Time")
top_5_states = state_counts.nlargest(5, "count")["state"].tolist()
selected_states = st.multiselect("Select states", sorted(state_counts["state"].unique()),
                                 default=top_5_states)
if selected_states:
    state_trend = (df[df["state"].isin(selected_states)]
                   .groupby(["year", "state"]).size().reset_index(name="count"))
    fig4 = px.line(state_trend, x="year", y="count", color="state", markers=True,
                   labels={"year": "Year", "count": "Events", "state": "State"})
    fig4.update_layout(hovermode="x unified")
    st.plotly_chart(fig4, use_container_width=True)
