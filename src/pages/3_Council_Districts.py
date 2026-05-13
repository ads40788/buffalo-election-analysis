"""
Buffalo Common Council Districts — longitudinal results by seat.
Line chart across all cycles + choropleth for a selected election.
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
div[data-testid="stMetricValue"] { font-size: 1.5rem !important; font-weight: 700 !important; }
@media (max-width: 768px) {
    .block-container { padding-left: 0.5rem !important; padding-right: 0.5rem !important; padding-top: 0.5rem !important; }
    h1 { font-size: 1.4rem !important; }
    h2 { font-size: 1.1rem !important; }
    div[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
    div[data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
}
</style>
""", unsafe_allow_html=True)

WARD_CODES = {
    "delaware":   "DEL", "ellicott":   "ELL", "fillmore":  "FIL",
    "lovejoy":    "LOV", "masten":     "MAS", "niagara":   "NIA",
    "north":      "NOR", "south":      "SOU", "university": "UNI",
}
META_COLS  = {"year", "election_type", "district", "ward", "ed_num", "ed_label", "shapefile_key"}
NOISE_RE   = re.compile(r"\b(blank|void|scatter|total)\b", re.IGNORECASE)
GRID_COLOR = "rgba(0,0,0,0.07)"
LINE_COLORS = px.colors.qualitative.D3

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
    # Strip middle initials: single capital letter (± period) between first and last name
    parts = name.split()
    if len(parts) >= 3:
        parts = [
            p for i, p in enumerate(parts)
            if not (0 < i < len(parts) - 1 and re.match(r"^[A-Z]\.?$", p))
        ]
        name = " ".join(parts)
    return name


# ── Data loading ───────────────────────────────────────────────────────────────

@st.cache_data
def load_base_eds() -> gpd.GeoDataFrame:
    return gpd.read_file(GEO_DIR / "buffalo_eds.geojson")

@st.cache_data
def load_council() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "council_all.csv", dtype={"year": int})

@st.cache_data
def district_eds_geo(_base_eds: gpd.GeoDataFrame, ward_code: str) -> gpd.GeoDataFrame:
    return _base_eds[
        _base_eds["ed_key"].str.contains(f" {ward_code} ", regex=False)
    ].copy()

