"""
Buffalo Mayoral Elections — Compare Elections
Two choropleth maps (one per axis) + scatter plot linking them.
Clicking a scatter point highlights the area on both maps.
"""

import json
import re
import streamlit as st
import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "jr.", "sr.", "esq", "esq."}

def last_name(full: str) -> str:
    parts = full.split()
    if len(parts) > 1 and parts[-1].lower().rstrip(".") in _SUFFIXES:
        return parts[-2]
    return parts[-1] if parts else full


BUFFALO_CENTER = {"lat": 42.886, "lon": -78.878}
META_COLS = {"year", "election_type", "ward", "ed_num", "ed_label", "shapefile_key"}
NOISE_RE  = re.compile(r"\b(blank|void|scatter|total)", re.IGNORECASE)
SEL_COLOR  = "#e41a1c"
GRID_COLOR = "rgba(0,0,0,0.07)"
AXIS_COLOR = "rgba(0,0,0,0.15)"


# ── Data loading ───────────────────────────────────────────────────────────────

@st.cache_data
def load_base_eds() -> gpd.GeoDataFrame:
    return gpd.read_file(GEO_DIR / "buffalo_eds.geojson")

@st.cache_data
def load_elections() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "mayoral_all.csv", dtype={"year": str})

@st.cache_data
def build_nbhd_geo(_eds: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return _eds.dissolve(by="nbhdname").reset_index()[["nbhdname", "nbhdnum", "geometry"]]


def get_candidates(df: pd.DataFrame) -> list[str]:
    return [
        c for c in df.columns
        if c not in META_COLS
        and not NOISE_RE.search(c)
        and df[c].notna().any()
        and pd.to_numeric(df[c], errors="coerce").gt(0).any()
    ]


def sorted_candidates(elections: pd.DataFrame) -> list[str]:
    cands = get_candidates(elections)
    totals = {c: pd.to_numeric(elections[c], errors="coerce").fillna(0).sum() for c in cands}
    return sorted(cands, key=lambda c: totals[c], reverse=True)


# ── Aggregation ────────────────────────────────────────────────────────────────

def _nbhd_agg(elections: pd.DataFrame, candidate: str, metric: str) -> pd.DataFrame:
    cands    = get_candidates(elections)
    sel_cols = ["shapefile_key"] + [c for c in cands if c in elections.columns]
    ed_nbhd  = base_eds[["ed_key", "nbhdname"]].merge(
        elections[sel_cols], left_on="ed_key", right_on="shapefile_key", how="left"
    )
    valid = [c for c in cands if c in ed_nbhd.columns]
    for c in valid:
        ed_nbhd[c] = pd.to_numeric(ed_nbhd[c], errors="coerce").fillna(0)
    agg           = ed_nbhd.groupby("nbhdname")[valid].sum().reset_index()
    agg["_total"] = agg[valid].sum(axis=1)
    raw           = agg[candidate] if candidate in agg.columns else pd.Series(0.0, index=agg.index)
    if metric == "Vote %":
        agg["val"] = (raw / agg["_total"].replace(0, float("nan")) * 100).round(2)
    else:
        agg["val"] = raw.round(0)
    return agg[["nbhdname", "val", "_total"]]


def _ed_agg(elections: pd.DataFrame, candidate: str, metric: str) -> pd.DataFrame:
    cands    = get_candidates(elections)
    sel_cols = ["shapefile_key"] + [c for c in cands if c in elections.columns]
    ed       = base_eds[["ed_key"]].merge(
        elections[sel_cols], left_on="ed_key", right_on="shapefile_key", how="left"
    )
    valid = [c for c in cands if c in ed.columns]
    for c in valid:
        ed[c] = pd.to_numeric(ed[c], errors="coerce").fillna(0)
    ed["_total"] = ed[valid].sum(axis=1)
    raw          = ed[candidate] if candidate in ed.columns else pd.Series(0.0, index=ed.index)
    if metric == "Vote %":
        ed["val"] = (raw / ed["_total"].replace(0, float("nan")) * 100).round(2)
    else:
        ed["val"] = raw.round(0)
    return ed[["ed_key", "val", "_total"]]


# ── Boundary-outline helper ────────────────────────────────────────────────────

def boundary_trace(gdf: gpd.GeoDataFrame, color: str = "#777777", width: float = 0.5) -> go.Scattermap:
    """Scattermap line trace outlining every polygon in a GeoDataFrame."""
    lats, lons = [], []
    for geom in gdf.geometry:
        if geom is None:
            continue
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        for poly in polys:
            for ring in [poly.exterior] + list(poly.interiors):
                xs, ys = ring.xy
                lons += list(xs) + [None]
                lats += list(ys) + [None]
    return go.Scattermap(
        lat=lats, lon=lons, mode="lines",
        line=dict(color=color, width=width),
        hoverinfo="skip", showlegend=False,
    )


def highlight_trace(gdf: gpd.GeoDataFrame, id_col: str, name: str) -> go.Scattermap | None:
    """Red border trace for a single selected area."""
    mask = gdf[id_col] == name
    if not mask.any():
        return None
    return boundary_trace(gdf[mask], color=SEL_COLOR, width=3)


# ── Choropleth factory ─────────────────────────────────────────────────────────

def make_choropleth(
    geo: gpd.GeoDataFrame,
    id_col: str,
    color_col: str,
    color_range: list | None,
    title: str,
    label: str,
    unit: str,
    other_col: str,
    other_label: str,
    height: int = 380,
) -> go.Figure:
    geo_json = json.loads(geo.to_json())
    fig = px.choropleth_map(
        geo,
        geojson=geo_json,
        locations=id_col,
        featureidkey=f"properties.{id_col}",
        color=color_col,
        color_continuous_scale="Blues",
        range_color=color_range,
        map_style="carto-positron",
        zoom=10.8,
        center=BUFFALO_CENTER,
        opacity=0.75,
        hover_name=id_col,
        hover_data={color_col: True, other_col: True, id_col: False, "nbhdnum": False},
        labels={color_col: label, other_col: other_label},
        title=title,
        height=height,
    )
    fig.update_layout(
        margin={"r": 0, "t": 36, "l": 0, "b": 0},
        coloraxis_colorbar=dict(
            thickness=12,
            len=0.6,
            title=dict(text=unit or "votes", side="right"),
            ticksuffix=unit,
            tickfont=dict(size=11),
        ),
    )
    # Fix hover: replace "colname=value" default with clean template
    fig.update_traces(
        hovertemplate=(
            "<b>%{location}</b><br>"
            f"{label}: %{{z:.1f}}{unit}<br>"
            f"{other_label}: %{{customdata[0]:.1f}}{unit}"
            "<extra></extra>"
        ),
        customdata=geo[[other_col]].values,
    )
    fig.add_trace(boundary_trace(geo))
    return fig


# ── Load data ──────────────────────────────────────────────────────────────────

base_eds     = load_base_eds()
elections_df = load_elections()
nbhd_geo     = build_nbhd_geo(base_eds)

available = (
    elections_df[["year", "election_type"]]
    .drop_duplicates()
    .sort_values(["year", "election_type"])
)
election_labels = [f"{r.year} {r.election_type.title()}" for r in available.itertuples()]
default_x = max(0, len(election_labels) - 2)
default_y = len(election_labels) - 1


# ── Session state ──────────────────────────────────────────────────────────────

for k, v in [("cmp_selected", None), ("cmp_last_idx", -1)]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Compare\nElections")
    st.divider()

    view = st.radio("Geography", ["Neighborhood", "Election District"])
    st.divider()

    st.markdown("**X axis (left map)**")
    x_sel  = st.selectbox("Election##x", election_labels, index=default_x, key="x_election")
    x_year, x_type = x_sel.split(" ", 1);  x_type = x_type.lower()
    x_elec = elections_df[(elections_df["year"] == x_year) & (elections_df["election_type"] == x_type)].copy()
    x_cand = st.selectbox("Candidate##x", sorted_candidates(x_elec), key="x_cand")
    x_met  = st.radio("Metric##x", ["Vote %", "Raw votes"], key="x_metric", horizontal=True)

    st.divider()

    st.markdown("**Y axis (right map)**")
    y_sel  = st.selectbox("Election##y", election_labels, index=default_y, key="y_election")
    y_year, y_type = y_sel.split(" ", 1);  y_type = y_type.lower()
    y_elec = elections_df[(elections_df["year"] == y_year) & (elections_df["election_type"] == y_type)].copy()
    y_cand = st.selectbox("Candidate##y", sorted_candidates(y_elec), key="y_cand")
    y_met  = st.radio("Metric##y", ["Vote %", "Raw votes"], key="y_metric", horizontal=True)

    st.divider()
    show_trend = st.checkbox("Scatter trend line", value=True)
    st.divider()
    st.caption("Data: Erie County Board of Elections · NYS GIS")


# ── Reset on settings change ───────────────────────────────────────────────────

cmp_key = f"{x_sel}|{x_cand}|{x_met}|{y_sel}|{y_cand}|{y_met}|{view}"
if st.session_state.get("_cmp_key") != cmp_key:
    st.session_state.cmp_selected = None
    st.session_state.cmp_last_idx = -1
    st.session_state["_cmp_key"]  = cmp_key


# ── Build joined dataset ───────────────────────────────────────────────────────

if view == "Neighborhood":
    x_raw = _nbhd_agg(x_elec, x_cand, x_met)
    y_raw = _nbhd_agg(y_elec, y_cand, y_met)
    id_col   = "nbhdname"
    geo_base = nbhd_geo
else:
    x_raw = _ed_agg(x_elec, x_cand, x_met)
    y_raw = _ed_agg(y_elec, y_cand, y_met)
    id_col   = "ed_key"
    geo_base = base_eds[["ed_key", "geometry"]]

joined = (
    x_raw[[id_col, "val", "_total"]].rename(columns={"val": "x_val", "_total": "x_total"})
    .merge(y_raw[[id_col, "val", "_total"]].rename(columns={"val": "y_val", "_total": "y_total"}),
           on=id_col, how="inner")
    .dropna(subset=["x_val", "y_val"])
    .pipe(lambda df: df[(df["x_total"] > 0) & (df["y_total"] > 0)])
    .reset_index(drop=True)
)

if joined.empty:
    st.warning("No overlapping data found for these two selections.")
    st.stop()

geo_cmp = geo_base.merge(joined, on=id_col, how="right")

x_unit  = "%" if x_met == "Vote %" else ""
y_unit  = "%" if y_met == "Vote %" else ""

def fmt_label(cand, year, etype):
    return f"{cand}  ({year} {etype.replace('primary','Primary').replace('general','General')})"

x_label = fmt_label(x_cand, x_year, x_type)
y_label = fmt_label(y_cand, y_year, y_type)
corr    = joined["x_val"].corr(joined["y_val"])


# ── Page header ────────────────────────────────────────────────────────────────

st.title("Compare Elections")
st.caption(
    f"**X:** {x_label}{' (%)' if x_met == 'Vote %' else ''}   ·   "
    f"**Y:** {y_label}{' (%)' if y_met == 'Vote %' else ''}   ·   "
    f"{view} · n={len(joined)}"
)

c1, c2, c3 = st.columns(3)
c1.metric("Pearson r", f"{corr:.3f}", help="Correlation between X and Y across areas")
c2.metric(f"X avg · {last_name(x_cand)}",
          f"{joined['x_val'].mean():.1f}{x_unit}" if x_met == "Vote %" else f"{int(joined['x_val'].sum()):,}")
c3.metric(f"Y avg · {last_name(y_cand)}",
          f"{joined['y_val'].mean():.1f}{y_unit}" if y_met == "Vote %" else f"{int(joined['y_val'].sum()):,}")

st.divider()


# ── Two maps (top) ─────────────────────────────────────────────────────────────

selected_area = st.session_state.cmp_selected
x_map_col, y_map_col = st.columns(2)

color_range_x = [0, 100] if x_met == "Vote %" else None
color_range_y = [0, 100] if y_met == "Vote %" else None

with x_map_col:
    fig_x = make_choropleth(
        geo_cmp, id_col,
        color_col="x_val", color_range=color_range_x,
        title=f"X: {x_label}",
        label=f"X{x_unit}",
        unit=x_unit,
        other_col="y_val", other_label=f"Y{y_unit}",
    )
    ht = highlight_trace(geo_cmp, id_col, selected_area) if selected_area else None
    if ht:
        fig_x.add_trace(ht)
    st.plotly_chart(fig_x, width="stretch", config={"displaylogo": False})

with y_map_col:
    fig_y = make_choropleth(
        geo_cmp, id_col,
        color_col="y_val", color_range=color_range_y,
        title=f"Y: {y_label}",
        label=f"Y{y_unit}",
        unit=y_unit,
        other_col="x_val", other_label=f"X{x_unit}",
    )
    ht = highlight_trace(geo_cmp, id_col, selected_area) if selected_area else None
    if ht:
        fig_y.add_trace(ht)
    st.plotly_chart(fig_y, width="stretch", config={"displaylogo": False})


# ── Scatter (bottom) ───────────────────────────────────────────────────────────

scatter_col, info_col = st.columns([4, 1])

with scatter_col:
    fig_sc = px.scatter(
        joined,
        x="x_val", y="y_val",
        hover_name=id_col,
        hover_data={"x_val": False, "y_val": False, "x_total": False, "y_total": False, id_col: False},
        labels={
            "x_val": f"X: {x_label}{' (%)' if x_met == 'Vote %' else ''}",
            "y_val": f"Y: {y_label}{' (%)' if y_met == 'Vote %' else ''}",
        },
        trendline="ols" if show_trend else None,
        trendline_color_override="#ff7f0e",
        color_discrete_sequence=["#3182bd"],
        height=420,
        title=f"Scatter · r = {corr:.3f}",
    )
    fig_sc.update_traces(
        selector=dict(mode="markers"),
        marker=dict(size=9, opacity=0.7),
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            f"X: %{{x:.1f}}{x_unit}<br>"
            f"Y: %{{y:.1f}}{y_unit}"
            "<extra></extra>"
        ),
    )

    # y=x reference line when both axes are percentages
    if x_met == "Vote %" and y_met == "Vote %":
        lo = min(joined["x_val"].min(), joined["y_val"].min()) * 0.9
        hi = max(joined["x_val"].max(), joined["y_val"].max()) * 1.05
        fig_sc.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi,
                         line=dict(color="#cccccc", dash="dot", width=1), layer="below")
        fig_sc.add_annotation(x=hi, y=hi, text="y = x", showarrow=False,
                               font=dict(color="#aaaaaa", size=11), xanchor="left")

    # Red ring on selected point
    if selected_area and selected_area in joined[id_col].values:
        sel_pt = joined[joined[id_col] == selected_area].iloc[0]
        fig_sc.add_trace(go.Scatter(
            x=[sel_pt["x_val"]], y=[sel_pt["y_val"]],
            mode="markers",
            marker=dict(color=SEL_COLOR, size=16, symbol="circle-open",
                        line=dict(width=3, color=SEL_COLOR)),
            hoverinfo="skip", showlegend=False,
        ))

    fig_sc.update_layout(
        margin={"r": 10, "t": 40, "l": 10, "b": 40},
        xaxis=dict(ticksuffix=x_unit, gridcolor=GRID_COLOR, zeroline=False),
        yaxis=dict(ticksuffix=y_unit, gridcolor=GRID_COLOR, zeroline=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
        clickmode="event+select",
        dragmode="select",   # enables single-click point selection
    )

    sc_event = st.plotly_chart(fig_sc, on_select="rerun", key=f"sc_{cmp_key}", width="stretch", config={"displaylogo": False})

    # Handle click — only process the scatter trace (curveNumber 0), not the trendline
    if sc_event and hasattr(sc_event, "selection") and sc_event.selection and sc_event.selection.points:
        for pt in sc_event.selection.points:
            if pt.get("curveNumber", 0) != 0:
                continue
            idx = pt.get("pointIndex", -1)
            if idx != st.session_state.cmp_last_idx and 0 <= idx < len(joined):
                st.session_state.cmp_last_idx = idx
                st.session_state.cmp_selected = str(joined.iloc[idx][id_col])
                st.rerun()   # maps are above; need another pass to show the highlight
            break

    st.caption("Click a point to highlight the area on both maps above. "
               "Drag to box-select multiple points.")


with info_col:
    st.markdown("&nbsp;")   # vertical padding
    if selected_area and selected_area in joined[id_col].values:
        sel_row = joined[joined[id_col] == selected_area].iloc[0]
        st.markdown(f"**{sel_row[id_col]}**")
        st.metric(f"X · {last_name(x_cand)}", f"{sel_row['x_val']:.1f}{x_unit}")
        st.metric(
            f"Y · {last_name(y_cand)}",
            f"{sel_row['y_val']:.1f}{y_unit}",
            delta=(
                f"{sel_row['y_val'] - sel_row['x_val']:+.1f}"
                if x_unit == y_unit else None
            ),
        )
    else:
        st.caption("← click a\nscatter point")
