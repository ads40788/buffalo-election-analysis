"""
Buffalo Mayoral Elections — Preliminary Results
Narrative storyboard: coalition inversion (2017-2021) + the three-coalition
theory illustrated by the 2025 Democratic primary.
"""

import json
import re
import numpy as np
import pandas as pd
import geopandas as gpd
import plotly.graph_objects as go
import plotly.express as px
import statsmodels.formula.api as smf
import streamlit as st
from pathlib import Path

ROOT     = Path(__file__).parent.parent.parent
GEO_DIR  = ROOT / "data" / "geo"
DATA_DIR = ROOT / "data" / "processed"

st.markdown("""
<style>
h1 { font-weight: 800 !important; letter-spacing: -0.5px; margin-bottom: 0.1rem !important; }
h2 { font-weight: 700 !important; border-bottom: 2px solid #e8e8e8; padding-bottom: 5px; margin-top: 1.6rem !important; }
h3 { font-weight: 600 !important; color: #222 !important;
     border-left: 3px solid #4e79a7; padding-left: 9px;
     margin-top: 1.1rem !important; margin-bottom: 0.4rem !important; }
div[data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: 700 !important; }
</style>
""", unsafe_allow_html=True)

GRID_COLOR = "rgba(0,0,0,0.07)"
META_COLS  = {"year", "election_type", "ward", "ed_num", "ed_label", "shapefile_key"}
NOISE_RE   = re.compile(r"\b(blank|void|scatter|total)", re.IGNORECASE)

# Coalition-group colors (consistent with Coalition Analysis page)
GROUP_COLORS = {
    "Black community":     "#d62728",
    "Working-class white": "#1f77b4",
    "Affluent white":      "#2ca02c",
    "Mixed / Other":       "#9467bd",
}

# 2025 candidate palette
CAND_COLORS = {
    "Ryan":     "#2ca02c",   # progressive
    "Scanlon":  "#1f77b4",   # South Buffalo
    "Whitfield":"#d62728",   # Black community
    "Wyatt":    "#ff7f0e",   # Black community
    "Other":    "#aaaaaa",
}

MAP_CFG = dict(map_style="carto-positron", zoom=10.7,
               center={"lat": 42.886, "lon": -78.878})

# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data
def load_geo():
    eds   = gpd.read_file(GEO_DIR / "buffalo_eds.geojson")
    nbhds = eds.dissolve("nbhdname").reset_index()[["nbhdname", "geometry"]]
    eds_map = eds[["ed_key", "nbhdname"]]
    return nbhds, eds_map

@st.cache_data
def load_elections():
    return pd.read_csv(DATA_DIR / "mayoral_all.csv", dtype={"year": str})

@st.cache_data
def load_demo():
    p = DATA_DIR / "neighborhood_demographics.csv"
    return pd.read_csv(p) if p.exists() else None

nbhd_geo, eds_map = load_geo()
elections_df       = load_elections()
demo_df            = load_demo()

if demo_df is None:
    st.error("Run `python src/fetch_demographics.py` first.")
    st.stop()

# ── Helpers ───────────────────────────────────────────────────────────────────

def find_col(df, pattern):
    """Return first column matching regex that has any numeric data."""
    for col in df.columns:
        if col in META_COLS or NOISE_RE.search(col):
            continue
        if re.search(pattern, col, re.IGNORECASE):
            if pd.to_numeric(df[col], errors="coerce").notna().any():
                return col
    return None


