"""
Buffalo Mayoral Elections — Coalition Shift Analysis
Visualizes Byron Brown's neighborhood-level coalition inversion across
2017 general, 2021 primary, and 2021 general elections.
"""

import json
import re
import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
from pathlib import Path

ROOT     = Path(__file__).parent.parent.parent
GEO_DIR  = ROOT / "data" / "geo"
DATA_DIR = ROOT / "data" / "processed"

st.markdown("""
<style>
h1 { font-weight: 800 !important; letter-spacing: -0.5px; margin-bottom: 0.1rem !important; }
h2 { font-weight: 700 !important; border-bottom: 2px solid #e8e8e8; padding-bottom: 5px; margin-top: 1.4rem !important; }
h3 { font-weight: 600 !important; color: #222 !important;
     margin-top: 1.1rem !important; margin-bottom: 0.4rem !important; }
section[data-testid="stSidebar"] h1 { font-size: 1.25rem !important; letter-spacing: 0; }
div[data-testid="stMetricValue"] { font-size: 1.5rem !important; font-weight: 700 !important; }
@media (max-width: 768px) {
    .block-container { padding-left: 0.75rem !important; padding-right: 0.75rem !important; padding-top: 1rem !important; }
    div[data-testid="stMetricValue"] { font-size: 1.2rem !important; }
}
</style>
""", unsafe_allow_html=True)

GROUP_COLORS = {
    "Black community":     "#d62728",
    "Working-class white": "#1f77b4",
    "Affluent white":      "#2ca02c",
    "Mixed / Other":       "#9467bd",
}
GRID_COLOR  = "rgba(0,0,0,0.07)"
AXIS_COLOR  = "rgba(0,0,0,0.15)"

META_COLS = {"year", "election_type", "ward", "ed_num", "ed_label", "shapefile_key"}
NOISE_RE  = re.compile(r"\b(blank|void|scatter|total)", re.IGNORECASE)


# ── Data loading ───────────────────────────────────────────────────────────────

@st.cache_data
def load_eds():
    return gpd.read_file(GEO_DIR / "buffalo_eds.geojson")[["ed_key", "nbhdname"]]

@st.cache_data
def load_base_eds_geo():
    return gpd.read_file(GEO_DIR / "buffalo_eds.geojson")[["ed_key", "nbhdname", "geometry"]]

@st.cache_data
def load_nbhd_geo():
    eds = gpd.read_file(GEO_DIR / "buffalo_eds.geojson")
    return eds.dissolve("nbhdname").reset_index()[["nbhdname", "geometry"]]

@st.cache_data
def load_elections():
    return pd.read_csv(DATA_DIR / "mayoral_all.csv", dtype={"year": str})

@st.cache_data
def load_demographics():
    p = DATA_DIR / "neighborhood_demographics.csv"
    return pd.read_csv(p) if p.exists() else None

@st.cache_data
def load_federal():
    p = DATA_DIR / "federal_by_nbhd.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    # Short label: "2020 President — Biden" etc.
    RACE_SHORT = {
        "president": "President", "congress": "Congress",
        "senate": "Senate", "President and Vice President": "President",
    }
    def _label(r):
        race  = RACE_SHORT.get(r["race_type"], r["race_label"])
        last  = r["dem_candidate"].split()[0] if r["dem_candidate"] else "Dem"
        return f"{r['year']} {race} — {last}"
    df["_label"] = df.apply(_label, axis=1)
    return df


def find_brown_col(df: pd.DataFrame) -> str | None:
    """Return the Brown column that actually has data in this filtered election slice."""
    for col in df.columns:
        if col not in META_COLS and not NOISE_RE.search(col):
            if re.search(r"\bbrown\b", col, re.IGNORECASE):
                if pd.to_numeric(df[col], errors="coerce").notna().any():
                    return col
    return None


