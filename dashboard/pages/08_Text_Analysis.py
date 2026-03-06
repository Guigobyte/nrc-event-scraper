"""Event text analysis: keyword trends, word frequency, word clouds."""

from __future__ import annotations

import re
import string
from collections import Counter
from io import BytesIO

import streamlit as st
import pandas as pd
import plotly.express as px

from data_loader import load_events
from components import render_sidebar_filters, partial_year_warning

st.set_page_config(page_title="Text Analysis | NRC Dashboard", layout="wide")
st.title("Event Text Analysis")

df_all = load_events()
df = render_sidebar_filters(df_all)
partial_year_warning(df)

# ── Stopwords (common + domain-specific) ────────────────────────────────
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "is", "was", "are", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might", "shall",
    "can", "not", "no", "that", "this", "it", "its", "as", "if", "than", "then",
    "so", "up", "out", "about", "into", "over", "after", "before", "between",
    "under", "again", "further", "there", "here", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other", "some", "such",
    "only", "same", "also", "just", "because", "during", "through",
    # Domain-specific common words to exclude
    "nrc", "licensee", "event", "reported", "report", "number", "date",
    "nuclear", "regulatory", "commission", "notification", "notified",
}


def tokenize(text: str) -> list[str]:
    """Simple word tokenizer: lowercase, strip punctuation, remove stopwords."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    words = text.split()
    return [w for w in words if w not in STOPWORDS and len(w) > 2 and not w.isdigit()]


# ── 1. Word frequency ──────────────────────────────────────────────────
st.subheader("Top 30 Words in Event Descriptions")
all_text = " ".join(df["event_text"].dropna())
word_counts = Counter(tokenize(all_text))
top_words = word_counts.most_common(30)
words_df = pd.DataFrame(top_words, columns=["Word", "Count"]).sort_values("Count", ascending=True)
fig = px.bar(words_df, x="Count", y="Word", orientation="h",
             labels={"Count": "Frequency"})
fig.update_layout(height=700)
st.plotly_chart(fig, use_container_width=True)

# ── 2. Word cloud ──────────────────────────────────────────────────────
st.subheader("Word Cloud")
try:
    from wordcloud import WordCloud
    import matplotlib.pyplot as plt

    wc = WordCloud(
        width=1200, height=600,
        background_color="white",
        max_words=100,
        stopwords=STOPWORDS,
        colormap="viridis",
    ).generate(all_text)

    fig_wc, ax = plt.subplots(figsize=(12, 6))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    st.pyplot(fig_wc)
    plt.close(fig_wc)
except ImportError:
    st.warning("Install `wordcloud` and `matplotlib` for word cloud visualization: "
               "`uv pip install wordcloud matplotlib`")

# ── 3. Keyword trend ───────────────────────────────────────────────────
st.subheader("Keyword Trend Over Time")
keyword = st.text_input("Enter a keyword to track", value="fire")
if keyword:
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    df_kw = df.copy()
    df_kw["has_keyword"] = df_kw["event_text"].fillna("").apply(lambda t: bool(pattern.search(t)))
    kw_yearly = df_kw.groupby("year").agg(
        total=("event_number", "count"),
        matches=("has_keyword", "sum"),
    ).reset_index()
    kw_yearly["match_pct"] = (kw_yearly["matches"] / kw_yearly["total"] * 100).round(2)

    col1, col2 = st.columns(2)
    with col1:
        fig3a = px.bar(kw_yearly, x="year", y="matches",
                       labels={"year": "Year", "matches": f'Events mentioning "{keyword}"'})
        fig3a.update_layout(title="Absolute Count")
        st.plotly_chart(fig3a, use_container_width=True)
    with col2:
        fig3b = px.line(kw_yearly, x="year", y="match_pct", markers=True,
                        labels={"year": "Year", "match_pct": "% of Events"})
        fig3b.update_layout(title="As Percentage of All Events")
        st.plotly_chart(fig3b, use_container_width=True)

# ── 4. Event text length trend ──────────────────────────────────────────
st.subheader("Event Description Length Over Time")
len_yearly = df.groupby("year")["event_text_length"].mean().reset_index(name="avg_length")
fig4 = px.line(len_yearly, x="year", y="avg_length", markers=True,
               labels={"year": "Year", "avg_length": "Avg Characters"})
st.plotly_chart(fig4, use_container_width=True)

# ── 5. Category-specific top words ──────────────────────────────────────
st.subheader("Top Words by Category")
selected_cat = st.selectbox("Select category", sorted(df["category"].unique()))
cat_text = " ".join(df[df["category"] == selected_cat]["event_text"].dropna())
cat_words = Counter(tokenize(cat_text)).most_common(20)
cat_df = pd.DataFrame(cat_words, columns=["Word", "Count"]).sort_values("Count", ascending=True)
fig5 = px.bar(cat_df, x="Count", y="Word", orientation="h",
              labels={"Count": "Frequency"})
fig5.update_layout(title=f"Top 20 Words - {selected_cat}")
st.plotly_chart(fig5, use_container_width=True)
