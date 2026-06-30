import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(
    page_title="SEO Executive Report",
    page_icon="📈",
    layout="wide",
)

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 16px 20px;
        border-left: 4px solid #4CAF50;
    }
    .metric-card.down { border-left-color: #f44336; }
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #333;
        margin-top: 2rem;
        margin-bottom: 0.5rem;
        border-bottom: 2px solid #e0e0e0;
        padding-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def generate_sample_data(weeks: int = 78) -> pd.DataFrame:
    """Generate synthetic weekly SEO data (replace with your real data source)."""
    rng = np.random.default_rng(42)
    end = datetime.today() - timedelta(days=datetime.today().weekday())  # last Monday
    dates = [end - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]

    trend = np.linspace(0.7, 1.0, weeks)
    noise = lambda scale: rng.normal(1, scale, weeks)

    clicks       = (rng.integers(8_000, 12_000, weeks) * trend * noise(0.08)).astype(int)
    impressions  = (clicks / rng.uniform(0.03, 0.06, weeks)).astype(int)
    ctr          = (clicks / impressions * 100).round(2)
    branded_pct  = rng.uniform(0.25, 0.40, weeks)
    branded      = (clicks * branded_pct).astype(int)
    non_branded  = clicks - branded
    bounce_rate  = (rng.uniform(38, 55, weeks) * noise(0.04)).round(1)
    avg_session  = (rng.uniform(90, 180, weeks) * noise(0.05)).round(0)
    top3_kw      = (rng.integers(18, 35, weeks) * trend).astype(int)
    top10_kw     = (rng.integers(80, 150, weeks) * trend).astype(int)

    return pd.DataFrame({
        "week":           dates,
        "clicks":         clicks,
        "impressions":    impressions,
        "ctr":            ctr,
        "branded":        branded,
        "non_branded":    non_branded,
        "bounce_rate":    bounce_rate,
        "avg_session_s":  avg_session,
        "kw_top3":        top3_kw,
        "kw_top10":       top10_kw,
    })

def fmt_delta(val: float, unit: str = "", invert: bool = False) -> str:
    arrow = "▲" if val >= 0 else "▼"
    color = ("#4CAF50" if val >= 0 else "#f44336") if not invert else ("#f44336" if val >= 0 else "#4CAF50")
    sign  = "+" if val >= 0 else ""
    return f'<span style="color:{color}">{arrow} {sign}{val:.1f}{unit}</span>'

def wow_delta(series: pd.Series, idx: int = -1):
    """Return absolute and % delta vs prior period."""
    curr = series.iloc[idx]
    prev = series.iloc[idx - 1]
    abs_d = curr - prev
    pct_d = (abs_d / prev * 100) if prev != 0 else 0
    return curr, abs_d, pct_d

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("⚙️ Report Settings")

time_range = st.sidebar.radio(
    "Time range",
    ["Last 13 weeks (quarterly)", "Last 26 weeks (6 months)", "Last 78 weeks (18 months)"],
    index=0,
)
range_map = {
    "Last 13 weeks (quarterly)":   13,
    "Last 26 weeks (6 months)":    26,
    "Last 78 weeks (18 months)":   78,
}
n_weeks = range_map[time_range]

st.sidebar.markdown("---")
st.sidebar.markdown("**Data source**")
uploaded = st.sidebar.file_uploader("Upload CSV (optional)", type="csv",
    help="Columns: week, clicks, impressions, ctr, branded, non_branded, bounce_rate, avg_session_s, kw_top3, kw_top10")

# ── Data ──────────────────────────────────────────────────────────────────────
if uploaded:
    raw = pd.read_csv(uploaded, parse_dates=["week"])
else:
    raw = generate_sample_data(78)

df = raw.sort_values("week").tail(n_weeks).reset_index(drop=True)

# ── Header ────────────────────────────────────────────────────────────────────
report_week = df["week"].iloc[-1].strftime("%b %d, %Y")
st.title("📊 SEO Executive Report")
st.caption(f"Week ending **{report_week}**  ·  {n_weeks}-week view")

# ── KPI Cards ─────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Key Metrics — Week-over-Week</div>', unsafe_allow_html=True)

metrics = [
    ("Organic Clicks",      "clicks",       "",   False, "🖱️"),
    ("Impressions",         "impressions",  "",   False, "👁️"),
    ("CTR",                 "ctr",          "%",  False, "📌"),
    ("Bounce Rate",         "bounce_rate",  "%",  True,  "↩️"),
    ("Avg Session (s)",     "avg_session_s","s",  False, "⏱️"),
    ("KW in Top 3",         "kw_top3",      "",   False, "🥇"),
    ("KW in Top 10",        "kw_top10",     "",   False, "🏅"),
]

cols = st.columns(len(metrics))
for col, (label, field, unit, invert, icon) in zip(cols, metrics):
    curr, abs_d, pct_d = wow_delta(df[field])
    col.metric(
        label=f"{icon} {label}",
        value=f"{curr:,.1f}{unit}" if isinstance(curr, float) else f"{curr:,}{unit}",
        delta=f"{pct_d:+.1f}%",
        delta_color="inverse" if invert else "normal",
    )

# ── Organic Traffic ───────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Organic Traffic (Clicks)</div>', unsafe_allow_html=True)

fig_clicks = px.bar(df, x="week", y="clicks", color_discrete_sequence=["#4CAF50"])
fig_clicks.add_scatter(x=df["week"], y=df["clicks"].rolling(4).mean(),
                        mode="lines", name="4-wk avg", line=dict(color="#1a6e1a", width=2))
fig_clicks.update_layout(height=320, margin=dict(t=10, b=10), legend=dict(orientation="h"))
st.plotly_chart(fig_clicks, use_container_width=True)

# ── Branded vs Non-Branded ────────────────────────────────────────────────────
st.markdown('<div class="section-header">Branded vs Non-Branded Split</div>', unsafe_allow_html=True)

c1, c2 = st.columns([2, 1])

fig_split = go.Figure()
fig_split.add_bar(x=df["week"], y=df["non_branded"], name="Non-Branded", marker_color="#2196F3")
fig_split.add_bar(x=df["week"], y=df["branded"],     name="Branded",     marker_color="#90CAF9")
fig_split.update_layout(barmode="stack", height=300, margin=dict(t=10, b=10),
                         legend=dict(orientation="h"))
c1.plotly_chart(fig_split, use_container_width=True)

latest_branded_pct    = df["branded"].iloc[-1] / df["clicks"].iloc[-1] * 100
latest_nonbranded_pct = 100 - latest_branded_pct
fig_pie = px.pie(
    values=[latest_nonbranded_pct, latest_branded_pct],
    names=["Non-Branded", "Branded"],
    color_discrete_sequence=["#2196F3", "#90CAF9"],
    hole=0.55,
)
fig_pie.update_layout(height=300, margin=dict(t=10, b=10, l=10, r=10),
                       showlegend=True, legend=dict(orientation="h"))
c2.plotly_chart(fig_pie, use_container_width=True)

# ── CTR & Impressions ─────────────────────────────────────────────────────────
st.markdown('<div class="section-header">CTR & Impressions</div>', unsafe_allow_html=True)

fig_ctr = go.Figure()
fig_ctr.add_bar(x=df["week"], y=df["impressions"], name="Impressions",
                marker_color="#E3F2FD", yaxis="y2")
fig_ctr.add_scatter(x=df["week"], y=df["ctr"], name="CTR (%)",
                    mode="lines+markers", line=dict(color="#1565C0", width=2), yaxis="y")
fig_ctr.update_layout(
    height=320,
    margin=dict(t=10, b=10),
    legend=dict(orientation="h"),
    yaxis=dict(title="CTR (%)", side="left"),
    yaxis2=dict(title="Impressions", side="right", overlaying="y", showgrid=False),
)
st.plotly_chart(fig_ctr, use_container_width=True)

# ── Engagement ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Engagement — Bounce Rate & Avg Session Duration</div>',
            unsafe_allow_html=True)

