"""CFR section (regulation) analysis."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px

from data_loader import load_events, load_cfr_sections
from components import render_sidebar_filters, partial_year_warning

st.set_page_config(page_title="Regulations | NRC Dashboard", layout="wide")
st.title("10 CFR Regulation Analysis")

df_all = load_events()
df = render_sidebar_filters(df_all)
partial_year_warning(df)

cfr_df = load_cfr_sections()

# Filter CFR to match current event selection
filtered_events = set(df["event_number"])
cfr_filtered = cfr_df[cfr_df["event_number"].isin(filtered_events)].copy()

# Separate info-only entries
info_mask = cfr_filtered["cfr_code"].str.upper().str.contains("NINF|INFORMATION", na=False)
cfr_regs = cfr_filtered[~info_mask]
cfr_info = cfr_filtered[info_mask]

st.info(f"**{len(cfr_regs):,}** regulatory citations across **{cfr_regs['event_number'].nunique():,}** events. "
        f"({len(cfr_info):,} information-only entries excluded.)")

# ── 1. Top 20 CFR sections ──────────────────────────────────────────────
st.subheader("Top 20 Most Cited CFR Sections")
top_cfr = cfr_regs.groupby(["cfr_code", "cfr_description"]).size().reset_index(name="count")
top_cfr = top_cfr.nlargest(20, "count").sort_values("count", ascending=True)
top_cfr["label"] = top_cfr["cfr_code"] + " - " + top_cfr["cfr_description"]

fig = px.bar(top_cfr, x="count", y="label", orientation="h",
             labels={"count": "Citations", "label": "CFR Section"})
fig.update_layout(height=600)
st.plotly_chart(fig, use_container_width=True)

# ── 2. CFR trend over time ──────────────────────────────────────────────
st.subheader("Top 5 CFR Sections Over Time")
top5_codes = cfr_regs["cfr_code"].value_counts().head(5).index.tolist()

# Join CFR data with event year
cfr_with_year = cfr_regs.merge(
    df[["event_number", "year"]].drop_duplicates(),
    on="event_number",
    how="inner",
)
cfr_top5 = cfr_with_year[cfr_with_year["cfr_code"].isin(top5_codes)]
cfr_trend = cfr_top5.groupby(["year", "cfr_code"]).size().reset_index(name="count")

fig2 = px.line(cfr_trend, x="year", y="count", color="cfr_code", markers=True,
               labels={"year": "Year", "count": "Citations", "cfr_code": "CFR Section"})
fig2.update_layout(hovermode="x unified")
st.plotly_chart(fig2, use_container_width=True)

# ── 3. CFR co-occurrence ────────────────────────────────────────────────
st.subheader("CFR Section Co-occurrence (Top 10)")
# For each event with multiple CFR sections, count pairs
multi_cfr = cfr_regs.groupby("event_number")["cfr_code"].apply(list).reset_index()
multi_cfr = multi_cfr[multi_cfr["cfr_code"].apply(len) > 1]

from collections import Counter
pair_counts: Counter = Counter()
for codes in multi_cfr["cfr_code"]:
    unique_codes = sorted(set(codes))
    for i, c1 in enumerate(unique_codes):
        for c2 in unique_codes[i + 1:]:
            pair_counts[(c1, c2)] += 1

if pair_counts:
    pairs_df = pd.DataFrame(
        [(c1, c2, cnt) for (c1, c2), cnt in pair_counts.most_common(10)],
        columns=["CFR Section 1", "CFR Section 2", "Co-occurrences"]
    )
    st.dataframe(pairs_df, hide_index=True, use_container_width=True)
else:
    st.info("No co-occurring CFR sections found in current selection.")

# ── 4. CFR sections by category ─────────────────────────────────────────
st.subheader("CFR Sections by Event Category")
cfr_with_cat = cfr_regs.merge(
    df[["event_number", "category"]].drop_duplicates(),
    on="event_number",
    how="inner",
)
top10_codes = cfr_regs["cfr_code"].value_counts().head(10).index.tolist()
cfr_cat = (cfr_with_cat[cfr_with_cat["cfr_code"].isin(top10_codes)]
           .groupby(["cfr_code", "category"]).size().reset_index(name="count"))
fig4 = px.bar(cfr_cat, x="cfr_code", y="count", color="category",
              labels={"cfr_code": "CFR Section", "count": "Citations", "category": "Category"})
st.plotly_chart(fig4, use_container_width=True)
