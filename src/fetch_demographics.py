"""
Fetch ACS 2020 5-year demographic data for Erie County census tracts,
spatially join to Buffalo neighborhoods, and save a neighborhood-level CSV.

Run once:  python src/fetch_demographics.py
Output:    data/processed/neighborhood_demographics.csv
"""

import requests
import pandas as pd
import geopandas as gpd
from pathlib import Path

ROOT    = Path(__file__).parent.parent
GEO_DIR = ROOT / "data" / "geo"
OUT     = ROOT / "data" / "processed" / "neighborhood_demographics.csv"

ACS_VARS = {
    "B02001_001E": "pop_total",
    "B02001_002E": "pop_white",
    "B02001_003E": "pop_black",
    "B19013_001E": "median_income",
    "B15003_001E": "edu_total",
    "B15003_022E": "edu_bachelors",
    "B15003_023E": "edu_masters",
    "B15003_024E": "edu_professional",
    "B15003_025E": "edu_doctorate",
}

SENTINEL = -666666666  # Census missing-value flag


def fetch_acs() -> pd.DataFrame:
    """ACS 2020 5-year for Erie County (FIPS 36-029) census tracts."""
    vars_str = ",".join(ACS_VARS)
    url = (
        f"https://api.census.gov/data/2020/acs/acs5"
        f"?get=NAME,{vars_str}"
        f"&for=tract:*&in=state:36%20county:029"
    )
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    raw = r.json()
    df = pd.DataFrame(raw[1:], columns=raw[0])
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    for var, name in ACS_VARS.items():
        df[name] = pd.to_numeric(df[var], errors="coerce")
        df.loc[df[name] == SENTINEL, name] = float("nan")
    return df[["GEOID"] + list(ACS_VARS.values())]


def fetch_tract_geo() -> gpd.GeoDataFrame:
    """Download 2020 NY census tract cartographic boundaries, filter to Erie County."""
    url = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_36_tract_500k.zip"
    print(f"  Downloading tract boundaries from Census.gov…")
    gdf = gpd.read_file(url)
    erie = gdf[gdf["COUNTYFP"] == "029"].copy()
    return erie[["GEOID", "geometry"]].to_crs("EPSG:4326")


def load_nbhds() -> gpd.GeoDataFrame:
    """Dissolve ED geometries to Buffalo neighborhood polygons."""
    eds = gpd.read_file(GEO_DIR / "buffalo_eds.geojson")
    nbhds = eds.dissolve("nbhdname").reset_index()[["nbhdname", "geometry"]]
    return nbhds.to_crs("EPSG:4326")


def run():
    print("Fetching ACS 2020 5-year data…")
    acs = fetch_acs()
    print(f"  {len(acs)} Erie County tracts fetched")

    print("Fetching tract boundaries…")
    tracts = fetch_tract_geo()
    tracts = tracts.merge(acs, on="GEOID", how="inner")
    print(f"  {len(tracts)} tracts with geometry + ACS data")

    print("Loading Buffalo neighborhood polygons…")
    nbhds = load_nbhds()

    # Project to UTM zone 17N for accurate centroids
    proj = tracts.to_crs("EPSG:26917")
    centroids = gpd.GeoDataFrame(
        tracts.drop(columns="geometry"),
        geometry=proj.geometry.centroid.to_crs("EPSG:4326"),
        crs="EPSG:4326",
    )

    # Assign each tract centroid to a Buffalo neighborhood
    joined = gpd.sjoin(centroids, nbhds[["nbhdname", "geometry"]],
                       how="left", predicate="within")
    matched = joined.dropna(subset=["nbhdname"])
    print(f"  {len(matched)} of {len(tracts)} Erie tracts mapped to Buffalo neighborhoods")

    # Aggregate population totals to neighborhood
    sum_cols = [
        "pop_total", "pop_white", "pop_black",
        "edu_total", "edu_bachelors", "edu_masters", "edu_professional", "edu_doctorate",
    ]
    agg = matched.groupby("nbhdname")[sum_cols].sum()

    # Population-weighted average of median income
    inc = (
        matched.dropna(subset=["median_income"])
        .assign(wi=lambda d: d["median_income"] * d["pop_total"])
        .groupby("nbhdname")
        .agg(wi_sum=("wi", "sum"), pop_sum=("pop_total", "sum"))
    )
    agg["median_income"] = (inc["wi_sum"] / inc["pop_sum"]).round(0)

    # Derived rates
    agg["pct_white"]   = (agg["pop_white"] / agg["pop_total"]).round(4)
    agg["pct_black"]   = (agg["pop_black"] / agg["pop_total"]).round(4)
    edu_col = agg[["edu_bachelors", "edu_masters", "edu_professional", "edu_doctorate"]].sum(axis=1)
    agg["pct_college"] = (edu_col / agg["edu_total"]).round(4)

    result = agg.reset_index()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT, index=False)
    print(f"\nSaved: {OUT}  ({len(result)} neighborhoods)")
    print(
        result[["nbhdname", "pop_total", "pct_white", "pct_black",
                "median_income", "pct_college"]]
        .sort_values("pct_black", ascending=False)
        .to_string(index=False)
    )


if __name__ == "__main__":
    run()