def nbhd_vote_pct(elections: pd.DataFrame, year: str, etype: str,
                  eds: pd.DataFrame) -> pd.Series:
    """
    Brown's share of total votes per neighborhood for one election.
    Returns Series indexed by nbhdname, values as 0–100 %.
    """
    sel = elections[(elections["year"] == year) &
                    (elections["election_type"] == etype)].copy()
    brown_col = find_brown_col(sel)
    if brown_col is None:
        return pd.Series(dtype=float, name="val")

    cand_cols = [
        c for c in sel.columns
        if c not in META_COLS and not NOISE_RE.search(c) and
        pd.to_numeric(sel[c], errors="coerce").notna().any()
    ]
    for c in cand_cols:
        sel[c] = pd.to_numeric(sel[c], errors="coerce").fillna(0)

    sel["_brown"] = sel[brown_col]
    sel["_total"] = sel[cand_cols].sum(axis=1)
    sel = sel.merge(eds, left_on="shapefile_key", right_on="ed_key", how="left")
    sel = sel.dropna(subset=["nbhdname"])

    agg = sel.groupby("nbhdname")[["_brown", "_total"]].sum()
    return (agg["_brown"] / agg["_total"].replace(0, float("nan")) * 100).round(2)


def ed_vote_pct(elections: pd.DataFrame, year: str, etype: str,
                eds: pd.DataFrame) -> pd.DataFrame:
    """
    Brown's share of total votes per election district for one election.
    Returns DataFrame with columns [ed_key, nbhdname, pct].
    """
    sel = elections[(elections["year"] == year) &
                    (elections["election_type"] == etype)].copy()
    brown_col = find_brown_col(sel)
    if brown_col is None:
        return pd.DataFrame(columns=["ed_key", "nbhdname", "pct"])

    cand_cols = [
        c for c in sel.columns
        if c not in META_COLS and not NOISE_RE.search(c) and
        pd.to_numeric(sel[c], errors="coerce").notna().any()
    ]
    for c in cand_cols:
        sel[c] = pd.to_numeric(sel[c], errors="coerce").fillna(0)

    sel["_brown"] = sel[brown_col]
    sel["_total"] = sel[cand_cols].sum(axis=1)
    sel["pct"]    = (sel["_brown"] / sel["_total"].replace(0, float("nan")) * 100).round(2)
    sel = sel.merge(eds[["ed_key", "nbhdname"]], left_on="shapefile_key",
                    right_on="ed_key", how="left")
    return sel[["ed_key", "nbhdname", "pct"]].dropna(subset=["ed_key", "nbhdname"])


# ── Load data ──────────────────────────────────────────────────────────────────

eds_map      = load_eds()
base_eds_geo = load_base_eds_geo()
elections_df = load_elections()
demo_df      = load_demographics()
nbhd_geo     = load_nbhd_geo()
fed_df       = load_federal()

if demo_df is None:
    st.error("Run `python src/fetch_demographics.py` first to generate demographic data.")
    st.stop()


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    view = st.radio("Geography", ["Neighborhood", "Election District"])
    st.divider()
    st.markdown("**Demographic thresholds**")
    black_thresh  = st.slider("Min % Black → 'Black community'",       20, 70, 40, 5)
    white_thresh  = st.slider("Min % white → white categories",         30, 70, 50, 5)
    income_thresh = st.slider("Income cutoff working-class / affluent", 30, 80, 50, 5)
    st.divider()
    if fed_df is not None:
        st.markdown("**Partisan reference election**")
        fed_labels = (
            fed_df[["_label", "year", "race_type"]]
            .drop_duplicates("_label")
            .sort_values(["year", "race_type"], ascending=[False, True])
        )
        # Default to 2020 Presidential
        label_list  = fed_labels["_label"].tolist()
        default_idx = next((i for i, l in enumerate(label_list) if "2020" in l and "President" in l), 0)
        fed_choice = st.selectbox(
            "Show Dem % from:",
            fed_labels["_label"].tolist(),
            index=default_idx,
        )
    else:
        fed_choice = None
    st.divider()
    st.caption("ACS 2020 5-year · Erie County BOE")


# ── Demographic typology ───────────────────────────────────────────────────────

def classify(row: pd.Series) -> str:
    pb, pw = row["pct_black"], row["pct_white"]
    inc    = row["median_income"]
    if pb >= black_thresh / 100:
        return "Black community"
    if pw >= white_thresh / 100:
        return "Working-class white" if inc < income_thresh * 1000 else "Affluent white"
    return "Mixed / Other"