c3, c4 = st.columns(2)

fig_bounce = px.line(df, x="week", y="bounce_rate", markers=True,
                     color_discrete_sequence=["#FF7043"],
                     labels={"bounce_rate": "Bounce Rate (%)"})
fig_bounce.update_layout(height=280, margin=dict(t=10, b=10))
c3.plotly_chart(fig_bounce, use_container_width=True)

fig_session = px.line(df, x="week", y="avg_session_s", markers=True,
                      color_discrete_sequence=["#7B1FA2"],
                      labels={"avg_session_s": "Avg Session (seconds)"})
fig_session.update_layout(height=280, margin=dict(t=10, b=10))
c4.plotly_chart(fig_session, use_container_width=True)

# ── Keyword Rankings ──────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Keyword Rankings</div>', unsafe_allow_html=True)

fig_kw = go.Figure()
fig_kw.add_scatter(x=df["week"], y=df["kw_top3"],  name="Top 3",
                   mode="lines+markers", line=dict(color="#F9A825", width=2))
fig_kw.add_scatter(x=df["week"], y=df["kw_top10"], name="Top 10",
                   mode="lines+markers", line=dict(color="#FDD835", width=1.5, dash="dash"))
fig_kw.update_layout(height=300, margin=dict(t=10, b=10), legend=dict(orientation="h"),
                     yaxis_title="# Keywords")
st.plotly_chart(fig_kw, use_container_width=True)

# ── WoW Summary Table ─────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Week-over-Week Summary Table</div>', unsafe_allow_html=True)

summary_cols = {
    "clicks":       ("Clicks",          "",   False),
    "impressions":  ("Impressions",     "",   False),
    "ctr":          ("CTR (%)",         "%",  False),
    "branded":      ("Branded",         "",   False),
    "non_branded":  ("Non-Branded",     "",   False),
    "bounce_rate":  ("Bounce Rate (%)", "%",  True),
    "avg_session_s":("Avg Session (s)", "s",  False),
    "kw_top3":      ("KW Top 3",        "",   False),
    "kw_top10":     ("KW Top 10",       "",   False),
}

rows = []
for field, (label, unit, invert) in summary_cols.items():
    curr, abs_d, pct_d = wow_delta(df[field])
    rows.append({
        "Metric":        label,
        "This Week":     f"{curr:,.1f}{unit}" if isinstance(curr, float) else f"{curr:,}",
        "Prior Week":    f"{df[field].iloc[-2]:,.1f}{unit}" if isinstance(df[field].iloc[-2], float) else f"{df[field].iloc[-2]:,}",
        "WoW Δ":         f"{pct_d:+.1f}%",
    })

summary_df = pd.DataFrame(rows)
st.dataframe(summary_df, use_container_width=True, hide_index=True)

# ── Raw Data ──────────────────────────────────────────────────────────────────
with st.expander("📄 Raw weekly data"):
    st.dataframe(df.sort_values("week", ascending=False).reset_index(drop=True),
                 use_container_width=True)
    st.download_button("Download CSV", df.to_csv(index=False), "seo_data.csv", "text/csv")

st.caption("Data shown is sample/synthetic. Upload a real CSV via the sidebar to populate with live data.")
