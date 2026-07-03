"""
SEO Executive Report
────────────────────
Data sources:
  • Google Search Console API  → clicks, impressions, CTR, keyword rankings
  • Google Analytics 4 API     → bounce rate, avg session duration

Auth: set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON file,
      or use OAuth credentials (see README / sidebar instructions).
"""

import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date

# ── Optional API imports (graceful fallback to sample data) ───────────────────
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric, OrderBy,
    )
    GOOGLE_LIBS = True
except ImportError:
    GOOGLE_LIBS = False

st.set_page_config(page_title="SEO Executive Report", page_icon="📈", layout="wide")

st.markdown("""
<style>
    .section-header {
        font-size: 1.1rem; font-weight: 600; color: #333;
        margin-top: 2rem; margin-bottom: 0.5rem;
        border-bottom: 2px solid #e0e0e0; padding-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
SCOPES_GSC = ["https://www.googleapis.com/auth/webmasters.readonly"]
SCOPES_GA4 = ["https://www.googleapis.com/auth/analytics.readonly"]

# ── Sidebar config ────────────────────────────────────────────────────────────
st.sidebar.title("⚙️ Report Settings")

st.sidebar.markdown("### Data source")
use_real = st.sidebar.toggle("Connect to Google APIs", value=False,
                              disabled=not GOOGLE_LIBS,
                              help="Requires google-auth, google-api-python-client, google-analytics-data")

if not GOOGLE_LIBS:
    st.sidebar.warning("Install API libraries to enable live data:\n"
                       "```\npip install google-auth google-api-python-client "
                       "google-analytics-data\n```")

creds_path, gsc_site, ga4_property, brand_terms = "", "", "", ""
if use_real:
    creds_path    = st.sidebar.text_input("Service account JSON path",
                                          value=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
                                          help="Absolute path to your service-account key file")
    gsc_site      = st.sidebar.text_input("Search Console site URL",
                                          placeholder="https://www.example.com/",
                                          help="Exact property URL as it appears in GSC")
    ga4_property  = st.sidebar.text_input("GA4 Property ID",
                                          placeholder="123456789",
                                          help="Numeric property ID (not measurement ID)")
    brand_terms   = st.sidebar.text_input("Brand keywords (comma-separated)",
                                          placeholder="acme, acme inc",
                                          help="Used to split branded vs non-branded clicks")

st.sidebar.markdown("---")
time_range = st.sidebar.radio(
    "Time range",
    ["Last 13 weeks (quarterly)", "Last 26 weeks (6 months)", "Last 78 weeks (18 months)"],
)
n_weeks = {"Last 13 weeks (quarterly)": 13,
           "Last 26 weeks (6 months)":  26,
           "Last 78 weeks (18 months)": 78}[time_range]

# ── API helpers ───────────────────────────────────────────────────────────────
def _creds(scopes):
    return service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)

@st.cache_data(ttl=3600, show_spinner="Fetching Search Console data…")
def fetch_gsc(site: str, start: str, end: str) -> pd.DataFrame:
    svc = build("searchconsole", "v1", credentials=_creds(SCOPES_GSC))
    rows = []
    request_body = {
        "startDate": start,
        "endDate": end,
        "dimensions": ["date", "query"],
        "rowLimit": 25000,
        "dataState": "final",
    }
    resp = svc.searchanalytics().query(siteUrl=site, body=request_body).execute()
    for r in resp.get("rows", []):
        rows.append({
            "date":        r["keys"][0],
            "query":       r["keys"][1],
            "clicks":      r["clicks"],
            "impressions": r["impressions"],
            "ctr":         r["ctr"] * 100,
            "position":    r["position"],
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600, show_spinner="Fetching GA4 data…")
def fetch_ga4(property_id: str, start: str, end: str) -> pd.DataFrame:
    client = BetaAnalyticsDataClient(credentials=_creds(SCOPES_GA4))
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="week")],       # ISO week number
        metrics=[
            Metric(name="bounceRate"),
            Metric(name="averageSessionDuration"),
        ],
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="week"))],
    )
    resp = client.run_report(req)
    rows = []
    for row in resp.rows:
        rows.append({
            "week_label":   row.dimension_values[0].value,
            "bounce_rate":  float(row.metric_values[0].value) * 100,
            "avg_session_s": float(row.metric_values[1].value),
        })
    return pd.DataFrame(rows)

def gsc_to_weekly(raw: pd.DataFrame, brand_kws: list[str]) -> pd.DataFrame:
    """Aggregate raw GSC row-per-query-per-day into weekly totals."""
    raw["date"] = pd.to_datetime(raw["date"])
    raw["week"] = raw["date"] - pd.to_timedelta(raw["date"].dt.dayofweek, unit="d")

    brand_mask = raw["query"].str.lower().str.contains(
        "|".join(brand_kws), na=False) if brand_kws else pd.Series(False, index=raw.index)

    weekly = (raw.groupby("week")
                 .agg(clicks=("clicks", "sum"),
                      impressions=("impressions", "sum"))
                 .reset_index())
    weekly["ctr"] = (weekly["clicks"] / weekly["impressions"] * 100).round(2)

    branded_clicks = (raw[brand_mask].groupby("week")["clicks"].sum()
                                     .reset_index().rename(columns={"clicks": "branded"}))
    weekly = weekly.merge(branded_clicks, on="week", how="left").fillna({"branded": 0})
    weekly["branded"]     = weekly["branded"].astype(int)
    weekly["non_branded"] = weekly["clicks"] - weekly["branded"]

    # keyword rank buckets
    top3  = (raw[raw["position"] <= 3].groupby("week")["query"].nunique()
                                        .reset_index().rename(columns={"query": "kw_top3"}))
    top10 = (raw[raw["position"] <= 10].groupby("week")["query"].nunique()
                                         .reset_index().rename(columns={"query": "kw_top10"}))
    weekly = weekly.merge(top3,  on="week", how="left").fillna({"kw_top3": 0})
    weekly = weekly.merge(top10, on="week", how="left").fillna({"kw_top10": 0})
    return weekly

def merge_sources(gsc_weekly: pd.DataFrame, ga4_weekly: pd.DataFrame) -> pd.DataFrame:
    """Join GSC and GA4 on ISO week."""
    gsc_weekly["iso_week"] = gsc_weekly["week"].dt.strftime("%Y%W")
    ga4_weekly["iso_week"] = ga4_weekly["week_label"].apply(
        lambda w: w if len(w) == 6 else f"20{w}")   # normalise GA4 yearWeek
    merged = gsc_weekly.merge(ga4_weekly.drop(columns=["week_label"]), on="iso_week", how="left")
    merged["bounce_rate"]   = merged["bounce_rate"].ffill()
    merged["avg_session_s"] = merged["avg_session_s"].ffill()
    return merged.drop(columns=["iso_week"])

# ── Sample data fallback ──────────────────────────────────────────────────────
def generate_sample_data(weeks: int = 78) -> pd.DataFrame:
    rng  = np.random.default_rng(42)
    end  = datetime.today() - timedelta(days=datetime.today().weekday())
    dates = [end - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    trend = np.linspace(0.7, 1.0, weeks)
    noise = lambda s: rng.normal(1, s, weeks)
    clicks      = (rng.integers(8_000, 12_000, weeks) * trend * noise(0.08)).astype(int)
    impressions = (clicks / rng.uniform(0.03, 0.06, weeks)).astype(int)
    branded_pct = rng.uniform(0.25, 0.40, weeks)
    return pd.DataFrame({
        "week":          dates,
        "clicks":        clicks,
        "impressions":   impressions,
        "ctr":           (clicks / impressions * 100).round(2),
        "branded":       (clicks * branded_pct).astype(int),
        "non_branded":   (clicks * (1 - branded_pct)).astype(int),
        "bounce_rate":   (rng.uniform(38, 55, weeks) * noise(0.04)).round(1),
        "avg_session_s": (rng.uniform(90, 180, weeks) * noise(0.05)).round(0),
        "kw_top3":       (rng.integers(18, 35, weeks) * trend).astype(int),
        "kw_top10":      (rng.integers(80, 150, weeks) * trend).astype(int),
    })

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_live(site, property_id, n_weeks, brand_terms_str):
    end_dt   = date.today()
    start_dt = end_dt - timedelta(weeks=n_weeks)
    start, end = start_dt.isoformat(), end_dt.isoformat()

    brand_kws = [b.strip().lower() for b in brand_terms_str.split(",") if b.strip()]

    raw_gsc  = fetch_gsc(site, start, end)
    gsc_wk   = gsc_to_weekly(raw_gsc, brand_kws)

    raw_ga4  = fetch_ga4(property_id, start, end)
    df       = merge_sources(gsc_wk, raw_ga4)
    return df.sort_values("week").tail(n_weeks).reset_index(drop=True)

if use_real and creds_path and gsc_site and ga4_property:
    try:
        df = load_live(gsc_site, ga4_property, n_weeks, brand_terms)
        data_label = "Live — Google APIs"
    except Exception as e:
        st.error(f"API error: {e}")
        df = generate_sample_data(78).tail(n_weeks).reset_index(drop=True)
        data_label = "Sample data (API error)"
else:
    df = generate_sample_data(78).tail(n_weeks).reset_index(drop=True)
    data_label = "Sample data"

# ── Dashboard ──────────────────────────────────────────────────────────────────
report_week = pd.to_datetime(df["week"].iloc[-1]).strftime("%b %d, %Y")
st.title("📊 SEO Executive Report")
st.caption(f"Week ending **{report_week}**  ·  {n_weeks}-week view  ·  _{data_label}_")

def wow_delta(series):
    curr, prev = series.iloc[-1], series.iloc[-2]
    return curr, (curr - prev) / prev * 100 if prev else 0

# KPI cards
st.markdown('<div class="section-header">Key Metrics — Week-over-Week</div>', unsafe_allow_html=True)
metrics = [
    ("🖱️ Organic Clicks",     "clicks",        "",  False),
    ("👁️ Impressions",        "impressions",   "",  False),
    ("📌 CTR",                 "ctr",           "%", False),
    ("↩️ Bounce Rate",        "bounce_rate",   "%", True),
    ("⏱️ Avg Session (s)",    "avg_session_s", "s", False),
    ("🥇 KW Top 3",           "kw_top3",       "",  False),
    ("🏅 KW Top 10",          "kw_top10",      "",  False),
]
for col, (label, field, unit, invert) in zip(st.columns(len(metrics)), metrics):
    curr, pct = wow_delta(df[field])
    col.metric(label, f"{curr:,.1f}{unit}" if isinstance(curr, float) else f"{curr:,}",
               f"{pct:+.1f}%", delta_color="inverse" if invert else "normal")

# Organic traffic
st.markdown('<div class="section-header">Organic Traffic (Clicks)</div>', unsafe_allow_html=True)
fig = px.bar(df, x="week", y="clicks", color_discrete_sequence=["#4CAF50"])
fig.add_scatter(x=df["week"], y=df["clicks"].rolling(4).mean(),
                mode="lines", name="4-wk avg", line=dict(color="#1a6e1a", width=2))
fig.update_layout(height=320, margin=dict(t=10, b=10), legend=dict(orientation="h"))
st.plotly_chart(fig, use_container_width=True)

# Branded / non-branded
st.markdown('<div class="section-header">Branded vs Non-Branded Split</div>', unsafe_allow_html=True)
c1, c2 = st.columns([2, 1])
fig_s = go.Figure()
fig_s.add_bar(x=df["week"], y=df["non_branded"], name="Non-Branded", marker_color="#2196F3")
fig_s.add_bar(x=df["week"], y=df["branded"],     name="Branded",     marker_color="#90CAF9")
fig_s.update_layout(barmode="stack", height=300, margin=dict(t=10, b=10), legend=dict(orientation="h"))
c1.plotly_chart(fig_s, use_container_width=True)

nb_pct = df["non_branded"].iloc[-1] / df["clicks"].iloc[-1] * 100
fig_p  = px.pie(values=[nb_pct, 100 - nb_pct], names=["Non-Branded", "Branded"],
                color_discrete_sequence=["#2196F3", "#90CAF9"], hole=0.55)
fig_p.update_layout(height=300, margin=dict(t=10, b=10, l=10, r=10), legend=dict(orientation="h"))
c2.plotly_chart(fig_p, use_container_width=True)

# CTR & Impressions
st.markdown('<div class="section-header">CTR & Impressions</div>', unsafe_allow_html=True)
fig_ci = go.Figure()
fig_ci.add_bar(x=df["week"], y=df["impressions"], name="Impressions",
               marker_color="#E3F2FD", yaxis="y2")
fig_ci.add_scatter(x=df["week"], y=df["ctr"], name="CTR (%)",
                   mode="lines+markers", line=dict(color="#1565C0", width=2))
fig_ci.update_layout(height=320, margin=dict(t=10, b=10), legend=dict(orientation="h"),
                     yaxis=dict(title="CTR (%)"),
                     yaxis2=dict(title="Impressions", overlaying="y", side="right", showgrid=False))
st.plotly_chart(fig_ci, use_container_width=True)

# Engagement
st.markdown('<div class="section-header">Engagement</div>', unsafe_allow_html=True)
c3, c4 = st.columns(2)
c3.plotly_chart(px.line(df, x="week", y="bounce_rate", markers=True,
                         color_discrete_sequence=["#FF7043"],
                         labels={"bounce_rate": "Bounce Rate (%)"})
                  .update_layout(height=280, margin=dict(t=10, b=10)), use_container_width=True)
c4.plotly_chart(px.line(df, x="week", y="avg_session_s", markers=True,
                         color_discrete_sequence=["#7B1FA2"],
                         labels={"avg_session_s": "Avg Session (s)"})
                  .update_layout(height=280, margin=dict(t=10, b=10)), use_container_width=True)

# Keyword rankings
st.markdown('<div class="section-header">Keyword Rankings</div>', unsafe_allow_html=True)
fig_kw = go.Figure()
fig_kw.add_scatter(x=df["week"], y=df["kw_top3"],  name="Top 3",
                   mode="lines+markers", line=dict(color="#F9A825", width=2))
fig_kw.add_scatter(x=df["week"], y=df["kw_top10"], name="Top 10",
                   mode="lines+markers", line=dict(color="#FDD835", width=1.5, dash="dash"))
fig_kw.update_layout(height=300, margin=dict(t=10, b=10), legend=dict(orientation="h"),
                     yaxis_title="# Keywords")
st.plotly_chart(fig_kw, use_container_width=True)

# Summary table
st.markdown('<div class="section-header">Week-over-Week Summary</div>', unsafe_allow_html=True)
rows = []
for field, (label, unit, _) in zip(
    ["clicks","impressions","ctr","branded","non_branded","bounce_rate","avg_session_s","kw_top3","kw_top10"],
    [("Clicks","",False),("Impressions","",False),("CTR (%)","%" ,False),
     ("Branded","",False),("Non-Branded","",False),("Bounce Rate (%)","%",True),
     ("Avg Session (s)","s",False),("KW Top 3","",False),("KW Top 10","",False)]
):
    curr, pct = wow_delta(df[field])
    prev = df[field].iloc[-2]
    fmt  = lambda v: f"{v:,.1f}{unit}" if isinstance(v, float) else f"{v:,}"
    rows.append({"Metric": label, "This Week": fmt(curr), "Prior Week": fmt(prev), "WoW Δ": f"{pct:+.1f}%"})
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# Raw data
with st.expander("📄 Raw weekly data"):
    st.dataframe(df.sort_values("week", ascending=False).reset_index(drop=True), use_container_width=True)
    st.download_button("Download CSV", df.to_csv(index=False), "seo_data.csv", "text/csv")