demo_df = demo_df.copy()
demo_df["demo_group"] = demo_df.apply(classify, axis=1)
demo_cols = ["nbhdname", "pct_white", "pct_black", "pct_college", "median_income", "demo_group"]


# ── Build vote table (neighborhood or ED) ─────────────────────────────────────

if view == "Neighborhood":
    id_col = "nbhdname"

    b17g = nbhd_vote_pct(elections_df, "2017", "general", eds_map).rename("brown_17g")
    b21p = nbhd_vote_pct(elections_df, "2021", "primary", eds_map).rename("brown_21p")
    b21g = nbhd_vote_pct(elections_df, "2021", "general", eds_map).rename("brown_21g")

    vote = (
        pd.concat([b17g, b21p, b21g], axis=1)
        .dropna(subset=["brown_17g", "brown_21g"])
        .reset_index()
        .rename(columns={"index": "nbhdname"})
    )
    joined = vote.merge(demo_df[demo_cols], on="nbhdname", how="left")

else:
    id_col = "ed_key"

    e17g = ed_vote_pct(elections_df, "2017", "general", eds_map)
    e21p = ed_vote_pct(elections_df, "2021", "primary", eds_map)
    e21g = ed_vote_pct(elections_df, "2021", "general", eds_map)

    vote = (
        e17g.rename(columns={"pct": "brown_17g"})
        .merge(e21g[["ed_key", "pct"]].rename(columns={"pct": "brown_21g"}),
               on="ed_key", how="inner")
        .merge(e21p[["ed_key", "pct"]].rename(columns={"pct": "brown_21p"}),
               on="ed_key", how="left")
        .dropna(subset=["brown_17g", "brown_21g"])
        .reset_index(drop=True)
    )
    # Inherit neighborhood demographics for each ED
    joined = vote.merge(demo_df[demo_cols], on="nbhdname", how="left")

joined["demo_group"] = joined["demo_group"].fillna("Mixed / Other")
joined["delta"]      = joined["brown_21g"] - joined["brown_17g"]
joined["delta_pg"]   = joined["brown_21g"] - joined["brown_21p"]

# Merge selected federal partisan reference (neighborhood level only)
if fed_df is not None and fed_choice:
    ref_slice = fed_df[fed_df["_label"] == fed_choice][["nbhdname", "dem_pct"]].rename(
        columns={"dem_pct": "ref_dem_pct"}
    )
    joined = joined.merge(ref_slice, on="nbhdname", how="left")
else:
    joined["ref_dem_pct"] = float("nan")


# ── Page header ────────────────────────────────────────────────────────────────

st.title("Coalition Shift Analysis")
st.caption(
    "Byron Brown lost the 2021 Democratic primary to India Walton, then won the general "
    "as a write-in by assembling an entirely different coalition — with neighborhoods that "
    "were his weakest in 2017 becoming his strongest."
)

n = len(joined)
r_main  = joined["brown_17g"].corr(joined["brown_21g"])
r_prime = joined["brown_17g"].corr(joined["brown_21p"]) if joined["brown_21p"].notna().sum() > 3 else float("nan")
avg_shift = joined["delta_pg"].mean()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Pearson r  (2017G vs 2021G)",       f"{r_main:.3f}",   help="Negative = coalition inversion")
c2.metric("Pearson r  (2017G vs 2021 primary)", f"{r_prime:.3f}" if not np.isnan(r_prime) else "n/a")
c3.metric("Avg primary→general shift",          f"{avg_shift:+.1f}%")
c4.metric("Election districts" if view == "Election District" else "Neighborhoods", n)

st.divider()


# ── MAP: demographic group classification ──────────────────────────────────────

if view == "Neighborhood":
    geo_demo = nbhd_geo.merge(
        demo_df[["nbhdname", "pct_white", "pct_black", "median_income", "demo_group"]],
        on="nbhdname", how="left",
    )
    map_id_col   = "nbhdname"
    map_title    = "Neighborhood demographic classification"
