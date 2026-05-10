"""
Buffalo Mayoral Elections — Home / Election Explorer
"""

import re
import json
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
    div[data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
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
AREA_COLORS = ["#1f77b4", "#ff7f0e"]
AVG_COLOR   = "#888888"
GRID_COLOR  = "rgba(0,0,0,0.07)"
AXIS_COLOR  = "rgba(0,0,0,0.15)"


# ── Data loading ──────────────────────────────────────────────────────────────

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


def city_pcts(sel: pd.DataFrame, cands: list[str]) -> dict[str, float]:
    totals = {c: pd.to_numeric(sel[c], errors="coerce").fillna(0).sum() for c in cands}
    grand  = sum(totals.values())
    return {c: round(v / grand * 100, 1) if grand else 0.0 for c, v in totals.items()}


def area_pcts(geo_row: pd.Series, cands: list[str]) -> dict[str, float]:
    vals  = {c: float(geo_row.get(c, 0) or 0) for c in cands}
    total = sum(vals.values())
    return {c: round(v / total * 100, 1) if total else 0.0 for c, v in vals.items()}


# ── Session state defaults ────────────────────────────────────────────────────

for key, default in [
    ("sel_areas", []),
    ("sel_election_key", ""),
    ("last_click_idx", -1),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── Load data ─────────────────────────────────────────────────────────────────

base_eds     = load_base_eds()
elections_df = load_elections()
nbhd_geo     = build_nbhd_geo(base_eds)

available = (
    elections_df[["year", "election_type"]]
    .drop_duplicates()
    .sort_values(["year", "election_type"])
)
election_labels = [
    f"{r.year} {r.election_type.title()}"
    for r in available.itertuples()
]


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Buffalo Mayoral\nElections")
    st.divider()

    sel_label = st.selectbox("Election", election_labels, index=len(election_labels) - 1)
    sel_year, sel_type = sel_label.split(" ", 1)
    sel_type = sel_type.lower()

    view = st.radio("Geography", ["Neighborhood", "Election District"])
    st.divider()

    election_key = f"{sel_label}_{view}"
    if st.session_state.sel_election_key != election_key:
        st.session_state.sel_areas = []
        st.session_state.last_click_idx = -1
        st.session_state.sel_election_key = election_key

    _candidate_placeholder = st.empty()
    _area_placeholder = st.empty()

    st.divider()
    st.caption("Data: Erie County Board of Elections · NYS GIS")


# ── Filter election data ──────────────────────────────────────────────────────

sel_elections = elections_df[
    (elections_df["year"] == sel_year) &
    (elections_df["election_type"] == sel_type)
].copy()

candidates = get_candidates(sel_elections)
if not candidates:
    st.warning("No candidate data for this selection.")
    st.stop()

city_avg = city_pcts(sel_elections, candidates)
total_votes = sum(
    pd.to_numeric(sel_elections[c], errors="coerce").fillna(0).sum()
    for c in candidates
)

candidates = sorted(candidates, key=lambda c: city_avg.get(c, 0), reverse=True)

with _candidate_placeholder:
    sel_candidate = st.selectbox("Candidate (map color)", candidates)


# ── Build geo layer ───────────────────────────────────────────────────────────

if view == "Election District":
    geo = base_eds.merge(
        sel_elections[["shapefile_key"] + candidates],
        left_on="ed_key", right_on="shapefile_key", how="left",
    )
    id_col   = "ed_key"
    name_col = "ed_key"
else:
    ed_nbhd = base_eds[["ed_key", "nbhdname"]].merge(
        sel_elections[["shapefile_key"] + candidates],
        left_on="ed_key", right_on="shapefile_key", how="left",
    )
    for c in candidates:
        ed_nbhd[c] = pd.to_numeric(ed_nbhd[c], errors="coerce").fillna(0)
    nbhd_agg = ed_nbhd.groupby("nbhdname")[candidates].sum().reset_index()
    geo = nbhd_geo.merge(nbhd_agg, on="nbhdname", how="left")
    id_col   = "nbhdname"
    name_col = "nbhdname"

for c in candidates:
    geo[c] = pd.to_numeric(geo[c], errors="coerce")

geo["_total"] = geo[candidates].sum(axis=1)
safe_total = geo["_total"].replace(0, float("nan"))
for c in candidates:
    geo[f"pct_{c}"] = (geo[c] / safe_total * 100).round(1)

color_col = f"pct_{sel_candidate}"

for c in candidates:
    votes_col = pd.to_numeric(geo[c], errors="coerce").fillna(0)
    pct_col   = pd.to_numeric(geo[f"pct_{c}"], errors="coerce")
    geo[f"_h_{c}"] = [
        f"{int(v):,} ({p:.1f}%)" if pd.notna(p) else "—"
        for v, p in zip(votes_col, pct_col)
    ]

geo_json = json.loads(geo.to_json())

# ── Area multiselect (fill sidebar placeholder) ───────────────────────────────

all_areas = sorted(geo[id_col].dropna().unique().tolist())
ms_key    = f"area_ms_{election_key}"
if ms_key not in st.session_state:
    st.session_state[ms_key] = []

with _area_placeholder:
    sel_areas_raw = st.multiselect("Compare areas (max 2)", all_areas, key=ms_key)

st.session_state.sel_areas = sel_areas_raw[:2]


# ── Page header ───────────────────────────────────────────────────────────────

st.title("Buffalo Mayoral Elections")
st.markdown(
    f"### {sel_year} {'Democratic Primary' if sel_type == 'primary' else 'General Election'}"
)

if sel_type == "primary" and view == "Election District":
    st.info(
        "Primary ballots use consolidated polling districts — grey polygons "
        "indicate EDs merged into a neighbouring district for this race. "
        "Switch to Neighborhood view for complete coverage.",
        icon="ℹ️",
    )


# ── Top metrics ───────────────────────────────────────────────────────────────

sorted_cands = sorted(city_avg.items(), key=lambda x: x[1], reverse=True)
metric_cols  = st.columns(min(len(sorted_cands), 4))
for i, (cand, pct) in enumerate(sorted_cands[:4]):
    votes = pd.to_numeric(sel_elections[cand], errors="coerce").fillna(0).sum()
    metric_cols[i].metric(last_name(cand), f"{votes:,.0f}", f"{pct:.1f}%")


# ── Map + right panel ─────────────────────────────────────────────────────────

map_col, right_col = st.columns([3, 2])

with map_col:
    hover_h = {f"_h_{c}": True for c in candidates if f"_h_{c}" in geo.columns}

    fig_map = px.choropleth_map(
        geo,
        geojson=geo_json,
        locations=id_col,
        featureidkey=f"properties.{id_col}",
        color=color_col,
        color_continuous_scale="Blues",
        range_color=[0, 100],
        map_style="carto-positron",
        zoom=11,
        center=BUFFALO_CENTER,
        opacity=0.75,
        hover_name=name_col,
        hover_data={
            **hover_h,
            color_col:  False,
            "_total":   False,
            id_col:     False,
            name_col:   False,
            "nbhdnum":  False,
            **{f"pct_{c}": False for c in candidates},
        },
        labels={f"_h_{c}": c for c in candidates},
        title=f"{sel_candidate} — % of votes",
        height=560,
    )
    fig_map.update_layout(
        margin={"r": 0, "t": 40, "l": 0, "b": 0},
        coloraxis_colorbar=dict(
            thickness=12,
            len=0.6,
            title=dict(text="Vote %", side="right"),
            ticksuffix="%",
            tickfont=dict(size=11),
        ),
        clickmode="event+select",
    )

    for i, area_name in enumerate(st.session_state.sel_areas):
        mask = geo[id_col] == area_name
        if mask.any():
            highlight = geo[mask]
            h_json = json.loads(highlight.to_json())
            lats, lons = [], []
            for feat in h_json["features"]:
                coords    = feat["geometry"]["coordinates"]
                geom_type = feat["geometry"]["type"]
                rings = coords if geom_type == "Polygon" else [r for poly in coords for r in poly]
                for ring in rings:
                    lons += [pt[0] for pt in ring] + [None]
                    lats += [pt[1] for pt in ring] + [None]
            fig_map.add_trace(go.Scattermap(
                lat=lats, lon=lons,
                mode="lines",
                line=dict(color=AREA_COLORS[i], width=3),
                hoverinfo="skip",
                showlegend=False,
            ))

    event = st.plotly_chart(fig_map, on_select="rerun", key=f"map_{election_key}",
                            width="stretch", config={"displaylogo": False})

    if event and hasattr(event, "selection") and event.selection and event.selection.points:
        pt  = event.selection.points[0]
        idx = pt.get("pointIndex", -1)
        if idx != st.session_state.last_click_idx and 0 <= idx < len(geo):
            st.session_state.last_click_idx = idx
            area = str(geo.iloc[idx][id_col])
            cur  = list(st.session_state.sel_areas)
            if area in cur:
                cur.remove(area)
            elif len(cur) < 2:
                cur.append(area)
            else:
                cur = [cur[-1], area]
            st.session_state.sel_areas = cur
            st.session_state[ms_key]   = cur

    if not st.session_state.sel_areas:
        st.caption("Click a polygon or use the sidebar to compare areas.")


# ── Right panel ───────────────────────────────────────────────────────────────

with right_col:

    bar_df = pd.DataFrame({
        "Candidate": list(city_avg.keys()),
        "Pct":       list(city_avg.values()),
        "Votes":     [pd.to_numeric(sel_elections[c], errors="coerce").fillna(0).sum() for c in city_avg],
    }).sort_values("Pct", ascending=False)
    bar_df["Label"] = bar_df.apply(lambda r: f"{r.Votes:,.0f}  ({r.Pct:.1f}%)", axis=1)

    fig_city = go.Figure(go.Bar(
        x=bar_df["Pct"],
        y=bar_df["Candidate"],
        orientation="h",
        text=bar_df["Label"],
        textposition="outside",
        marker_color=[
            AREA_COLORS[0] if c == sel_candidate else "#c6dbef"
            for c in bar_df["Candidate"]
        ],
        hovertemplate="<b>%{y}</b><br>%{x:.1f}%<extra></extra>",
    ))
    fig_city.update_layout(
        title="City-wide Results",
        xaxis=dict(title="Vote %", range=[0, bar_df["Pct"].max() * 1.6], ticksuffix="%",
                   gridcolor=GRID_COLOR, zeroline=False),
        yaxis=dict(title=None, autorange="reversed", gridcolor=GRID_COLOR),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=max(220, len(candidates) * 42),
        margin={"r": 10, "t": 40, "l": 10, "b": 30},
    )
    st.plotly_chart(fig_city, width="stretch", config={"displaylogo": False})

    # ── Comparison panel ──────────────────────────────────────────────────────

    if st.session_state.sel_areas:
        st.divider()

        area_names = st.session_state.sel_areas
        area_data  = []
        for name in area_names:
            row = geo[geo[id_col] == name]
            if not row.empty:
                r = row.iloc[0]
                pcts  = area_pcts(r, candidates)
                votes = {c: int(float(r.get(c, 0) or 0)) for c in candidates}
                area_data.append((name, pcts, votes))

        if area_data:
            labels = [last_name(a[0]) if view == "Election District" else a[0]
                      for a in area_data]
            st.markdown(f"**Comparing:** {' vs '.join(labels)} vs City Avg")

            fig_cmp = go.Figure()
            for (name, pcts, votes), color, label in zip(area_data, AREA_COLORS, labels):
                fig_cmp.add_trace(go.Bar(
                    name=label,
                    x=[pcts.get(c, 0) for c in candidates],
                    y=candidates,
                    orientation="h",
                    marker_color=color,
                    text=[f"{votes.get(c,0):,} ({pcts.get(c,0):.1f}%)" for c in candidates],
                    textposition="outside",
                    hovertemplate="<b>%{y}</b><br>%{x:.1f}%<extra></extra>",
                ))
            fig_cmp.add_trace(go.Scatter(
                name="City Avg",
                x=[city_avg.get(c, 0) for c in candidates],
                y=candidates,
                mode="markers",
                marker=dict(color=AVG_COLOR, size=10, symbol="line-ns",
                            line=dict(width=2, color=AVG_COLOR)),
            ))

            max_x = max(max(p for p in pcts.values()) for _, pcts, _ in area_data)
            fig_cmp.update_layout(
                barmode="group",
                title="vs City Average",
                xaxis=dict(title="Vote %", ticksuffix="%", range=[0, max_x * 1.6],
                           gridcolor=GRID_COLOR, zeroline=False),
                yaxis=dict(title=None, autorange="reversed", gridcolor=GRID_COLOR),
                plot_bgcolor="white",
                paper_bgcolor="white",
                legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
                height=max(260, len(candidates) * 48),
                margin={"r": 10, "t": 30, "l": 10, "b": 60},
            )
            st.plotly_chart(fig_cmp, width="stretch", config={"displaylogo": False})

            for (name, pcts, _), color in zip(area_data, AREA_COLORS):
                label = last_name(name) if view == "Election District" else name
                st.markdown(f"<span style='color:{color};font-weight:bold'>■ {label}</span>",
                            unsafe_allow_html=True)
                metric_row = st.columns(min(len(candidates), 3))
                for i, c in enumerate(candidates):
                    delta = pcts.get(c, 0) - city_avg.get(c, 0)
                    metric_row[i % 3].metric(
                        label=last_name(c),
                        value=f"{pcts.get(c,0):.1f}%",
                        delta=f"{delta:+.1f}pp",
                    )

    else:
        st.divider()
        if view == "Neighborhood":
            col_name, sort_col = "Neighborhood", f"pct_{sel_candidate}"
            id_display = "nbhdname"
        else:
            col_name, sort_col = "District", f"pct_{sel_candidate}"
            id_display = id_col

        if sort_col in geo.columns:
            tbl_rows = []
            for _, row in geo.sort_values(sort_col, ascending=False).iterrows():
                if pd.isna(row.get(sort_col)):
                    continue
                entry = {col_name: row[id_display]}
                for c in candidates:
                    val = row.get(f"pct_{c}")
                    entry[c] = float(val) if pd.notna(val) else None
                tbl_rows.append(entry)
            if tbl_rows:
                tbl = pd.DataFrame(tbl_rows)
                col_cfg = {c: st.column_config.NumberColumn(c, format="%.1f%%") for c in candidates}
                st.dataframe(tbl, column_config=col_cfg, width="stretch", height=300, hide_index=True)