def nbhd_pct(elections, year, etype, candidate_re, eds):
    """Brown (or any candidate) share per neighborhood → Series indexed by nbhdname."""
    sel = elections[(elections["year"] == year) &
                    (elections["election_type"] == etype)].copy()
    target = find_col(sel, candidate_re)
    if target is None:
        return pd.Series(dtype=float)
    cand_cols = [c for c in sel.columns if c not in META_COLS and not NOISE_RE.search(c)
                 and pd.to_numeric(sel[c], errors="coerce").notna().any()]
    for c in cand_cols:
        sel[c] = pd.to_numeric(sel[c], errors="coerce").fillna(0)
    sel["_t"] = sel[target]
    sel["_n"] = sel[cand_cols].sum(axis=1)
    sel = sel.merge(eds, left_on="shapefile_key", right_on="ed_key", how="left").dropna(subset=["nbhdname"])
    agg = sel.groupby("nbhdname")[["_t", "_n"]].sum()
    return (agg["_t"] / agg["_n"].replace(0, float("nan")) * 100).round(2)


def classify_demo(row, black_t=0.40, white_t=0.50, inc_t=50_000):
    pb, pw = row["pct_black"], row["pct_white"]
    if pb >= black_t:
        return "Black community"
    if pw >= white_t:
        return "Working-class white" if row["median_income"] < inc_t else "Affluent white"
    return "Mixed / Other"


def make_choropleth(geo_df, col, title, colorscale="RdYlBu", zmid=50,
                    zmin=0, zmax=100, height=320):
    geo_json = json.loads(geo_df.to_json())
    id_col   = "nbhdname"
    fig = px.choropleth_map(
        geo_df, geojson=geo_json, locations=id_col,
        featureidkey=f"properties.{id_col}",
        color=col, color_continuous_scale=colorscale,
        range_color=[zmin, zmax],
        **MAP_CFG, opacity=0.78, height=height,
        hover_name=id_col,
        hover_data={c: False for c in geo_df.columns if c != id_col},
    )
    pct_vals = geo_df[col].fillna(0).values
    fig.update_traces(
        hovertemplate="<b>%{location}</b><br>" + f"{title}: %{{z:.1f}}%<extra></extra>",
    )
    fig.update_layout(
        margin={"r": 0, "t": 32, "l": 0, "b": 0},
        title=dict(text=title, font=dict(size=13)),
        coloraxis_colorbar=dict(
            title="%", thickness=10, len=0.55,
            tickformat=".0f",
        ),
        coloraxis_cmid=zmid,
    )
    return fig


# ── Classify neighborhoods ────────────────────────────────────────────────────

demo_df = demo_df.copy()
demo_df["demo_group"] = demo_df.apply(classify_demo, axis=1)

# ── Compute neighborhood vote shares ─────────────────────────────────────────

b17g = nbhd_pct(elections_df, "2017", "general", r"\bbrown\b", eds_map)
b21p = nbhd_pct(elections_df, "2021", "primary", r"\bbrown\b", eds_map)
b21g = nbhd_pct(elections_df, "2021", "general", r"\bbrown\b", eds_map)

vote = (
    pd.concat([b17g.rename("brown_17g"), b21p.rename("brown_21p"),
                b21g.rename("brown_21g")], axis=1)
    .dropna(subset=["brown_17g", "brown_21g"])
    .reset_index().rename(columns={"index": "nbhdname"})
)
joined = vote.merge(
    demo_df[["nbhdname", "pct_white", "pct_black", "pct_college",
             "median_income", "demo_group"]],
    on="nbhdname", how="left"
)
joined["delta"]    = joined["brown_21g"] - joined["brown_17g"]
joined["delta_pg"] = joined["brown_21g"] - joined["brown_21p"]

r_main   = joined["brown_17g"].corr(joined["brown_21g"])
r_primary = joined["brown_17g"].corr(joined["brown_21p"])
n_nbhds  = len(joined)

# ── PAGE ──────────────────────────────────────────────────────────────────────

