"""Reactor operations analysis: scrams, power levels, operating modes."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from data_loader import load_events, load_reactor_units
from components import render_sidebar_filters, partial_year_warning

st.set_page_config(page_title="Reactor Ops | NRC Dashboard", layout="wide")
st.title("Reactor Operations Analysis")

df_all = load_events()
df = render_sidebar_filters(df_all)
partial_year_warning(df)

ru_df = load_reactor_units()

# Filter reactor units to matched events
filtered_events = set(df["event_number"])
ru = ru_df[ru_df["event_number"].isin(filtered_events)].copy()

# Join year info
ru = ru.merge(df[["event_number", "year"]].drop_duplicates(), on="event_number", how="inner")

st.info(f"**{len(ru):,}** reactor unit status records across **{ru['event_number'].nunique():,}** events.")

# ── 1. Scram code distribution ──────────────────────────────────────────
st.subheader("Scram Code Distribution")
scram_labels = {"N": "No Scram", "A/R": "Automatic Trip", "M/R": "Manual Trip"}
ru["scram_label"] = ru["scram_code"].map(scram_labels).fillna(ru["scram_code"])

col1, col2 = st.columns(2)
with col1:
    scram_counts = ru["scram_label"].value_counts().reset_index()
    scram_counts.columns = ["Scram Type", "Count"]
    fig = px.pie(scram_counts, values="Count", names="Scram Type", hole=0.4)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.dataframe(scram_counts, hide_index=True, use_container_width=True)

# ── 2. Scram trend over time ────────────────────────────────────────────
st.subheader("Reactor Scrams Over Time")
scrams = ru[ru["scram_code"].isin(["A/R", "M/R"])]
scram_trend = scrams.groupby(["year", "scram_label"]).size().reset_index(name="count")
fig2 = px.bar(scram_trend, x="year", y="count", color="scram_label",
              labels={"year": "Year", "count": "Scrams", "scram_label": "Type"})
fig2.update_layout(hovermode="x unified")
st.plotly_chart(fig2, use_container_width=True)

# ── 3. Initial power distribution ───────────────────────────────────────
st.subheader("Initial Power Level Distribution")
power_data = ru.dropna(subset=["initial_power"])
if len(power_data) > 0:
    fig3 = px.histogram(power_data, x="initial_power", nbins=20,
                        labels={"initial_power": "Initial Power (%)", "count": "Records"})
    fig3.update_layout(bargap=0.1)
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("No initial power data available in current selection.")

# ── 4. Operating mode transitions (Sankey) ──────────────────────────────
st.subheader("Reactor Mode Transitions (Initial -> Current)")
transitions = ru[
    (ru["initial_rx_mode"] != "") & (ru["current_rx_mode"] != "")
    & ru["initial_rx_mode"].notna() & ru["current_rx_mode"].notna()
].copy()

if len(transitions) > 0:
    # Get unique modes
    modes_initial = transitions["initial_rx_mode"].unique().tolist()
    modes_current = transitions["current_rx_mode"].unique().tolist()

    # Build labels: initial modes first, then current modes (with suffix to distinguish)
    labels = [f"{m} (initial)" for m in modes_initial] + [f"{m} (current)" for m in modes_current]
    initial_idx = {m: i for i, m in enumerate(modes_initial)}
    current_idx = {m: i + len(modes_initial) for i, m in enumerate(modes_current)}

    trans_counts = transitions.groupby(["initial_rx_mode", "current_rx_mode"]).size().reset_index(name="count")
    sources = [initial_idx[r["initial_rx_mode"]] for _, r in trans_counts.iterrows()]
    targets = [current_idx[r["current_rx_mode"]] for _, r in trans_counts.iterrows()]
    values = trans_counts["count"].tolist()

    fig4 = go.Figure(go.Sankey(
        node=dict(label=labels, pad=15, thickness=20),
        link=dict(source=sources, target=targets, value=values),
    ))
    fig4.update_layout(height=500)
    st.plotly_chart(fig4, use_container_width=True)
else:
    st.info("No mode transition data available.")

# ── 5. Power level at scram events ──────────────────────────────────────
st.subheader("Power Level at Scram vs Non-Scram Events")
power_scram = ru.dropna(subset=["initial_power"]).copy()
power_scram["had_scram"] = power_scram["scram_code"].isin(["A/R", "M/R"])
power_scram["scram_status"] = power_scram["had_scram"].map({True: "Scram", False: "No Scram"})

if len(power_scram) > 0:
    fig5 = px.box(power_scram, x="scram_status", y="initial_power",
                  labels={"scram_status": "", "initial_power": "Initial Power (%)"})
    st.plotly_chart(fig5, use_container_width=True)

# ── 6. Reactor criticality ──────────────────────────────────────────────
st.subheader("Reactor Criticality at Event Time")
crit_data = ru[ru["rx_crit"].isin(["Y", "N"])]
if len(crit_data) > 0:
    crit_counts = crit_data["rx_crit"].value_counts().reset_index()
    crit_counts.columns = ["Critical", "Count"]
    crit_counts["Critical"] = crit_counts["Critical"].map({"Y": "Critical (Y)", "N": "Subcritical (N)"})
    fig6 = px.pie(crit_counts, values="Count", names="Critical", hole=0.4)
    st.plotly_chart(fig6, use_container_width=True)
