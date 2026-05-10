"""
Spatial join pipeline:
  1. Filter NYS election districts to City of Buffalo
  2. Assign each ED to a neighborhood via spatial join
  3. Merge election results onto ED geometries
  4. Save GeoJSONs for the dashboard
"""

import pandas as pd
import geopandas as gpd
from pathlib import Path

ROOT = Path(__file__).parent.parent
GEO_DIR = ROOT / "data" / "geo"
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_DIR = ROOT / "data" / "geo"

NYS_ED_SHP = ROOT / "NYS_Election_Districts" / "Election_Districts.shp"
NBHD_SHP = GEO_DIR / "neighborhoods"


def load_buffalo_eds() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(NYS_ED_SHP)
    buffalo = gdf[gdf["Municipali"] == "Buffalo"].copy()
    buffalo = buffalo.rename(columns={"Election_D": "ed_key"})
    buffalo = buffalo.to_crs("EPSG:4326")
    print(f"Buffalo EDs loaded: {len(buffalo)}")
    return buffalo[["ed_key", "geometry"]]


def load_neighborhoods() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(NBHD_SHP)
    gdf = gdf.to_crs("EPSG:4326")
    gdf = gdf[["nbhdname", "nbhdnum", "geometry"]].copy()
    print(f"Neighborhoods loaded: {len(gdf)}")
    return gdf


def assign_neighborhoods(eds: gpd.GeoDataFrame, nbhds: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Assign each ED to a neighborhood using centroid-based spatial join."""
    # Project to UTM zone 17N (NAD83) for accurate centroid calculation
    projected = eds.to_crs("EPSG:26917")
    ed_centroids = projected.copy()
    ed_centroids["geometry"] = projected.geometry.centroid
    ed_centroids = ed_centroids.to_crs("EPSG:4326")
    joined = gpd.sjoin(ed_centroids, nbhds, how="left", predicate="within")
    joined = joined[["ed_key", "nbhdname", "nbhdnum"]].copy()
    eds_with_nbhd = eds.merge(joined, on="ed_key", how="left")
    unmatched = eds_with_nbhd["nbhdname"].isna().sum()
    if unmatched:
        print(f"  Warning: {unmatched} EDs did not match a neighborhood (likely boundary edge cases)")
    return eds_with_nbhd


def load_elections() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_DIR / "mayoral_all.csv", dtype=str)
    # Normalize blank/void/scatter columns — they vary by year
    blank_cols = [c for c in df.columns if any(
        kw in c.lower() for kw in ("blank", "void", "scatter")
    )]
    df["blank_void_scatter"] = df[blank_cols].apply(
        lambda row: pd.to_numeric(row, errors="coerce").fillna(0).sum(), axis=1
    )
    # Normalize total column
    total_cols = [c for c in df.columns if c.lower() == "total"]
    if total_cols:
        df["total_votes"] = pd.to_numeric(df[total_cols[0]], errors="coerce").fillna(0)

    # Drop raw blank/void/scatter/total columns to keep things clean
    drop_cols = blank_cols + [c for c in df.columns if c.lower() in ("total", "total votes")]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
    return df


def identify_candidates(df: pd.DataFrame) -> list[str]:
    """Return all columns that are candidate vote counts."""
    non_candidate = {
        "year", "election_type", "ward", "ed_num", "ed_label",
        "shapefile_key", "blank_void_scatter", "total_votes",
    }
    return [c for c in df.columns if c not in non_candidate]


def build_geo_elections(eds: gpd.GeoDataFrame, elections: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Join elections onto ED geometries.
    Adds vote_share_<candidate> columns for each election,
    computed as each candidate's share of total valid votes.
    """
    # Merge on shapefile_key = ed_key
    merged = eds.merge(
        elections,
        left_on="ed_key",
        right_on="shapefile_key",
        how="left",
    )

    # Compute vote shares per row (each row is one ED × one election)
    candidate_cols = identify_candidates(elections)
    for col in candidate_cols:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)

    merged["total_votes"] = pd.to_numeric(merged.get("total_votes", 0), errors="coerce").fillna(0)

    for col in candidate_cols:
        if col in merged.columns:
            safe_denom = merged["total_votes"].replace(0, float("nan"))
            merged[f"share_{col}"] = (merged[col] / safe_denom * 100).round(1)

    return merged


def run():
    eds = load_buffalo_eds()
    nbhds = load_neighborhoods()
    eds = assign_neighborhoods(eds, nbhds)

    # Save the base ED → neighborhood mapping
    eds.to_file(OUT_DIR / "buffalo_eds.geojson", driver="GeoJSON")
    print(f"Saved buffalo_eds.geojson ({len(eds)} EDs)")

    # Build full election + geo dataset
    elections = load_elections()
    geo_elections = build_geo_elections(eds, elections)

    geo_elections.to_file(OUT_DIR / "buffalo_eds_elections.geojson", driver="GeoJSON")
    print(f"Saved buffalo_eds_elections.geojson ({len(geo_elections)} rows)")

    # Also save a neighborhood-aggregated version for each election
    candidate_cols = identify_candidates(elections)
    numeric_cols = candidate_cols + ["blank_void_scatter", "total_votes"]

    for col in numeric_cols:
        if col in geo_elections.columns:
            geo_elections[col] = pd.to_numeric(geo_elections[col], errors="coerce").fillna(0)

    nbhd_agg = (
        geo_elections.dropna(subset=["year"])
        .groupby(["year", "election_type", "nbhdname", "nbhdnum"])[
            [c for c in numeric_cols if c in geo_elections.columns]
        ]
        .sum()
        .reset_index()
    )

    # Recompute shares at neighborhood level
    for col in candidate_cols:
        if col in nbhd_agg.columns:
            safe_denom = nbhd_agg["total_votes"].replace(0, float("nan"))
            nbhd_agg[f"share_{col}"] = (nbhd_agg[col] / safe_denom * 100).round(1)

    # Attach neighborhood geometry
    nbhd_geo = nbhds.merge(nbhd_agg, on=["nbhdname", "nbhdnum"], how="right")
    nbhd_geo = gpd.GeoDataFrame(nbhd_geo, geometry="geometry", crs="EPSG:4326")
    nbhd_geo.to_file(OUT_DIR / "buffalo_nbhd_elections.geojson", driver="GeoJSON")
    print(f"Saved buffalo_nbhd_elections.geojson ({len(nbhd_geo)} rows)")

    # Summary
    print("\nED match rate by election:")
    for (yr, et), grp in geo_elections.dropna(subset=["year"]).groupby(["year", "election_type"]):
        matched = grp["shapefile_key"].notna().sum()
        print(f"  {yr} {et}: {matched}/{len(eds)} EDs matched")


if __name__ == "__main__":
    run()