st.title("Coalition Inversion in Buffalo Mayoral Politics")
st.markdown(
    "**Byron Brown** served as Buffalo's mayor for sixteen years (2006–2021). "
    "After losing the 2021 Democratic primary to India Walton, he won the November "
    "general election as a write-in — by assembling a coalition almost perfectly "
    "inverted from the one that had sustained him throughout his tenure. "
    "This page presents the core empirical findings and extends the analysis to the 2025 Democratic primary."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Neighborhoods analyzed", n_nbhds)
c2.metric("r  (2017G vs 2021G)", f"{r_main:.3f}", help="Negative = coalition inversion")
c3.metric("r  (2017G vs 2021 primary)", f"{r_primary:.3f}")
c4.metric("Avg shift (primary→general)", f"{joined['delta_pg'].mean():+.1f}%")

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STORYBOARD MAPS
# ══════════════════════════════════════════════════════════════════════════════

st.header("The Coalition Inversion: 2017 → 2021")
st.caption(
    "Each map shows Brown's share of total votes, neighborhood by neighborhood. "
    "Blue = strong Brown support; red = weak. The color scale is identical across all three — "
    "the inversion is visible at a glance."
)

geo_story = nbhd_geo.merge(
    joined[["nbhdname", "brown_17g", "brown_21p", "brown_21g", "demo_group"]],
    on="nbhdname", how="left"
)

col1, col2, col3 = st.columns(3)
with col1:
    st.plotly_chart(
        make_choropleth(geo_story, "brown_17g", "2017 General — Brown %"),
        width="stretch", config={"displaylogo": False},
    )
with col2:
    st.plotly_chart(
        make_choropleth(geo_story, "brown_21p", "2021 Primary — Brown %"),
        width="stretch", config={"displaylogo": False},
    )
with col3:
    st.plotly_chart(
        make_choropleth(geo_story, "brown_21g", "2021 General — Brown %"),
        width="stretch", config={"displaylogo": False},
    )

st.caption(
    "**Reading the storyboard:** In 2017, Brown ran strongest in Black community neighborhoods "
    "and weakest in affluent white areas. By 2021, this relationship reversed: Black community "
    "neighborhoods became his weakest, while working-class white neighborhoods became his strongest. "
    "The 2021 primary (center) shows the decisive break — Walton won by mobilizing the progressive "
    "and Black community vote that Brown had long taken for granted."
)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════════

st.header("Vote Shares by Coalition Group")

grp_summary = (
    joined.groupby("demo_group")
    [["brown_17g", "brown_21p", "brown_21g", "delta", "delta_pg"]]
    .agg(["mean", "count"])
)

# Flatten and format
rows = []
for grp in GROUP_COLORS:
    if grp not in joined["demo_group"].values:
        continue
    sub = joined[joined["demo_group"] == grp]
    rows.append({
        "Coalition group":   grp,
        "N":                 len(sub),
        "2017 General %":    sub["brown_17g"].mean().round(1),
        "2021 Primary %":    sub["brown_21p"].mean().round(1),
        "2021 General %":    sub["brown_21g"].mean().round(1),
        "Δ 17G→21G":         sub["delta"].mean().round(1),
        "Δ 21P→21G":         sub["delta_pg"].mean().round(1),
    })

summary_df = pd.DataFrame(rows).set_index("Coalition group")

# Style: highlight delta columns
def color_delta(val):
    try:
        v = float(val)
        if v > 5:   return "color: #2ca02c; font-weight:600"
        if v < -5:  return "color: #d62728; font-weight:600"
    except:
        pass
    return ""

st.dataframe(
    summary_df.style.map(color_delta, subset=["Δ 17G→21G", "Δ 21P→21G"]),
    width="stretch",
)
st.caption(
    "Mean Brown vote share by neighborhood demographic classification (ACS 2020 thresholds: "
    "≥40% Black → Black community; ≥50% white + income split at $50k). "
    "Δ = change in percentage points."
)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — REGRESSION
# ══════════════════════════════════════════════════════════════════════════════

st.header("Regression Results")

reg = joined.dropna(subset=["brown_17g", "brown_21g", "pct_white", "median_income"]).copy()
reg["income_k"]  = reg["median_income"] / 1000

def coef_table(model):
    rows = []
    for term in model.params.index:
        p = model.pvalues[term]
        rows.append({
            "Term": term,
            "β":    round(model.params[term], 3),
            "SE":   round(model.bse[term], 3),
            "t":    round(model.tvalues[term], 2),
            "p":    "< 0.001" if p < 0.001 else f"{p:.3f}",
            "":     ("***" if p < 0.001 else "**" if p < 0.01
                     else "*" if p < 0.05 else "·" if p < 0.1 else ""),
        })
    return pd.DataFrame(rows)

def fit(formula):
    try:
        return smf.ols(formula, data=reg).fit(), None
    except Exception as e:
        return None, str(e)

model_specs = [
    ("M1: Baseline",
     "brown_21g ~ brown_17g",
     "Does 2017 performance predict 2021? Negative β confirms the inversion."),
    ("M2: + Race & Income",
     "brown_21g ~ brown_17g + pct_white + income_k",
     "Does the inversion persist after controlling for neighborhood composition?"),
    ("M3: Interaction",
     "brown_21g ~ brown_17g + pct_white * income_k",
     "Does income operate differently in white vs Black neighborhoods?"),
    ("M4: Δ Model",
     "delta ~ pct_white * income_k",
     "What predicts the *change* (2021G − 2017G) rather than the level?"),
]

tabs = st.tabs([label for label, _, _ in model_specs])
for tab, (label, formula, interp) in zip(tabs, model_specs):
    with tab:
        m, err = fit(formula)
        if err:
            st.error(err)
        else:
            col_l, col_r = st.columns([3, 2])
            with col_l:
                st.dataframe(coef_table(m), hide_index=True, width="stretch")
                st.caption(
                    f"R² = {m.rsquared:.3f}  ·  N = {int(m.nobs)}"
                    "  ·  *** p<0.001  ** p<0.01  * p<0.05  · p<0.1"
                )
            with col_r:
                st.markdown(f"**{label}**")
                st.markdown(interp)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — 2025 PRIMARY: THE THREE-COALITION THEORY
# ══════════════════════════════════════════════════════════════════════════════

st.header("2025 Democratic Primary: The Three-Coalition Theory")
st.markdown(
    "The 2025 primary offers a forward-looking test of the coalition structure identified above. "
    "Three distinct electoral blocs emerged: **Sean Ryan** (progressive, won with 12,439 votes), "
    "**Christopher Scanlon** (South Buffalo/working-class white, 9,430), and two Black candidates — "
    "**Garnell Whitfield Jr.** (2,204) and **Rasheed Wyatt** (2,066). "
    "Ryan won — but the combined non-Ryan vote (13,700) exceeded his total, suggesting that "
    "the Black vote's split between two candidates was decisive."
)

# Compute 2025 primary neighborhood shares
p25 = elections_df[(elections_df["year"] == "2025") &
                   (elections_df["election_type"] == "primary")].copy()

cand_map = {
    "ryan":     r"\bryan\b",
    "scanlon":  r"\bscanlon\b",
    "whitfield":r"\bwhitfield\b",
    "wyatt":    r"\bwyatt\b",
}

pct_25 = {}
for key, pat in cand_map.items():
    pct_25[key] = nbhd_pct(elections_df, "2025", "primary", pat, eds_map)

# All-candidate total for denominator
all_cand_cols = [
    c for c in p25.columns
    if c not in META_COLS and not NOISE_RE.search(c)
    and pd.to_numeric(p25[c], errors="coerce").notna().any()
]
for c in all_cand_cols:
    p25[c] = pd.to_numeric(p25[c], errors="coerce").fillna(0)

p25 = p25.merge(eds_map, left_on="shapefile_key", right_on="ed_key", how="left").dropna(subset=["nbhdname"])
agg25 = p25.groupby("nbhdname")[all_cand_cols].sum()

# Combined Black candidate %
black_cands = [find_col(p25, r"\bwhitfield\b"), find_col(p25, r"\bwyatt\b")]
black_cands = [c for c in black_cands if c]
total_25    = agg25.sum(axis=1)
pct_25_combined_black = (
    agg25[black_cands].sum(axis=1) / total_25.replace(0, float("nan")) * 100
).round(2) if black_cands else pd.Series(dtype=float)

# Build geo DataFrame for 2025 maps
geo25 = nbhd_geo.copy()
for key in pct_25:
    geo25 = geo25.merge(
        pct_25[key].rename(f"pct_{key}").reset_index().rename(columns={"index": "nbhdname"}),
        on="nbhdname", how="left"
    )
geo25 = geo25.merge(
    pct_25_combined_black.rename("pct_black_combined").reset_index().rename(columns={"index": "nbhdname"}),
    on="nbhdname", how="left"
)
geo25 = geo25.merge(demo_df[["nbhdname", "demo_group"]], on="nbhdname", how="left")

# Determine leading candidate per neighborhood
def leading(row):
    candidates = {
        "Ryan":     row.get("pct_ryan", 0) or 0,
        "Scanlon":  row.get("pct_scanlon", 0) or 0,
        "Whitfield":row.get("pct_whitfield", 0) or 0,
        "Wyatt":    row.get("pct_wyatt", 0) or 0,
    }
    return max(candidates, key=candidates.get)

geo25["leader"]     = geo25.apply(leading, axis=1)
geo25["pct_nonryan"] = (
    geo25.get("pct_scanlon", 0).fillna(0)
    + geo25.get("pct_whitfield", 0).fillna(0)
    + geo25.get("pct_wyatt", 0).fillna(0)
)

# ── 2025 maps ─────────────────────────────────────────────────────────────────

st.markdown("### Maps: 2025 Democratic Primary")
col_a, col_b, col_c = st.columns(3)

with col_a:
    st.plotly_chart(
        make_choropleth(geo25, "pct_ryan", "Ryan %", colorscale="Greens",
                        zmid=50, zmin=0, zmax=100),
        width="stretch", config={"displaylogo": False},
    )
    st.caption("Ryan strongest in affluent/progressive white neighborhoods (Elmwood, Allentown, Delaware)")

with col_b:
    st.plotly_chart(
        make_choropleth(geo25, "pct_scanlon", "Scanlon %", colorscale="Blues",
                        zmid=25, zmin=0, zmax=80),
        width="stretch", config={"displaylogo": False},
    )
    st.caption("Scanlon strongest in South Buffalo/working-class white neighborhoods")

with col_c:
    st.plotly_chart(
        make_choropleth(geo25, "pct_black_combined", "Whitfield + Wyatt %",
                        colorscale="Reds", zmid=25, zmin=0, zmax=80),
        width="stretch", config={"displaylogo": False},
    )
    st.caption("Combined Black candidate vote — split between two candidates in Black community neighborhoods")

# ── Coalition math ────────────────────────────────────────────────────────────

st.markdown("### The Two-of-Three Arithmetic")

# Summary by demo group
rows_25 = []
for grp in GROUP_COLORS:
    mask = demo_df["demo_group"] == grp
    nbhds_in_grp = demo_df.loc[mask, "nbhdname"].values
    sub = geo25[geo25["nbhdname"].isin(nbhds_in_grp)]
    if sub.empty:
        continue
    # Weight by total ED count (proxy: use row count)
    rows_25.append({
        "Group":             grp,
        "N":                 len(sub),
        "Ryan %":            sub["pct_ryan"].mean().round(1),
        "Scanlon %":         sub["pct_scanlon"].mean().round(1),
        "Whitfield + Wyatt %": sub["pct_black_combined"].mean().round(1),
    })

table_25 = pd.DataFrame(rows_25).set_index("Group")
st.dataframe(table_25, width="stretch")

# City-wide coalition math callout
ryan_total     = 12_439
scanlon_total  = 9_430
whitfield      = 2_204
wyatt          = 2_066
black_combined = whitfield + wyatt
nonryan        = scanlon_total + black_combined

col_math1, col_math2 = st.columns(2)
with col_math1:
    st.markdown("**City-wide primary totals**")
    math_df = pd.DataFrame([
        {"Candidate / Coalition":    "Sean Ryan (Progressive)",
         "Votes": ryan_total,       "% of votes cast": f"{ryan_total/(ryan_total+nonryan)*100:.1f}%"},
        {"Candidate / Coalition":    "Christopher Scanlon (S. Buffalo)",
         "Votes": scanlon_total,    "% of votes cast": f"{scanlon_total/(ryan_total+nonryan)*100:.1f}%"},
        {"Candidate / Coalition":    "Garnell Whitfield Jr.",
         "Votes": whitfield,        "% of votes cast": f"{whitfield/(ryan_total+nonryan)*100:.1f}%"},
        {"Candidate / Coalition":    "Rasheed Wyatt",
         "Votes": wyatt,            "% of votes cast": f"{wyatt/(ryan_total+nonryan)*100:.1f}%"},
        {"Candidate / Coalition":    "── Combined non-Ryan ──",
         "Votes": nonryan,          "% of votes cast": f"{nonryan/(ryan_total+nonryan)*100:.1f}%"},
    ])
    st.dataframe(math_df, hide_index=True, width="stretch")

with col_math2:
    st.markdown("**The two-of-three coalition argument**")
    st.markdown(
        f"Ryan won with **{ryan_total:,}** votes. "
        f"The combined non-Ryan total was **{nonryan:,}** — "
        f"**{nonryan - ryan_total:,} more** than Ryan's total.\n\n"
        "The decisive factor: the Black community vote split between two candidates "
        f"({whitfield:,} + {wyatt:,} = {black_combined:,}). "
        "Had either Black candidate consolidated that vote, the combined "
        "working-class white + Black coalition would have prevailed.\n\n"
        "This illustrates a structural feature of Buffalo mayoral politics: "
        "**no single demographic bloc can win alone**. Winning requires at least "
        "two of the three major coalition groups — progressive white, "
        "working-class white, and Black community — to align behind a single candidate."
    )

st.divider()

# ── Connecting 2021 and 2025 ───────────────────────────────────────────────────

st.markdown("### Connecting 2021 and 2025")
st.markdown(
    "The table below places the 2025 primary candidates in the context of the "
    "coalition map established by the 2017–2021 analysis. "
    "For each candidate, the column shows their mean vote share in neighborhoods "
    "that were Brown's *strongest* (≥55% in 2017G) vs. his *weakest* (<40% in 2017G) — "
    "a direct test of whether the 2025 coalition structure echoes the 2021 inversion."
)

strong_brown = joined[joined["brown_17g"] >= 55]["nbhdname"].values
weak_brown   = joined[joined["brown_17g"] <  40]["nbhdname"].values

compare_rows = []
for key, label in [("ryan","Ryan"), ("scanlon","Scanlon"),
                   ("black_combined","Whitfield + Wyatt")]:
    col = f"pct_{key}"
    if col not in geo25.columns:
        continue
    compare_rows.append({
        "Candidate":                     label,
        "Strong-Brown nbhds (2017 ≥55%)":
            geo25[geo25["nbhdname"].isin(strong_brown)][col].mean().round(1),
        "Weak-Brown nbhds (2017 <40%)":
            geo25[geo25["nbhdname"].isin(weak_brown)][col].mean().round(1),
    })

st.dataframe(pd.DataFrame(compare_rows).set_index("Candidate"), width="stretch")
st.caption(
    "Strong-Brown neighborhoods in 2017 were predominantly Black community areas; "
    "weak-Brown neighborhoods were predominantly affluent white. "
    "Ryan's support pattern (strongest in weak-Brown areas) replicates Walton's 2021 primary coalition. "
    "Scanlon's pattern mirrors Brown's 2021 general coalition. "
    "Whitfield + Wyatt track the Black community bloc that anchored Brown's 2017 coalition."
)
