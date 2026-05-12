"""
Buffalo Elections — Compare Elections
Two choropleth maps + scatter plot. Works across mayoral and council races.
When a council election is selected the maps zoom to that district.
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

def normalize_name(name: str) -> str:
    """Normalize candidate name: fix OCR artifacts and strip middle initials."""
    name = re.sub(r"\s+\.", ".", str(name).strip())
    name = re.sub(r"\s+", " ", name).strip()
    parts = name.split()
    if len(parts) >= 3:
        parts = [
            p for i, p in enumerate(parts)
            if not (0 < i < len(parts) - 1 and re.match(r"^[A-Z]\.?$", p))
        ]
        name = " ".join(parts)
    return name


BUFFALO_CENTER = {"lat": 42.886, "lon": -78.878}
META_COLS = {"year", "election_type", "district", "ward", "ed_num", "ed_label", "shapefile_key"}
NOISE_RE  = re.compile(r"\b(blank|void|scatter|total)", re.IGNORECASE)
SEL_COLOR  = "#e41a1c"
GRID_COLOR = "rgba(0,0,0,0.07)"

WARD_CODES = {
    "delaware":   "DEL", "ellicott":   "ELL", "fillmore":  "FIL",
    "lovejoy":    "LOV", "masten":     "MAS", "niagara":   "NIA",
    "north":      "NOR", "south":      "SOU", "university": "UNI",
}


# ── Data loading ───────────────────────────────────────────────────────────────

@st.cache_data
def load_base_eds() -> gpd.GeoDataFrame:
    return gpd.read_file(GEO_DIR / "buffalo_eds.geojson")

@st.cache_data
def load_mayoral() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "mayoral_all.csv", dtype={"year": str})

@st.cache_data
def load_council() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "council_all.csv", dtype={"year": str})
    return df

@st.cache_data
def build_nbhd_geo(_eds: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return _eds.dissolve(by="nbhdname").reset_index()[["nbhdname", "nbhdnum", "geometry"]]

@st.cache_data
def district_eds(_base_eds: gpd.GeoDataFrame, ward_code: str) -> gpd.GeoDataFrame:
    return _base_eds[
        _base_eds["ed_key"].str.contains(f" {ward_code} ", regex=False)
    ].copy()

@st.cache_data
def district_nbhd(_dist_eds: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return _dist_eds.dissolve(by="nbhdname").reset_index()[["nbhdname", "geometry"]]


# ── Election registry ──────────────────────────────────────────────────────────

@st.cache_data
def build_registry(_mayoral: pd.DataFrame, _council: pd.DataFrame) -> dict:
    """Label → metadata dict for all available elections."""
    reg = {}
    for yr, etype in _mayoral[["year", "election_type"]].drop_duplicates().itertuples(index=False):
        label = f"{yr} {etype.title()} — Mayor"
        reg[label] = {"race": "mayor", "year": yr, "etype": etype, "district": None}
    for yr, etype, dist in (
        _council[["year", "election_type", "district"]]
        .drop_duplicates()
        .itertuples(index=False)
    ):
        label = f"{yr} {etype.title()} — {dist.title()} Council"
        reg[label] = {"race": "council", "year": yr, "etype": etype, "district": dist}
    return reg


def get_elec_data(meta: dict) -> pd.DataFrame:
    if meta["race"] == "mayor":
        return mayoral_df[
            (mayoral_df["year"]           == meta["year"]) &
            (mayoral_df["election_type"]  == meta["etype"])
        ].copy()
    else:
        return council_df[
            (council_df["year"]           == meta["year"]) &
            (council_df["election_type"]  == meta["etype"]) &
            (council_df["district"]       == meta["district"])
        ].copy()


def get_geo_scope(
    x_meta: dict, y_meta: dict, view: str
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, str | None]:
    """
    Return (eds_ref, nbhd_ref, scope_district).
    scope_district is None for city-wide, or the district name for council-scoped views.
    When both elections are council from different districts, returns (None, None, 'conflict').
    """
    x_council = x_meta["race"] == "council"
    y_council = y_meta["race"] == "council"

    if x_council and y_council and x_meta["district"] != y_meta["district"]:
        return None, None, "conflict"

    if x_council or y_council:
        dist = x_meta["district"] if x_council else y_meta["district"]
        wc   = WARD_CODES[dist]
        eds  = district_eds(base_eds, wc)
        nbhd = district_nbhd(eds)
        return eds, nbhd, dist

    return base_eds, nbhd_geo, None


def map_params(gdf: gpd.GeoDataFrame) -> tuple[dict, float]:
    if gdf is None or len(gdf) == 0:
        return BUFFALO_CENTER, 10.8
    b    = gdf.total_bounds
    center = {"lat": (b[1] + b[3]) / 2, "lon": (b[0] + b[2]) / 2}
    span = max(b[3] - b[1], (b[2] - b[0]) * 0.7)
    zoom = (13.5 if span < 0.02 else
            13.0 if span < 0.04 else
            12.5 if span < 0.07 else
            12.0 if span < 0.12 else 10.8)
    return center, zoom


# ── Candidates ─────────────────────────────────────────────────────────────────

def get_candidates(df: pd.DataFrame) -> list[str]:
    return [
        c for c in df.columns
        if c not in META_COLS
        and not NOISE_RE.search(c)
        and df[c].notna().any()
        and pd.to_numeric(df[c], errors="coerce").gt(0).any()
    ]

def sorted_candidates(elections: pd.DataFrame) -> list[str]:
    cands  = get_candidates(elections)
    totals = {c: pd.to_numeric(elections[c], errors="coerce").fillna(0).sum() for c in cands}
    return sorted(cands, key=lambda c: totals[c], reverse=True)


# ── Aggregation ────────────────────────────────────────────────────────────────

def _nbhd_agg(
    elections: pd.DataFrame, candidate: str, metric: str,
    eds_ref: gpd.GeoDataFrame,
) -> pd.DataFrame:
    cands    = get_candidates(elections)
    sel_cols = ["shapefile_key"] + [c for c in cands if c in elections.columns]
    ed_nbhd  = eds_ref[["ed_key", "nbhdname"]].merge(
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


def _ed_agg(
    elections: pd.DataFrame, candidate: str, metric: str,
    eds_ref: gpd.GeoDataFrame,
) -> pd.DataFrame:
    cands    = get_candidates(elections)
    sel_cols = ["shapefile_key"] + [c for c in cands if c in elections.columns]
    ed       = eds_ref[["ed_key"]].merge(
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


# ── Boundary / highlight traces ────────────────────────────────────────────────

def boundary_trace(gdf: gpd.GeoDataFrame, color: str = "#777777", width: float = 0.5) -> go.Scattermap:
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
    center: dict,
    zoom: float,
    height: int = 380,
) -> go.Figure:
    geo_json = json.loads(geo.to_json())
    hover_data = {color_col: True, other_col: True, id_col: False}
    if "nbhdnum" in geo.columns:
        hover_data["nbhdnum"] = False

    fig = px.choropleth_map(
        geo,
        geojson=geo_json,
        locations=id_col,
        featureidkey=f"properties.{id_col}",
        color=color_col,
        color_continuous_scale="Blues",
        range_color=color_range,
        map_style="carto-positron",
        zoom=zoom,
        center=center,
        opacity=0.75,
        hover_name=id_col,
        hover_data=hover_data,
        labels={color_col: label, other_col: other_label},
        title=title,
        height=height,
    )
    fig.update_layout(
        margin={"r": 0, "t": 36, "l": 0, "b": 0},
        coloraxis_colorbar=dict(
            thickness=12, len=0.6,
            title=dict(text=unit or "votes", side="right"),
            ticksuffix=unit, tickfont=dict(size=11),
        ),
    )
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

base_eds   = load_base_eds()
mayoral_df = load_mayoral()
council_df = load_council()
nbhd_geo   = build_nbhd_geo(base_eds)

registry      = build_registry(mayoral_df, council_df)
all_labels    = sorted(
    registry.keys(),
    key=lambda l: (-int(l[:4]), l),
)

# Defaults: most recent two mayoral elections
mayor_labels = [l for l in all_labels if "Mayor" in l]
default_x = all_labels.index(mayor_labels[1]) if len(mayor_labels) > 1 else max(0, len(all_labels) - 2)
default_y = all_labels.index(mayor_labels[0]) if mayor_labels else len(all_labels) - 1


# ── Session state ──────────────────────────────────────────────────────────────

for k, v in [("cmp_selected", None), ("cmp_last_idx", -1)]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    view = st.radio("Geography", ["Neighborhood", "Election District"])
    st.divider()

    st.markdown("**Map 1** · left on desktop, top on mobile")
    x_sel  = st.selectbox("Election", all_labels, index=default_x, key="x_election")
    x_meta = registry[x_sel]
    x_elec = get_elec_data(x_meta)
    x_cand = st.selectbox("Candidate", sorted_candidates(x_elec), key="x_cand",
                           format_func=normalize_name)
    x_met  = st.radio("Metric", ["Vote %", "Raw votes"], key="x_metric", horizontal=True)

    st.divider()

    st.markdown("**Map 2** · right on desktop, bottom on mobile")
    y_sel  = st.selectbox("Election", all_labels, index=default_y, key="y_election")
    y_meta = registry[y_sel]
    y_elec = get_elec_data(y_meta)
    y_cand = st.selectbox("Candidate", sorted_candidates(y_elec), key="y_cand",
                           format_func=normalize_name)
    y_met  = st.radio("Metric", ["Vote %", "Raw votes"], key="y_metric", horizontal=True)

    st.divider()
    show_trend = st.checkbox("Scatter trend line", value=True)
    st.divider()
    st.caption("Data: Erie County Board of Elections · NYS GIS")


# ── Geographic scope ───────────────────────────────────────────────────────────

eds_ref, nbhd_ref, scope_district = get_geo_scope(x_meta, y_meta, view)

if scope_district == "conflict":
    st.title("Compare Elections")
    st.warning(
        "The two selected elections are from different council districts "
        f"({x_meta['district'].title()} and {y_meta['district'].title()}). "
        "Their election districts don't overlap, so there's no data to compare. "
        "Choose elections from the same district, or mix a council election with a mayoral one."
    )
    st.stop()

map_center, map_zoom = map_params(
    eds_ref if view == "Election District" else nbhd_ref
)


# ── Reset on settings change ───────────────────────────────────────────────────

cmp_key = f"{x_sel}|{x_cand}|{x_met}|{y_sel}|{y_cand}|{y_met}|{view}"
if st.session_state.get("_cmp_key") != cmp_key:
    st.session_state.cmp_selected = None
    st.session_state.cmp_last_idx = -1
    st.session_state["_cmp_key"]  = cmp_key


# ── Build joined dataset ───────────────────────────────────────────────────────

if view == "Neighborhood":
    x_raw  = _nbhd_agg(x_elec, x_cand, x_met, eds_ref)
    y_raw  = _nbhd_agg(y_elec, y_cand, y_met, eds_ref)
    id_col   = "nbhdname"
    geo_base = nbhd_ref
else:
    x_raw  = _ed_agg(x_elec, x_cand, x_met, eds_ref)
    y_raw  = _ed_agg(y_elec, y_cand, y_met, eds_ref)
    id_col   = "ed_key"
    geo_base = eds_ref[["ed_key", "geometry"]]

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

def fmt_label(cand, meta):
    yr   = meta["year"]
    etype = meta["etype"].replace("primary", "Primary").replace("general", "General")
    race  = "Mayor" if meta["race"] == "mayor" else f"{meta['district'].title()} Council"
    return f"{normalize_name(cand)}  ({yr} {etype}, {race})"

x_label = fmt_label(x_cand, x_meta)
y_label = fmt_label(y_cand, y_meta)
corr    = joined["x_val"].corr(joined["y_val"])


# ── Page header ────────────────────────────────────────────────────────────────

st.title("Compare Elections")
scope_note = f" · {scope_district.title()} District" if scope_district else ""
st.caption(
    f"**X:** {x_label}{' (%)' if x_met == 'Vote %' else ''}   ·   "
    f"**Y:** {y_label}{' (%)' if y_met == 'Vote %' else ''}   ·   "
    f"{view}{scope_note} · n={len(joined)}"
)

c1, c2, c3 = st.columns(3)
c1.metric("Pearson r", f"{corr:.3f}", help="Correlation between X and Y across areas")
c2.metric(f"X avg · {last_name(normalize_name(x_cand))}",
          f"{joined['x_val'].mean():.1f}{x_unit}" if x_met == "Vote %" else f"{int(joined['x_val'].sum()):,}")
c3.metric(f"Y avg · {last_name(normalize_name(y_cand))}",
          f"{joined['y_val'].mean():.1f}{y_unit}" if y_met == "Vote %" else f"{int(joined['y_val'].sum()):,}")

st.divider()


# ── Two maps ───────────────────────────────────────────────────────────────────

selected_area  = st.session_state.cmp_selected
x_map_col, y_map_col = st.columns(2)

color_range_x = [0, 100] if x_met == "Vote %" else None
color_range_y = [0, 100] if y_met == "Vote %" else None

with x_map_col:
    fig_x = make_choropleth(
        geo_cmp, id_col,
        color_col="x_val", color_range=color_range_x,
        title=f"X: {normalize_name(x_cand)}",
        label=f"X{x_unit}", unit=x_unit,
        other_col="y_val", other_label=f"Y{y_unit}",
        center=map_center, zoom=map_zoom,
    )
    ht = highlight_trace(geo_cmp, id_col, selected_area) if selected_area else None
    if ht:
        fig_x.add_trace(ht)
    st.plotly_chart(fig_x, use_container_width=True, config={"displaylogo": False})

with y_map_col:
    fig_y = make_choropleth(
        geo_cmp, id_col,
        color_col="y_val", color_range=color_range_y,
        title=f"Y: {normalize_name(y_cand)}",
        label=f"Y{y_unit}", unit=y_unit,
        other_col="x_val", other_label=f"X{x_unit}",
        center=map_center, zoom=map_zoom,
    )
    ht = highlight_trace(geo_cmp, id_col, selected_area) if selected_area else None
    if ht:
        fig_y.add_trace(ht)
    st.plotly_chart(fig_y, use_container_width=True, config={"displaylogo": False})


# ── Scatter ────────────────────────────────────────────────────────────────────

scatter_col, info_col = st.columns([4, 1])

with scatter_col:
    fig_sc = px.scatter(
        joined,
        x="x_val", y="y_val",
        hover_name=id_col,
        hover_data={"x_val": False, "y_val": False, "x_total": False, "y_total": False, id_col: False},
        labels={
            "x_val": f"X: {normalize_name(x_cand)}{' (%)' if x_met == 'Vote %' else ''}",
            "y_val": f"Y: {normalize_name(y_cand)}{' (%)' if y_met == 'Vote %' else ''}",
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

    if x_met == "Vote %" and y_met == "Vote %":
        lo = min(joined["x_val"].min(), joined["y_val"].min()) * 0.9
        hi = max(joined["x_val"].max(), joined["y_val"].max()) * 1.05
        fig_sc.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi,
                         line=dict(color="#cccccc", dash="dot", width=1), layer="below")
        fig_sc.add_annotation(x=hi, y=hi, text="y = x", showarrow=False,
                               font=dict(color="#aaaaaa", size=11), xanchor="left")

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
        dragmode="select",
    )

    sc_event = st.plotly_chart(
        fig_sc, on_select="rerun", key=f"sc_{cmp_key}",
        use_container_width=True, config={"displaylogo": False},
    )

    if sc_event and hasattr(sc_event, "selection") and sc_event.selection and sc_event.selection.points:
        for pt in sc_event.selection.points:
            if pt.get("curveNumber", 0) != 0:
                continue
            idx = pt.get("pointIndex", -1)
            if idx != st.session_state.cmp_last_idx and 0 <= idx < len(joined):
                st.session_state.cmp_last_idx = idx
                st.session_state.cmp_selected = str(joined.iloc[idx][id_col])
                st.rerun()
            break

    st.caption("Click a point to highlight the area on both maps above. "
               "Drag to box-select multiple points.")

with info_col:
    st.markdown("&nbsp;")
    if selected_area and selected_area in joined[id_col].values:
        sel_row = joined[joined[id_col] == selected_area].iloc[0]
        st.markdown(f"**{sel_row[id_col]}**")
        st.metric(f"X · {last_name(normalize_name(x_cand))}", f"{sel_row['x_val']:.1f}{x_unit}")
        st.metric(
            f"Y · {last_name(normalize_name(y_cand))}",
            f"{sel_row['y_val']:.1f}{y_unit}",
            delta=(
                f"{sel_row['y_val'] - sel_row['x_val']:+.1f}"
                if x_unit == y_unit else None
            ),
        )
    else:
        st.caption("← click a\nscatter point")