else:
    geo_demo = base_eds_geo.merge(
        demo_df[["nbhdname", "pct_white", "pct_black", "median_income", "demo_group"]],
        on="nbhdname", how="left",
    )
    map_id_col   = "ed_key"
    map_title    = "Election district demographic classification (inherited from neighborhood)"

geo_demo["demo_group"]    = geo_demo["demo_group"].fillna("Mixed / Other")
geo_demo["pct_white_fmt"] = (geo_demo["pct_white"] * 100).round(1)
geo_demo["pct_black_fmt"] = (geo_demo["pct_black"] * 100).round(1)

geo_json = json.loads(geo_demo.to_json())

fig_map = px.choropleth_map(
    geo_demo,
    geojson=geo_json,
    locations=map_id_col,
    featureidkey=f"properties.{map_id_col}",
    color="demo_group",
    color_discrete_map=GROUP_COLORS,
    category_orders={"demo_group": list(GROUP_COLORS)},
    map_style="carto-positron",
    zoom=10.7,
    center={"lat": 42.886, "lon": -78.878},
    opacity=0.75,
    hover_name=map_id_col,
    hover_data={c: False for c in geo_demo.columns if c != map_id_col},
    height=380,
    title=map_title + " — adjust thresholds in sidebar",
)
# Each categorical choropleth trace only holds its own group's rows, so we
# must assign customdata per-trace (not globally) to keep indices aligned.
hover_tmpl = (
    "<b>%{location}</b><br>"
    "Group: %{customdata[0]}<br>"
    "% white: %{customdata[1]:.0f}   % Black: %{customdata[2]:.0f}<br>"
    "Median income: $%{customdata[3]:,.0f}"
    "<extra></extra>"
)
for trace in fig_map.data:
    grp = trace.name
    mask = geo_demo["demo_group"].fillna("Mixed / Other") == grp
    subset = geo_demo[mask][["demo_group", "pct_white_fmt", "pct_black_fmt",
                              "median_income"]].fillna(0)
    trace.customdata    = subset.values
    trace.hovertemplate = hover_tmpl
fig_map.update_layout(
    margin={"r": 0, "t": 36, "l": 0, "b": 0},
    legend=dict(title="Group", orientation="v"),
)
st.plotly_chart(fig_map, width="stretch", config={"displaylogo": False})

st.divider()


# ── CHART A: 2017G vs 2021G colored by demographic group ─────────────────────

lo = float(min(joined["brown_17g"].min(), joined["brown_21g"].min()) * 0.9)
hi = float(max(joined["brown_17g"].max(), joined["brown_21g"].max()) * 1.05)

# Hover label setup — ED view shows ed_key as title + neighborhood as sub-line
# sub_tmpl_a: Chart A customdata layout has nbhdname at index 6
# sub_tmpl_b: Chart B customdata layout has nbhdname at index 2
if view == "Neighborhood":
    label_col  = "nbhdname"
    sub_tmpl_a = ""
    sub_tmpl_b = ""
