"""Emergency classification analysis."""

from __future__ import annotations

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from data_loader import load_events
from components import render_sidebar_filters, partial_year_warning
from normalizer import SEVERITY_ORDER

st.set_page_config(page_title="Emergency | NRC Dashboard", layout="wide")
st.title("Emergency Classification Analysis")

df_all = load_events()
df = render_sidebar_filters(df_all)
partial_year_warning(df)

# ── 1. Emergency class distribution ─────────────────────────────────────
st.subheader("Emergency Class Distribution")
col1, col2 = st.columns(2)

with col1:
    ec_counts = df["emergency_class_normalized"].value_counts().reset_index()
    ec_counts.columns = ["Emergency Class", "Count"]
    fig = px.pie(ec_counts, values="Count", names="Emergency Class", hole=0.4)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    # Counts table
    ec_sorted = ec_counts.sort_values("Count", ascending=False)
    st.dataframe(ec_sorted, hide_index=True, use_container_width=True)

# ── 2. Emergency class trend over time ──────────────────────────────────
st.subheader("Emergency Class Trend Over Time")
yearly_ec = df.groupby(["year", "emergency_class_normalized"]).size().reset_index(name="count")
fig2 = px.area(yearly_ec, x="year", y="count", color="emergency_class_normalized",
               category_orders={"emergency_class_normalized": SEVERITY_ORDER},
               labels={"year": "Year", "count": "Events", "emergency_class_normalized": "Emergency Class"})
fig2.update_layout(hovermode="x unified")
st.plotly_chart(fig2, use_container_width=True)

# ── 3. Severity by category ────────────────────────────────────────────
st.subheader("Emergency Severity by Category")
cat_ec = df.groupby(["category", "emergency_class_normalized"]).size().reset_index(name="count")
fig3 = px.bar(cat_ec, x="category", y="count", color="emergency_class_normalized",
              category_orders={"emergency_class_normalized": SEVERITY_ORDER},
              labels={"category": "Category", "count": "Events", "emergency_class_normalized": "Emergency Class"})
st.plotly_chart(fig3, use_container_width=True)

# ── 4. High-severity event timeline ────────────────────────────────────
st.subheader("High-Severity Event Timeline (Alert and Above)")
high_sev = df[df["emergency_severity"] >= 3].copy()
if len(high_sev) > 0:
    high_sev["date_display"] = high_sev["event_date"].fillna(high_sev["report_date"])
    fig4 = px.scatter(
        high_sev,
        x="date_display",
        y="emergency_class_normalized",
        color="emergency_class_normalized",
        hover_data=["event_number", "facility", "state"],
        category_orders={"emergency_class_normalized": ["Alert", "Site Area Emergency", "General Emergency"]},
        labels={"date_display": "Date", "emergency_class_normalized": "Class"},
    )
    fig4.update_traces(marker=dict(size=10))
    fig4.update_layout(height=400)
    st.plotly_chart(fig4, use_container_width=True)

    # Highlight General Emergency events
    gen_emerg = high_sev[high_sev["emergency_class_normalized"] == "General Emergency"]
    if len(gen_emerg) > 0:
        st.warning(f"**{len(gen_emerg)} General Emergency event(s)** in the dataset:")
        for _, row in gen_emerg.iterrows():
            st.write(f"- Event {row['event_number']} ({row.get('facility', 'N/A')}, "
                     f"{row.get('state', 'N/A')}) - {row['event_date']}")
else:
    st.info("No high-severity events (Alert or above) in the current filter selection.")

# ── 5. Emergency class x region ─────────────────────────────────────────
st.subheader("Emergency Class by Region")
region_ec = df.groupby(["region_label", "emergency_class_normalized"]).size().reset_index(name="count")
pivot = region_ec.pivot(index="region_label", columns="emergency_class_normalized", values="count").fillna(0)
# Reorder columns by severity
ordered_cols = [c for c in SEVERITY_ORDER if c in pivot.columns]
pivot = pivot[ordered_cols]
fig5 = px.imshow(pivot, labels=dict(x="Emergency Class", y="Region", color="Events"),
                 aspect="auto", color_continuous_scale="YlOrRd")
st.plotly_chart(fig5, use_container_width=True)

# ── 6. Serious event rate ──────────────────────────────────────────────
st.subheader("Serious Event Rate (Alert + Unusual Event as % of Total)")
yearly_total = df.groupby("year").size().reset_index(name="total")
yearly_serious = df[df["emergency_severity"] >= 2].groupby("year").size().reset_index(name="serious")
rate = yearly_total.merge(yearly_serious, on="year", how="left").fillna(0)
rate["rate_pct"] = (rate["serious"] / rate["total"] * 100).round(2)

fig6 = go.Figure()
fig6.add_trace(go.Scatter(x=rate["year"], y=rate["rate_pct"], mode="lines+markers",
                           name="Serious Event %"))
fig6.update_layout(xaxis_title="Year", yaxis_title="% of Total Events",
                   hovermode="x unified")
st.plotly_chart(fig6, use_container_width=True)
