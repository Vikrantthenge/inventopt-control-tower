
import html
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from model import sample, plan

# ==========================================================
# INVENTOPT 2.0
# Enterprise Inventory Intelligence & MEIO Control Tower
# Developed by Vikrant Thenge
# ==========================================================

st.set_page_config(
    page_title="InventOpt 2.0 | Inventory Control Tower",
    page_icon="📦",
    layout="wide"
)

# ----------------------------------------------------------
# CORPORATE THEME
# ----------------------------------------------------------

NAVY = "#102b46"
BLUE = "#2563a6"
TEAL = "#078a75"
RED = "#dc4545"
AMBER = "#d99a27"

COLORS = {
    "Below target": RED,
    "On target": TEAL,
    "Above target": AMBER
}

st.markdown("""
<style>
.block-container {
    padding-top: 2rem;
    max-width: 1500px;
}

.hero {
    background: linear-gradient(110deg, #102b46, #205b85);
    color: white;
    padding: 28px;
    border-radius: 16px;
    margin-bottom: 20px;
}

.hero h1 {
    color: white;
    margin: 0;
    font-size: 2.1rem;
}

.hero p {
    color: #dceaf5;
    margin: 8px 0 0;
}

.kpi {
    background: #f4f8fc;
    border: 1px solid #dce6ef;
    border-radius: 12px;
    padding: 17px;
    min-height: 125px;
    color: #102b46;
    border-top: 4px solid #2563a6;
}

.kpi small {
    color: #52687b;
}

.kpi strong {
    display: block;
    font-size: 1.8rem;
    margin: 8px 0;
}

.stTabs [data-baseweb="tab"] {
    font-weight: 600;
}

[data-testid="stSidebar"] {
    border-right: 1px solid #dce6ef;
}
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------
# HEADER
# ----------------------------------------------------------

st.markdown("""
<div class="hero">
    <small>DECISION ANALYTICS • SUPPLY CHAIN PORTFOLIO</small>
    <h1>📦 InventOpt 2.0</h1>
    <p>Enterprise Inventory Intelligence &amp; MEIO Control Tower</p>
    <p>Monitor • Forecast • Optimize • Plan</p>
</div>
""", unsafe_allow_html=True)

st.caption(
    "Independent demonstration | Synthetic retail data by default "
    "| Stock snapshots are simulated, not actual client results."
)

# ----------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------

with st.sidebar:

    st.header("🎛 Planning assumptions")

    upload = st.file_uploader(
        "Optional demand CSV",
        type="csv"
    )

    service = st.slider(
        "Target cycle service level (%)",
        80, 99, 95
    ) / 100

    sl = st.slider(
        "Store lead time (weeks)",
        1, 4, 1
    )

    dl = st.slider(
        "DC lead time (weeks)",
        1, 8, 2
    )

    growth = st.slider(
        "Annual demand growth (%)",
        -20, 30, 8
    ) / 100

    stock_factor = st.slider(
        "Simulated stock vs target (%)",
        30, 170, 100
    ) / 100

    st.caption(
        "Adjust assumptions to compare planning scenarios."
    )

# ----------------------------------------------------------
# LOAD AND VALIDATE DATA
# ----------------------------------------------------------

try:

    path = Path(__file__).with_name("retail_demand.csv")

    if upload is not None:
        df = pd.read_csv(upload)
    elif path.exists():
        df = pd.read_csv(path)
    else:
        df = sample()

    df = df[
        ["date", "sku", "dc", "store", "demand", "unit_cost"]
    ].copy()

    df["date"] = pd.to_datetime(df.date, errors="raise")

    for c in ["demand", "unit_cost"]:
        df[c] = pd.to_numeric(df[c], errors="raise")

    if (
        df.empty
        or df.isna().any().any()
        or not np.isfinite(
            df[["demand", "unit_cost"]]
        ).all().all()
        or (df[["demand", "unit_cost"]] < 0).any().any()
    ):
        raise ValueError(
            "Use complete, finite, nonnegative data."
        )

    df["date"] = df.date.dt.to_period("W-SUN").dt.start_time

    for c in ["sku", "dc", "store"]:
        df[c] = df[c].astype(str)

except Exception as e:
    st.error(f"Invalid CSV: {e}")
    st.stop()

# ----------------------------------------------------------
# INTERACTIVE FILTERS
# ----------------------------------------------------------

with st.sidebar:

    st.header("🔎 Network filters")

    for col, label in [
        ("sku", "Product"),
        ("dc", "Distribution centre"),
        ("store", "Store")
    ]:

        opts = sorted(df[col].unique())

        chosen = st.multiselect(
            label,
            opts,
            default=opts,
            key=col
        )

        df = df[df[col].isin(chosen)]

    st.caption(
        "Region is represented by distribution centre."
    )

if df.empty:
    st.info("Select at least one product, DC and store.")
    st.stop()

# ----------------------------------------------------------
# INVENTORY OPTIMIZATION MODEL
# ----------------------------------------------------------

a, b = plan(df, service, sl, dl)

rng = np.random.default_rng(8)

a["simulated_stock"] = np.round(
    a.target_stock
    * stock_factor
    * rng.uniform(0.55, 1.45, len(a))
)

a["gap"] = a.simulated_stock - a.target_stock

a["status"] = np.select(
    [
        a.gap < -0.15 * a.target_stock,
        a.gap > 0.15 * a.target_stock
    ],
    [
        "Below target",
        "Above target"
    ],
    default="On target"
)

a["reorder_qty"] = np.ceil(
    (-a.gap).clip(lower=0)
)

a["excess_units"] = a.gap.clip(lower=0)

a["excess_value"] = (
    a.excess_units * a.unit_cost
)

b["buffer_saving"] = (
    b.independent_buffer - b.pooled_buffer
).clip(lower=0)

low = a[a.status == "Below target"]
high = a[a.status == "Above target"]
on = a[a.status == "On target"]

# ----------------------------------------------------------
# REUSABLE FUNCTIONS
# ----------------------------------------------------------

def kpi(col, label, value, detail, color=BLUE):

    col.markdown(
        f"""
        <div class="kpi" style="border-top-color:{color}">
            <small>{html.escape(label)}</small>
            <strong>{html.escape(str(value))}</strong>
            <small>{html.escape(detail)}</small>
        </div>
        """,
        unsafe_allow_html=True
    )


def chart(fig):

    fig.update_layout(
        template="plotly_white",
        font=dict(family="Arial", color=NAVY),
        margin=dict(l=15, r=15, t=55, b=20),
        legend_title_text=""
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={"displaylogo": False}
    )


def table(data):

    st.dataframe(
        data.round(2),
        width="stretch",
        hide_index=True
    )


def download(label, data, name):

    st.download_button(
        label,
        data.to_csv(index=False),
        name,
        mime="text/csv"
    )

# ----------------------------------------------------------
# EXECUTIVE KPI CARDS
# ----------------------------------------------------------

cols = st.columns(4)

kpi(
    cols[0],
    "📈 Weekly demand",
    f"{a.weekly_forecast.sum():,.0f} units",
    "Eight-week average"
)

kpi(
    cols[1],
    "💰 Store target value",
    f"₹{a.target_value.sum():,.0f}",
    "Indicative inventory investment"
)

kpi(
    cols[2],
    "⚠ Below target",
    len(low),
    "Product–store combinations",
    RED
)

kpi(
    cols[3],
    "🏭 DC pooling potential",
    f"{b.buffer_saving.sum():,.0f} units",
    "Indicative safety buffer reduction",
    TEAL
)

st.write("")

# ----------------------------------------------------------
# DASHBOARD NAVIGATION
# ----------------------------------------------------------

t1, t2, t3, t4, t5 = st.tabs([
    "📊 Executive overview",
    "📈 Demand forecast",
    "🌐 MEIO network",
    "🎯 3-year plan",
    "📋 Action centre"
])

# ==========================================================
# TAB 1: EXECUTIVE OVERVIEW
# ==========================================================

with t1:

    st.subheader("Executive intelligence")

    if len(low):

        st.warning(
            f"{len(low)} product–store combinations "
            f"are below target. Review replenishment of "
            f"{low.reorder_qty.sum():,.0f} units "
            "in these combinations."
        )

    else:
        st.success(
            "No combinations are below the 15% alert threshold."
        )

    st.info(
        f"{len(high)} combinations are above target; "
        "review excess stock before placing new orders. "
        f"Estimated DC pooling potential: "
        f"{b.buffer_saving.sum():,.0f} units."
    )

    l, r = st.columns([3, 2])

    with l:

        fig = px.bar(
            a.groupby(["dc", "status"], as_index=False).size(),
            x="dc",
            y="size",
            color="status",
            color_discrete_map=COLORS,
            barmode="group",
            labels={
                "size": "Product–store combinations",
                "dc": "Distribution centre"
            },
            title="Stock risk by distribution centre"
        )

        chart(fig)

    with r:

        fig = px.pie(
            a,
            names="status",
            hole=0.65,
            color="status",
            color_discrete_map=COLORS,
            title="Inventory health mix"
        )

        chart(fig)

    # Inventory risk heatmap

    st.subheader("Inventory risk heatmap")

    heat = a.assign(
        location=a.dc + " / " + a.store,
        coverage=np.where(
            a.target_stock > 0,
            a.simulated_stock
            / a.target_stock.replace(0, np.nan) * 100,
            np.nan
        )
    ).pivot(
        index="sku",
        columns="location",
        values="coverage"
    )

    fig = px.imshow(
        heat,
        aspect="auto",
        color_continuous_scale=[
            [0, RED],
            [0.4249, RED],
            [0.425, TEAL],
            [0.575, TEAL],
            [0.5751, AMBER],
            [1, AMBER]
        ],
        zmin=0,
        zmax=200,
        labels={"color": "% of target"},
        title="Stock as percentage of target"
    )

    chart(fig)

    st.caption(
        "🔴 Below 85%: shortage alert | "
        "🟢 85–115%: on target | "
        "🟠 Above 115%: excess alert. "
        "Zero target is shown as missing."
    )

# ==========================================================
# TAB 2: DEMAND FORECASTING
# ==========================================================

with t2:

    st.subheader("Demand forecasting & validation")

    h = df.groupby("date").demand.sum().sort_index()

    horizon = st.slider(
        "Forecast horizon (weeks)",
        4, 26, 12
    )

    future = pd.date_range(
        h.index[-1] + pd.Timedelta(weeks=1),
        periods=horizon,
        freq="W-MON"
    )

    pred = h.shift(1).rolling(8).mean()

    valid = pred.notna()

    denom = h[valid].abs().sum()

    forecast_value = h.tail(8).mean()

    wape = (
        100 * (h[valid] - pred[valid]).abs().sum() / denom
        if denom else None
    )

    c = st.columns(3)

    c[0].metric(
        "Weekly forecast",
        f"{forecast_value:,.0f} units"
    )

    c[1].metric(
        "Rolling WAPE",
        f"{wape:.1f}%" if wape is not None else "N/A"
    )

    c[2].metric(
        "Forecast horizon",
        f"{horizon} weeks"
    )

    fig = go.Figure()

    fig.add_scatter(
        x=h.index,
        y=h.values,
        name="Historical demand",
        line=dict(color=BLUE)
    )

    fig.add_scatter(
        x=[h.index[-1], *future],
        y=[h.iloc[-1], *([forecast_value] * horizon)],
        name="Forecast",
        line=dict(color=TEAL, dash="dash")
    )

    fig.update_layout(
        title="Historical demand and moving-average forecast",
        yaxis_title="Units"
    )

    chart(fig)

    forecast_df = pd.DataFrame({
        "date": future,
        "forecast_units": forecast_value
    })

    download(
        "📥 Download forecast",
        forecast_df,
        "forecast.csv"
    )

    st.caption(
        "Eight-week moving average with rolling one-step "
        "backtest. Historical error does not guarantee future "
        "accuracy; missing weeks are not imputed."
    )

# ==========================================================
# TAB 3: MULTI-ECHELON INVENTORY OPTIMIZATION
# ==========================================================

with t3:

    st.subheader("Multi-echelon inventory network")

    dcs = sorted(a.dc.unique())

    locations = a[["dc", "store"]].drop_duplicates()

    labels = (
        ["Supplier (illustrative)"]
        + dcs
        + [
            f"{r.dc} / {r.store}"
            for r in locations.itertuples()
        ]
    )

    sources = []
    targets = []
    values = []

    for i, dc in enumerate(dcs):

        qty = float(
            a.loc[a.dc == dc, "weekly_forecast"].sum()
        )

        sources.append(0)
        targets.append(i + 1)
        values.append(qty)

    for j, r in enumerate(locations.itertuples()):

        sources.append(dcs.index(r.dc) + 1)

        targets.append(1 + len(dcs) + j)

        qty = float(
            a.loc[
                (a.dc == r.dc) & (a.store == r.store),
                "weekly_forecast"
            ].sum()
        )

        values.append(qty)

    fig = go.Figure(
        go.Sankey(
            node=dict(
                label=labels,
                pad=18,
                color=(
                    [NAVY]
                    + [BLUE] * len(dcs)
                    + [TEAL] * len(locations)
                )
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values
            )
        )
    )

    fig.update_layout(
        title="Illustrative weekly demand flow (units)"
    )

    chart(fig)

    pooled = b.groupby(
        "dc",
        as_index=False
    )[
        ["pooled_buffer", "independent_buffer"]
    ].sum().melt(
        id_vars="dc",
        var_name="method",
        value_name="units"
    )

    pooled["method"] = pooled.method.map({
        "pooled_buffer": "Pooled buffer",
        "independent_buffer": "Independent buffers"
    })

    fig = px.bar(
        pooled,
        x="dc",
        y="units",
        color="method",
        barmode="group",
        color_discrete_sequence=[TEAL, BLUE],
        title="DC safety stock: pooled vs independent"
    )

    chart(fig)

    table(b)

    download(
        "📥 Download DC inventory plan",
        b,
        "dc_plan.csv"
    )

    st.info(
        "MEIO-inspired two-echelon heuristic using observed "
        "demand covariance. Not a globally optimized solver; "
        "no supply constraints or end-to-end service simulation."
    )

# ==========================================================
# TAB 4: THREE-YEAR LONG-RANGE PLANNING
# ==========================================================

with t4:

    st.subheader("Long-range inventory planning")

    base = a.weekly_forecast.sum() * 52

    value = (
        a.target_value.sum()
        + (b.target_stock * b.unit_cost).sum()
    )

    p = pd.DataFrame([
        {
            "year": f"Year {i}",
            "annual_demand": base * (1 + growth) ** i,
            "indicative_network_stock_value":
                value * (1 + growth) ** i
        }
        for i in range(1, 4)
    ])

    l, r = st.columns(2)

    with l:

        chart(
            px.bar(
                p,
                x="year",
                y="annual_demand",
                title="Annual demand scenario",
                color_discrete_sequence=[BLUE]
            )
        )

    with r:

        chart(
            px.bar(
                p,
                x="year",
                y="indicative_network_stock_value",
                title="Inventory investment scenario (₹)",
                color_discrete_sequence=[TEAL]
            )
        )

    table(p)

    download(
        "📥 Download 3-year strategic plan",
        p,
        "three_year_plan.csv"
    )

    st.caption(
        "Assumes constant costs and lead times with "
        "proportional stock scaling. Scenario, not a "
        "financial forecast."
    )

# ==========================================================
# TAB 5: INVENTORY ACTION CENTRE
# ==========================================================

with t5:

    st.subheader("Prioritized inventory actions")

    a["recommendation"] = np.select(
        [
            a.status == "Below target",
            a.status == "Above target"
        ],
        [
            "Review replenishment",
            "Review transfer / pause orders"
        ],
        default="Monitor"
    )

    status = st.multiselect(
        "Risk status",
        list(COLORS),
        default=list(COLORS)
    )

    view = a[
        a.status.isin(status)
    ].sort_values(
        "reorder_qty",
        ascending=False
    )

    table(
        view[[
            "sku",
            "dc",
            "store",
            "weekly_forecast",
            "safety_stock",
            "target_stock",
            "simulated_stock",
            "status",
            "reorder_qty",
            "excess_value",
            "recommendation"
        ]]
    )

    download(
        "📥 Download inventory action plan",
        view,
        "store_actions.csv"
    )

    st.caption(
        "Recommendations are rule-based decision support, "
        "not automatic orders. Below target does not establish "
        "an actual stockout."
    )

# ==========================================================
# PERSONAL BRANDING & FOOTER
# ==========================================================

st.divider()

st.markdown("""
<div style="text-align:center; padding:20px;">
    <h4>Developed by Vikrant Thenge</h4>
    <p>Operations &amp; Decision Analytics Professional</p>
    <a href="https://github.com/Vikrantthenge" target="_blank">
        <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/github/github-original.svg"
        width="30">
    </a>
    &nbsp;&nbsp;
    <a href="https://www.linkedin.com/in/vthenge/" target="_blank">
        <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/linkedin/linkedin-original.svg"
        width="30">
    </a>
    <p style="font-size:13px; margin-top:15px;">
        Python • Streamlit • Plotly • Decision Science • Inventory Analytics
    </p>
</div>
""", unsafe_allow_html=True)

st.caption(
    "InventOpt 2.0 | Independent Analytics Portfolio Project"
)