else:
    label_col  = "ed_key"
    sub_tmpl_a = "Neighborhood: %{customdata[6]}<br>"
    sub_tmpl_b = "Neighborhood: %{customdata[2]}<br>"

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("2017 vs 2021 General")
    fig_a = go.Figure()

    for group, color in GROUP_COLORS.items():
        g = joined[joined["demo_group"] == group]
        if g.empty:
            continue
        fig_a.add_trace(go.Scatter(
            x=g["brown_17g"], y=g["brown_21g"],
            mode="markers", name=group,
            marker=dict(color=color, size=11, opacity=0.85,
                        line=dict(color="white", width=0.8)),
            customdata=np.column_stack([
                g[label_col].values,
                g["brown_21p"].fillna(float("nan")).values,
                (g["pct_white"] * 100).round(1).values,
                (g["pct_black"] * 100).round(1).values,
                g["median_income"].values,
                g["delta"].values,
                g["nbhdname"].values,
            ]),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                + sub_tmpl_a +
                "2017 general: %{x:.1f}%<br>"
                "2021 general: %{y:.1f}%  (%{customdata[5]:+.1f})<br>"
                "2021 primary: %{customdata[1]:.1f}%<br>"
                "% white: %{customdata[2]:.0f}   "
                "% Black: %{customdata[3]:.0f}<br>"
                "Median income: $%{customdata[4]:,.0f}"
                "<extra></extra>"
            ),
        ))

    fig_a.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi,
                    line=dict(color="#cccccc", dash="dot", width=1), layer="below")
    fig_a.add_annotation(x=hi, y=hi, text="y = x", showarrow=False,
                         font=dict(color="#aaaaaa", size=10), xanchor="left")

    fig_a.update_layout(
        xaxis=dict(title="2017 General — Brown %", range=[lo, hi],
                   gridcolor=GRID_COLOR, zeroline=False),
        yaxis=dict(title="2021 General — Brown %", range=[lo, hi],
                   gridcolor=GRID_COLOR, zeroline=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(t=40, b=40, l=50, r=20),
        height=440,
    )
    fig_a.update_xaxes(gridcolor=GRID_COLOR, zeroline=False)
    fig_a.update_yaxes(gridcolor=GRID_COLOR, zeroline=False)
    st.plotly_chart(fig_a, width="stretch", config={"displaylogo": False})
    st.caption(f"Pearson r = {r_main:.3f}  ·  Points below the diagonal lost support; above gained.")


# ── CHART B: Arrow chart — 2021 primary vs general at same x (2017) ───────────

with col_b:
    st.subheader("Primary vs General Shift (2021)")
    unit = "area's" if view == "Election District" else "neighborhood's"
    st.caption(f"Each line connects an {unit} 2021 primary % (open) to its 2021 general % (filled). "
               "X-axis anchors it to 2017 general performance.")

    arrow_df = joined.dropna(subset=["brown_21p"])
    fig_b    = go.Figure()
    added    = set()

    for group, color in GROUP_COLORS.items():
        g = arrow_df[arrow_df["demo_group"] == group]
        if g.empty:
            continue

        # Batch vertical line segments (x constant, y goes from 2021P to 2021G)
        seg_x, seg_y = [], []
        for _, row in g.iterrows():
            seg_x += [row["brown_17g"], row["brown_17g"], None]
            seg_y += [row["brown_21p"],  row["brown_21g"],  None]

        fig_b.add_trace(go.Scatter(
            x=seg_x, y=seg_y, mode="lines",
            line=dict(color=color, width=1.8),
            showlegend=False, hoverinfo="skip",
        ))

        # Open circle = 2021 primary
        fig_b.add_trace(go.Scatter(
            x=g["brown_17g"], y=g["brown_21p"],
            mode="markers",
            name=group, showlegend=(group not in added),
            marker=dict(color=color, size=8, symbol="circle-open",
                        line=dict(width=2, color=color)),
            customdata=np.column_stack([g[label_col].values, g["delta_pg"].values,
                                        g["nbhdname"].values]),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                + sub_tmpl_b +
                "2021 Primary: %{y:.1f}%<br>"
                "Primary→general shift: %{customdata[1]:+.1f}%"
                "<extra></extra>"
            ),
        ))
        added.add(group)

        # Filled circle = 2021 general
        fig_b.add_trace(go.Scatter(
            x=g["brown_17g"], y=g["brown_21g"],
            mode="markers", showlegend=False,
            marker=dict(color=color, size=8, symbol="circle"),
            customdata=np.column_stack([g[label_col].values, g["delta_pg"].values,
                                        g["nbhdname"].values]),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                + sub_tmpl_b +
                "2021 General: %{y:.1f}%<br>"
                "Primary→general shift: %{customdata[1]:+.1f}%"
                "<extra></extra>"
            ),
        ))

    fig_b.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi,
                    line=dict(color="#cccccc", dash="dot", width=1), layer="below")

    # Annotations explaining marker types
    fig_b.add_annotation(
        x=0.02, y=0.97, xref="paper", yref="paper",
        text="<b>Open</b> = 2021 Primary   <b>Filled</b> = 2021 General",
        showarrow=False, font=dict(size=11, color="#555555"),
        align="left", xanchor="left",
    )

    fig_b.update_layout(
        xaxis=dict(title="2017 General — Brown % (reference)",
                   gridcolor=GRID_COLOR, zeroline=False),
        yaxis=dict(title="Brown %", gridcolor=GRID_COLOR, zeroline=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(t=40, b=40, l=50, r=20),
        height=440,
    )
    fig_b.update_xaxes(gridcolor=GRID_COLOR, zeroline=False)
    fig_b.update_yaxes(gridcolor=GRID_COLOR, zeroline=False)
    st.plotly_chart(fig_b, width="stretch", config={"displaylogo": False})

st.divider()


# ── REGRESSION ─────────────────────────────────────────────────────────────────

st.subheader("Regression: Predictors of Coalition Inversion")

reg = joined.dropna(subset=["brown_17g", "brown_21g", "pct_white", "median_income"]).copy()
reg["income_k"] = reg["median_income"] / 1000

import statsmodels.formula.api as smf


def coef_table(model) -> pd.DataFrame:
    rows = []
    for term in model.params.index:
        p = model.pvalues[term]
        rows.append({
            "Term": term,
            "beta": round(model.params[term], 3),
            "SE":   round(model.bse[term], 3),
            "t":    round(model.tvalues[term], 2),
            "p":    "< 0.001" if p < 0.001 else f"{p:.3f}",
            "sig":  ("***" if p < 0.001 else "**" if p < 0.01
                     else "*" if p < 0.05 else "." if p < 0.1 else ""),
        })
    return pd.DataFrame(rows)


def fit_model(formula: str, data: pd.DataFrame):
    try:
        return smf.ols(formula, data=data).fit(), None
    except Exception as exc:
        return None, str(exc)


reg_col, interp_col = st.columns([3, 2])

with reg_col:
    model_specs = [
        ("M1: baseline",          "brown_21g ~ brown_17g"),
        ("M2: + race & income",   "brown_21g ~ brown_17g + pct_white + income_k"),
        ("M3: + interaction",     "brown_21g ~ brown_17g + pct_white * income_k"),
        ("M4: delta ~ race×inc",  "delta ~ pct_white * income_k"),
    ]
    tabs = st.tabs([label for label, _ in model_specs])
    for tab, (label, formula) in zip(tabs, model_specs):
        with tab:
            model, err = fit_model(formula, reg)
            if err:
                st.error(f"Model failed: {err}")
            else:
                st.dataframe(coef_table(model), hide_index=True, width="stretch")
                st.caption(
                    f"R² = {model.rsquared:.3f}  ·  N = {int(model.nobs)}"
                    "  ·  Signif: *** p < 0.001  ** p < 0.01  * p < 0.05  . p < 0.1"
                )

with interp_col:
    st.markdown("**What the models test**")
    st.markdown(
        "**M1** — Is the 2017→2021 correlation negative? "
        "The coefficient on `brown_17g` tests the raw coalition inversion.\n\n"
        "**M2** — Does the inversion persist after controlling for neighborhood "
        "racial composition and income?\n\n"
        "**M3** — The `pct_white × income_k` interaction is the key term. "
        "It tests whether income predicts Brown's 2021 support *differently* in "
        "white vs. Black neighborhoods. Expected: lower income boosts Brown in "
        "white neighborhoods (South Buffalo) but not in Black neighborhoods.\n\n"
        "**M4** — Same interaction on the *change* (2021G − 2017G), isolating "
        "what predicts the shift rather than the level."
    )
    st.divider()
    st.markdown("**Mean vote share by group**")
    shift_by_group = (
        joined.groupby("demo_group")
        [["brown_17g", "brown_21p", "brown_21g", "delta", "delta_pg"]]
        .mean().round(1)
        .rename(columns={
            "brown_17g": "2017G",
            "brown_21p": "2021P",
            "brown_21g": "2021G",
            "delta":     "17G→21G",
            "delta_pg":  "21P→21G",
        })
    )
    st.dataframe(shift_by_group, width="stretch")


# ── PARTISAN CONTEXT ───────────────────────────────────────────────────────────

st.divider()
st.subheader("Partisan Context")
st.caption(
    "Buffalo is an overwhelmingly Democratic city. The coalition inversion shown above "
    "is an *intra-Democratic* phenomenon — not a partisan defection. The chart below "
    "plots each neighborhood's Brown 2021 general % against its federal Democratic % "
    "from the reference election selected in the sidebar."
)

if joined["ref_dem_pct"].notna().sum() < 3:
    st.info("Run `python src/parse_federal.py` to generate federal reference data.")
else:
    ctx_data = joined.dropna(subset=["ref_dem_pct", "brown_21g"])
    ref_lo   = float(ctx_data["ref_dem_pct"].min() * 0.92)
    ref_hi   = float(min(ctx_data["ref_dem_pct"].max() * 1.04, 100))

    fig_ctx = go.Figure()
    for group, color in GROUP_COLORS.items():
        g = ctx_data[ctx_data["demo_group"] == group]
        if g.empty:
            continue
        fig_ctx.add_trace(go.Scatter(
            x=g["ref_dem_pct"], y=g["brown_21g"],
            mode="markers", name=group,
            marker=dict(color=color, size=11, opacity=0.85,
                        line=dict(color="white", width=0.8)),
            customdata=np.column_stack([
                g[label_col].values,
                g["ref_dem_pct"].values,
                g["brown_21g"].values,
                g["nbhdname"].values,
            ]),
            hovertemplate=(
                f"<b>%{{customdata[0]}}</b><br>"
                + ("Neighborhood: %{customdata[3]}<br>" if view == "Election District" else "")
                + f"Federal Dem ({fed_choice}): %{{customdata[1]:.1f}}%<br>"
                "Brown 2021 General: %{customdata[2]:.1f}%"
                "<extra></extra>"
            ),
        ))

    # Reference line at 50% federal Dem (partisan threshold)
    fig_ctx.add_vline(x=50, line_dash="dot", line_color="#cccccc", line_width=1)
    fig_ctx.add_annotation(
        x=50.5, y=ref_hi * 0.98, text="50% Dem threshold",
        showarrow=False, font=dict(size=10, color="#aaaaaa"), xanchor="left",
    )

    ctx_r = ctx_data["ref_dem_pct"].corr(ctx_data["brown_21g"])
    fig_ctx.update_layout(
        xaxis=dict(title=f"Federal Dem % ({fed_choice})", range=[ref_lo, ref_hi],
                   gridcolor=GRID_COLOR, zeroline=False),
        yaxis=dict(title="Brown 2021 General %", range=[lo, hi],
                   gridcolor=GRID_COLOR, zeroline=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(t=40, b=40, l=50, r=20),
        height=420,
    )
    fig_ctx.update_xaxes(gridcolor=GRID_COLOR, zeroline=False)
    fig_ctx.update_yaxes(gridcolor=GRID_COLOR, zeroline=False)
    st.plotly_chart(fig_ctx, width="stretch", config={"displaylogo": False})
    st.caption(
        f"Pearson r = {ctx_r:.3f}  ·  All neighborhoods to the right of the dotted line "
        "voted majority-Democratic in the reference federal election — demonstrating that "
        "variation in Brown's write-in support operates entirely within the Democratic electorate."
    )

    # City-wide summary table for reference
    if fed_df is not None and fed_choice:
        city_row = fed_df[fed_df["_label"] == fed_choice].groupby("_label").agg(
            dem_votes=("dem_votes","sum"), rep_votes=("rep_votes","sum"),
            other_votes=("other_votes","sum"), total_votes=("total_votes","sum"),
            dem_candidate=("dem_candidate","first"), rep_candidate=("rep_candidate","first"),
        ).reset_index()
        if not city_row.empty:
            r = city_row.iloc[0]
            tot = r["total_votes"]
            st.caption(
                f"City-wide ({fed_choice}): **{r['dem_candidate']}** "
                f"{r['dem_votes']/tot*100:.1f}%  ·  "
                f"**{r['rep_candidate']}** {r['rep_votes']/tot*100:.1f}%  ·  "
                f"Other {r['other_votes']/tot*100:.1f}%"
            )