@st.cache_data
def district_nbhd_geo(_dist_eds: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return _dist_eds.dissolve(by="nbhdname").reset_index()[["nbhdname", "geometry"]]


# ── Analysis helpers ───────────────────────────────────────────────────────────

def get_candidates(df: pd.DataFrame) -> list[str]:
    return [
        c for c in df.columns
        if c not in META_COLS
        and not NOISE_RE.search(c)
        and pd.to_numeric(df[c], errors="coerce").gt(0).any()
    ]


def build_timeline(df: pd.DataFrame, district: str) -> pd.DataFrame:
    """District-wide vote totals in long form for the line chart."""
    sub = df[df["district"] == district]
    records = []
    for (yr, etype), grp in sub.groupby(["year", "election_type"]):
        cands = get_candidates(grp)
        raw = {normalize_name(c): pd.to_numeric(grp[c], errors="coerce").fillna(0).sum()
               for c in cands}
        merged: dict[str, float] = {}
        for name, votes in raw.items():
            merged[name] = merged.get(name, 0) + votes
        grand = sum(merged.values())
        for name, votes in merged.items():
            records.append({
                "year": yr, "election_type": etype, "candidate": name,
                "votes": int(votes),
                "vote_pct": round(votes / grand * 100, 1) if grand > 0 else 0.0,
                "total_votes": int(grand),
            })
    return pd.DataFrame(records) if records else pd.DataFrame()


# ── Line chart ─────────────────────────────────────────────────────────────────

def make_line_chart(timeline: pd.DataFrame, title: str) -> go.Figure:
    """Render a vote-share line chart for a single election type."""
    if timeline.empty:
        return go.Figure()

    # Keep candidates who cleared 2% in at least one election
    max_pct = timeline.groupby("candidate")["vote_pct"].max()
    keep    = max_pct[max_pct >= 2].index
    data    = timeline[timeline["candidate"].isin(keep)].copy()
    if data.empty:
        return go.Figure()

    # Stable candidate order: sort by total votes descending
    order = (
        data.groupby("candidate")["votes"].sum()
        .sort_values(ascending=False)
        .index.tolist()
    )

    fig = go.Figure()
    all_years = sorted(data["year"].unique())

    for i, cand in enumerate(order):
        color = LINE_COLORS[i % len(LINE_COLORS)]
        sub   = data[data["candidate"] == cand].sort_values("year")
        fig.add_trace(go.Scatter(
            x=sub["year"], y=sub["vote_pct"],
            mode="lines+markers",
            name=cand,
            line=dict(color=color, width=2.5),
            marker=dict(size=8),
            customdata=sub[["votes", "total_votes"]].values,
            hovertemplate=(
                f"<b>{cand}</b><br>"
                "%{x}<br>"
                "%{y:.1f}%  (%{customdata[0]:,} / %{customdata[1]:,} votes)"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=title,
        xaxis=dict(
            title="Year",
            tickvals=all_years,
            ticktext=[str(y) for y in all_years],
            gridcolor=GRID_COLOR, zeroline=False,
        ),
        yaxis=dict(
            title="Vote share (%)",
            range=[0, 105],
            gridcolor=GRID_COLOR, zeroline=False,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="v", x=1.01, y=1, xanchor="left"),
        margin=dict(t=40, b=40, l=50, r=10),
        height=320,
    )
    return fig


# ── Map helpers ────────────────────────────────────────────────────────────────

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


def map_params(gdf: gpd.GeoDataFrame) -> tuple[dict, float]:
    if gdf is None or len(gdf) == 0:
        return {"lat": 42.886, "lon": -78.878}, 11.5
    b = gdf.total_bounds
    center = {"lat": (b[1] + b[3]) / 2, "lon": (b[0] + b[2]) / 2}
    span = max(b[3] - b[1], (b[2] - b[0]) * 0.7)
    zoom = (13.5 if span < 0.02 else
            13.0 if span < 0.04 else
            12.5 if span < 0.07 else 12.0)
    return center, zoom


def make_choropleth(
    geo: gpd.GeoDataFrame,
    id_col: str,
    val_col: str,
    center: dict,
    zoom: float,
    title: str,
    cand_label: str,
    height: int = 420,
) -> go.Figure:
    geo_json = json.loads(geo.to_json())
    hover_data = {val_col: True, id_col: False}
    if "nbhdnum" in geo.columns:
        hover_data["nbhdnum"] = False

    fig = px.choropleth_map(
        geo,
        geojson=geo_json,
        locations=id_col,
        featureidkey=f"properties.{id_col}",
        color=val_col,
        color_continuous_scale="Blues",
        range_color=[0, 100],
        map_style="carto-positron",
        zoom=zoom,
        center=center,
        opacity=0.75,
        hover_name=id_col,
        hover_data=hover_data,
        labels={val_col: "Vote %"},
        title=title,
        height=height,
    )
    fig.update_layout(
        margin={"r": 0, "t": 36, "l": 0, "b": 0},
        coloraxis_colorbar=dict(
            thickness=12, len=0.6,
            title=dict(text="%", side="right"),
            ticksuffix="%", tickfont=dict(size=11),
        ),
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{location}</b><br>"
            f"{cand_label}: %{{z:.1f}}%"
            "<extra></extra>"
        ),
    )
    fig.add_trace(boundary_trace(geo))
    return fig


# ── Load data ──────────────────────────────────────────────────────────────────

base_eds   = load_base_eds()
council_df = load_council()


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    district = st.selectbox(
        "District",
        list(WARD_CODES.keys()),
        format_func=lambda d: d.title(),
    )
    view = st.radio("Geography", ["Neighborhood", "Election District"])
    st.divider()

    # Available elections for this district
    avail = (
        council_df[council_df["district"] == district]
        [["year", "election_type"]]
        .drop_duplicates()
        .sort_values(["year", "election_type"], ascending=[False, False])
    )
    election_opts = [
        f"{int(r.year)} {r.election_type.title()}"
        for r in avail.itertuples()
    ]
    if not election_opts:
        st.warning("No data found for this district.")
        st.stop()

    map_sel  = st.selectbox("Map: election", election_opts)
    map_year = int(map_sel.split()[0])
    map_etype = map_sel.split()[1].lower()

    elec_slice = council_df[
        (council_df["district"] == district) &
        (council_df["year"]           == map_year) &
        (council_df["election_type"]  == map_etype)
    ].copy()

    cands = get_candidates(elec_slice)
    if not cands:
        st.warning("No candidate data for this selection.")
        st.stop()

    totals_by_cand = {
        c: pd.to_numeric(elec_slice[c], errors="coerce").fillna(0).sum()
        for c in cands
    }
    sorted_cands = sorted(cands, key=lambda c: totals_by_cand[c], reverse=True)
    map_cand = st.selectbox(
        "Map: candidate",
        sorted_cands,
        format_func=normalize_name,
    )
    st.divider()
    st.caption("Data: Erie County Board of Elections · NYS GIS")


# ── District geo ───────────────────────────────────────────────────────────────

ward_code  = WARD_CODES[district]
dist_eds   = district_eds_geo(base_eds, ward_code)
dist_nbhd  = district_nbhd_geo(dist_eds)
center, zoom = map_params(dist_eds if view == "Election District" else dist_nbhd)


# ── Timeline data ──────────────────────────────────────────────────────────────

timeline = build_timeline(council_df, district)


# ── Page header ────────────────────────────────────────────────────────────────

st.title(f"{district.title()} District")

# Top metrics from the most recent general election
gen_data = council_df[
    (council_df["district"] == district) &
    (council_df["election_type"] == "general")
]
if not gen_data.empty:
    latest_yr = gen_data["year"].max()
    latest    = gen_data[gen_data["year"] == latest_yr]
    latest_cands = get_candidates(latest)
    totals = {
        normalize_name(c): pd.to_numeric(latest[c], errors="coerce").fillna(0).sum()
        for c in latest_cands
    }
    grand  = sum(totals.values())
    winner = max(totals, key=totals.get) if totals else "—"

    winner_pct = f"{totals[winner]/grand*100:.1f}%" if grand > 0 else "—"
    _metric_items = [
        ("Most recent", str(latest_yr)),
        ("Winner", last_name(winner)),
        ("Vote share", winner_pct),
    ]
    _cards = "".join(
        f'<div style="flex:1;min-width:88px;background:#f8f9fa;border-radius:8px;'
        f'padding:0.6rem 0.75rem;border:1px solid #e8e8e8;">'
        f'<div style="font-size:0.72rem;color:#666;font-weight:500;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{lbl}</div>'
        f'<div style="font-size:1.25rem;font-weight:700;color:#111;'
        f'white-space:nowrap;">{val}</div></div>'
        for lbl, val in _metric_items
    )
    st.markdown(
        f'<div style="display:flex;gap:0.5rem;flex-wrap:nowrap;overflow-x:auto;'
        f'margin-bottom:0.75rem;padding-bottom:0.25rem;">{_cards}</div>',
        unsafe_allow_html=True,
    )

st.divider()


# ── Line charts (general + primary) ───────────────────────────────────────────

gen_timeline = timeline[timeline["election_type"] == "general"]
pri_timeline = timeline[timeline["election_type"] == "primary"]

fig_gen = make_line_chart(
    gen_timeline,
    title=f"{district.title()} District — General elections",
)
st.plotly_chart(fig_gen, use_container_width=True, config={"displaylogo": False})

if not pri_timeline.empty:
    fig_pri = make_line_chart(
        pri_timeline,
        title=f"{district.title()} District — Democratic primaries",
    )
    st.plotly_chart(fig_pri, use_container_width=True, config={"displaylogo": False})

st.divider()


# ── Choropleth ─────────────────────────────────────────────────────────────────

map_col, info_col = st.columns([3, 1])

# Build aggregated geo for the map
norm_cand = normalize_name(map_cand)

if view == "Election District":
    id_col = "ed_key"
    valid_cands = get_candidates(elec_slice)
    elec_slice = elec_slice.copy()
    for c in valid_cands:
        elec_slice[c] = pd.to_numeric(elec_slice[c], errors="coerce").fillna(0)
    elec_slice["_total"] = elec_slice[valid_cands].sum(axis=1)
    raw = elec_slice[map_cand] if map_cand in elec_slice.columns else pd.Series(0.0, index=elec_slice.index)
    elec_slice["val"] = (raw / elec_slice["_total"].replace(0, float("nan")) * 100).round(2)

    geo_map = dist_eds.merge(
        elec_slice[["shapefile_key", "val", "_total"]],
        left_on="ed_key", right_on="shapefile_key", how="left",
    )
    match_pct = geo_map["val"].notna().mean()

else:
    id_col = "nbhdname"
    valid_cands = get_candidates(elec_slice)
    elec_slice = elec_slice.copy()
    for c in valid_cands:
        elec_slice[c] = pd.to_numeric(elec_slice[c], errors="coerce").fillna(0)

    ed_nbhd = dist_eds[["ed_key", "nbhdname"]].merge(
        elec_slice[["shapefile_key"] + valid_cands],
        left_on="ed_key", right_on="shapefile_key", how="left",
    )
    for c in valid_cands:
        ed_nbhd[c] = pd.to_numeric(ed_nbhd[c], errors="coerce").fillna(0)

    agg           = ed_nbhd.groupby("nbhdname")[valid_cands].sum().reset_index()
    agg["_total"] = agg[valid_cands].sum(axis=1)
    raw_col       = map_cand if map_cand in agg.columns else None
    agg["val"]    = (
        pd.to_numeric(agg[raw_col], errors="coerce").fillna(0)
        / agg["_total"].replace(0, float("nan")) * 100
    ).round(2) if raw_col else float("nan")

    geo_map = dist_nbhd.merge(agg[["nbhdname", "val", "_total"]], on="nbhdname", how="left")
    match_pct = geo_map["val"].notna().mean()

map_title = f"{norm_cand} · {district.title()} {map_etype.title()} {map_year}"

with map_col:
    fig_map = make_choropleth(
        geo_map, id_col, "val", center, zoom,
        title=map_title, cand_label=norm_cand, height=380,
    )
    st.plotly_chart(fig_map, use_container_width=True, config={"displaylogo": False})

    # Warn if few EDs matched (likely pre-2015 boundary mismatch)
    if match_pct < 0.5:
        st.caption(
            f"Only {match_pct:.0%} of {view.lower()}s matched. "
            "Pre-2015 elections use historical ED boundaries that may differ "
            "from the current shapefile — neighborhood view is more reliable for older cycles."
        )

with info_col:
    st.markdown("&nbsp;")
    if not elec_slice.empty and not timeline.empty:
        row = timeline[
            (timeline["year"]           == map_year) &
            (timeline["election_type"]  == map_etype) &
            (timeline["candidate"]      == norm_cand)
        ]
        if not row.empty:
            r = row.iloc[0]
            st.metric(f"{last_name(norm_cand)}", f"{r['vote_pct']:.1f}%")
            st.metric("Votes", f"{r['votes']:,}")
            st.metric("Total cast", f"{r['total_votes']:,}")

    st.divider()
    # Incumbency summary table
    if not timeline.empty:
        gen_timeline = timeline[timeline["election_type"] == "general"].copy()
        if not gen_timeline.empty:
            winners = (
                gen_timeline.sort_values("vote_pct", ascending=False)
                .groupby("year")
                .first()
                .reset_index()[["year", "candidate", "vote_pct"]]
                .sort_values("year")
                .rename(columns={"year": "Year", "candidate": "Winner", "vote_pct": "Vote %"})
            )
            winners["Winner"] = winners["Winner"].apply(last_name)
            st.caption("**General election winners**")
            st.dataframe(winners, hide_index=True, use_container_width=True)
