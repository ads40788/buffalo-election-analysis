"""
Parse presidential and congressional results for Buffalo EDs from even-year
Erie County BOE canvass books.  Aggregates to neighborhood level.

Run once:  python src/parse_federal.py
Output:    data/processed/federal_by_nbhd.csv
           data/processed/federal_by_city.csv
"""

import re
import pandas as pd
import geopandas as gpd
from pathlib import Path

ROOT    = Path(__file__).parent.parent
RAW_DIR = ROOT / "Elections Data Congressional and Presidential"
GEO_DIR = ROOT / "data" / "geo"
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Ward / ED helpers (mirrors parse_elections.py) ────────────────────────────

WARD_CODES = {
    "delaware": "DEL", "ellicott": "ELL", "fillmore": "FIL",
    "lovejoy": "LOV",  "masten":   "MAS", "niagara":  "NIA",
    "north":   "NOR",  "south":    "SOU", "university":"UNI",
}

ORDINAL_RE  = re.compile(r"^(\d+)(st|nd|rd|th)\s+[Dd]istrict", re.IGNORECASE)
MODERN_ED_RE = re.compile(r"^([A-Za-z]{2,4})\s+\d")
NOISE_RE    = re.compile(r"\b(blank|void|scatter|total|federal)", re.IGNORECASE)

# Broad party-line suffix pattern for name cleaning
PARTY_SUFFIX_RE = re.compile(
    r"\s+(Democrat(ic)?|Republican[\w/\s]*|Conservative|Independence|"
    r"Working Families|Green( Party)?|Reform|Write-?In|Women.?s Equality|"
    r"Liberal|Right to Life|Progressive|WEP|WOR|GRE|REF|IND|CON|REP|"
    r"Back the Blue[\w\s/]*|Public Service|Libertarian|Socialism[\w\s]*|"
    r"Constitution|Peace[\w\s]*|Strong Leadership|Patriot|Unite[\w\s]*)$",
    re.IGNORECASE,
)


def clean_name(text: str) -> str:
    """Extract candidate name, stripping party line and running-mate."""
    text = re.sub(r"\s+", " ", str(text).replace("\n", " ")).strip()
    text = PARTY_SUFFIX_RE.sub("", text).strip()
    # Presidential tickets: "Biden / Harris" → "Biden"
    if "/" in text:
        text = text.split("/")[0].strip()
    return text


def get_party(cell_text: str) -> str:
    t = cell_text.lower()
    if "democrat" in t:
        return "democrat"
    if "republican" in t:
        return "republican"
    if "conservative" in t:
        return "conservative"   # almost always same person as rep
    return "other"


def is_ward_header(row_vals: list) -> str | None:
    first    = str(row_vals[0]).strip().lower()
    rest_emp = all(v == "" for v in row_vals[1:])
    if rest_emp and first in WARD_CODES:
        return WARD_CODES[first]
    return None


def is_ed_row(row_vals: list) -> bool:
    label = str(row_vals[0]).strip()
    return bool(MODERN_ED_RE.match(label) or ORDINAL_RE.match(label))


def parse_ed_label(raw: str, current_ward: str) -> tuple[str, str]:
    raw = str(raw).strip()
    m = ORDINAL_RE.match(raw)
    if m:
        return current_ward, m.group(1)
    m = re.match(r"([A-Za-z]{3,4})\s+0*(\d+)", raw)
    if m:
        return m.group(1).upper(), m.group(2)
    return "", ""


# ── Core sheet parser ─────────────────────────────────────────────────────────

def parse_federal_sheet(df_raw: pd.DataFrame) -> pd.DataFrame | None:
    """
    Parse any federal/statewide canvass sheet.
    Returns tidy DataFrame: ward, ed_num, shapefile_key, <candidate_name>…
    Candidates running on multiple party lines are summed into a single column.
    """
    header = df_raw.iloc[0].tolist()

    # Build candidate_cols: {clean_name: {"cols": [...], "parties": [...]}}
    candidate_cols: dict[str, dict] = {}
    for idx, cell in enumerate(header):
        if idx == 0:
            continue
        cell_str = str(cell).replace("\n", " ").strip()
        if not cell_str or cell_str.lower() == "nan":
            continue
        if NOISE_RE.search(cell_str):
            continue
        party = get_party(cell_str)
        name  = clean_name(cell_str)
        if not name:
            continue
        if name not in candidate_cols:
            candidate_cols[name] = {"cols": [], "parties": []}
        candidate_cols[name]["cols"].append(idx)
        candidate_cols[name]["parties"].append(party)

    if not candidate_cols:
        return None

    records      = []
    current_ward = None

    for i in range(1, len(df_raw)):
        row      = df_raw.iloc[i].tolist()
        row_vals = [str(v).strip() if str(v).strip() != "nan" else "" for v in row]

        if all(v == "" for v in row_vals):
            continue
        if re.match(r"^20\d{2}$|^19\d{2}$", row_vals[0]):
            continue
        # Total rows
        if re.search(r"^total$", row_vals[0], re.IGNORECASE):
            continue

        ward = is_ward_header(row_vals)
        if ward:
            current_ward = ward
            continue

        if current_ward and is_ed_row(row_vals):
            ward_code, ed_num = parse_ed_label(row_vals[0], current_ward)
            if not ward_code:
                ward_code = current_ward

            rec = {
                "ward":          ward_code,
                "ed_num":        ed_num,
                "shapefile_key": f"Buffalo {ward_code} {ed_num}",
            }
            for cand_name, info in candidate_cols.items():
                votes = 0
                for col_idx in info["cols"]:
                    if col_idx < len(row):
                        try:
                            v = row[col_idx]
                            votes += int(float(str(v))) if str(v).strip() not in ("", "nan") else 0
                        except (ValueError, TypeError):
                            pass
                rec[cand_name] = votes
            records.append(rec)

    if not records:
        return None

    df = pd.DataFrame(records)
    # Attach party info for each candidate (for Dem/Rep identification later)
    df.attrs["candidate_parties"] = {
        name: info["parties"] for name, info in candidate_cols.items()
    }
    return df


# ── Identify Democrat and Republican ─────────────────────────────────────────

def dem_rep_cols(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """Return (dem_col, rep_col) from the parsed candidate columns."""
    parties = df.attrs.get("candidate_parties", {})
    dem_col = rep_col = None
    for name, lines in parties.items():
        if name not in df.columns:
            continue
        if any("democrat" in p for p in lines) and dem_col is None:
            dem_col = name
        if any("republican" in p for p in lines) and rep_col is None:
            rep_col = name
    # Fallback: candidate who ran on Conservative line only (no Republican line)
    if rep_col is None:
        for name, lines in parties.items():
            if name not in df.columns:
                continue
            if any("conservative" in p for p in lines):
                rep_col = name
                break
    return dem_col, rep_col


# ── Aggregate to neighborhood ─────────────────────────────────────────────────

def aggregate_to_nbhd(
    df: pd.DataFrame,
    eds: pd.DataFrame,
    dem_col: str | None,
    rep_col: str | None,
    year: int,
    race_type: str,
    race_label: str,
) -> pd.DataFrame | None:
    """Merge ED results to neighborhoods, compute Dem/Rep pct."""
    cand_cols = [c for c in df.columns
                 if c not in ("ward", "ed_num", "shapefile_key")]

    merged = df.merge(eds[["ed_key", "nbhdname"]],
                      left_on="shapefile_key", right_on="ed_key", how="inner")
    if merged.empty:
        return None

    agg = merged.groupby("nbhdname")[cand_cols].sum()

    dem_votes   = agg[dem_col] if dem_col in agg.columns else pd.Series(0, index=agg.index)
    rep_votes   = agg[rep_col] if rep_col in agg.columns else pd.Series(0, index=agg.index)
    other_votes = agg[[c for c in cand_cols if c not in (dem_col, rep_col)]].sum(axis=1)
    total       = dem_votes + rep_votes + other_votes

    result = pd.DataFrame({
        "year":          year,
        "race_type":     race_type,
        "race_label":    race_label,
        "dem_candidate": dem_col or "",
        "rep_candidate": rep_col or "",
        "nbhdname":      agg.index,
        "dem_votes":     dem_votes.values,
        "rep_votes":     rep_votes.values,
        "other_votes":   other_votes.values,
        "total_votes":   total.values,
    }).reset_index(drop=True)

    result["dem_pct"] = (result["dem_votes"] / result["total_votes"].replace(0, float("nan")) * 100).round(2)
    result["rep_pct"] = (result["rep_votes"] / result["total_votes"].replace(0, float("nan")) * 100).round(2)

    return result


# ── Race configurations ───────────────────────────────────────────────────────

RACE_CONFIGS = [
    # (filename, engine, year, race_type, sheet_name, race_label)
    # Pre-2012: Buffalo was split between CD-27 and CD-28 (old district lines).
    # We parse both and let the neighborhood merge capture whichever EDs each district holds.
    ("2002 GENERAL ELECTION results.xls",           "xlrd",     2002, "congress",  "27thCong",                          "CD-27"),
    ("2004 GENERAL ELECTION results.xls",           "xlrd",     2004, "president", "President-VicePres",                "President"),
    ("2004 GENERAL ELECTION results.xls",           "xlrd",     2004, "congress",  "27Cong",                            "CD-27"),
    ("2004 GENERAL ELECTION results.xls",           "xlrd",     2004, "congress",  "28Cong",                            "CD-28"),
    ("2006 GENERAL ELECTION results.xls",           "xlrd",     2006, "senate",    "USSenate",                          "US Senate"),
    ("2008 GENERAL ELECTION.xlsx",                  "openpyxl", 2008, "president", "President-VicePres",                "President"),
    ("2008 GENERAL ELECTION.xlsx",                  "openpyxl", 2008, "congress",  "27Cong",                            "CD-27"),
    ("2008 GENERAL ELECTION.xlsx",                  "openpyxl", 2008, "congress",  "28Cong",                            "CD-28"),
    ("2010 GENERAL ELECTION RESULTS.xls",           "xlrd",     2010, "congress",  "27thCongress",                      "CD-27"),
    ("2010 GENERAL ELECTION RESULTS.xls",           "xlrd",     2010, "congress",  "28thCongress58Sen",                 "CD-28"),
    # 2012+: Buffalo consolidated into CD-26 after redistricting
    ("GeneralElection2012.xls",                     "xlrd",     2012, "president", "Pres-VicePres",                     "President"),
    ("GeneralElection2012.xls",                     "xlrd",     2012, "congress",  "26Congress",                        "CD-26"),
    ("2014 General Election Certified Results.xls", "xlrd",     2014, "congress",  "26Congress",                        "CD-26"),
    ("2016-General-Election-Canvass-Book-WEB.xlsx", "openpyxl", 2016, "president", "President",                         "President"),
    ("2016-General-Election-Canvass-Book-WEB.xlsx", "openpyxl", 2016, "congress",  "CD-26",                             "CD-26"),
    ("2018-General-Election-Canvass-Book-Web.xlsx", "openpyxl", 2018, "congress",  "CD-26",                             "CD-26"),
    ("2020 General Canvass Booknew.xlsx",           "openpyxl", 2020, "president", "President and Vice President",      "President"),
    ("2020 General Canvass Booknew.xlsx",           "openpyxl", 2020, "congress",  "Representative in Congress-26th",   "CD-26"),
    ("2022 General Canvass Book 1-24-23.xlsx",      "openpyxl", 2022, "congress",  "CD-26",                             "CD-26"),
    ("2024 General Canvass Booknew.xlsx",           "openpyxl", 2024, "president", "President and Vice President",      "President"),
    ("2024 General Canvass Booknew.xlsx",           "openpyxl", 2024, "congress",  "Representative in Congress-26th",   "CD-26"),
]


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    eds = gpd.read_file(GEO_DIR / "buffalo_eds.geojson")[["ed_key", "nbhdname"]]

    all_nbhd = []
    all_city = []

    for filename, engine, year, race_type, sheet_name, race_label in RACE_CONFIGS:
        fpath = RAW_DIR / filename
        if not fpath.exists():
            print(f"  MISSING: {filename}")
            continue

        try:
            df_raw = pd.read_excel(fpath, sheet_name=sheet_name,
                                   header=None, engine=engine)
        except Exception as e:
            print(f"  ERROR  {year} {race_label}: {e}")
            continue

        df = parse_federal_sheet(df_raw)
        if df is None or df.empty:
            print(f"  NO DATA  {year} {race_label}")
            continue

        dem_col, rep_col = dem_rep_cols(df)

        nbhd_df = aggregate_to_nbhd(df, eds, dem_col, rep_col,
                                     year, race_type, race_label)
        if nbhd_df is None or nbhd_df.empty:
            print(f"  NO MATCH {year} {race_label} (no ED→neighborhood joins)")
            continue

        all_nbhd.append(nbhd_df)

        # City-wide totals
        city_row = {
            "year":          year,
            "race_type":     race_type,
            "race_label":    race_label,
            "dem_candidate": dem_col or "",
            "rep_candidate": rep_col or "",
            "dem_votes":     int(nbhd_df["dem_votes"].sum()),
            "rep_votes":     int(nbhd_df["rep_votes"].sum()),
            "other_votes":   int(nbhd_df["other_votes"].sum()),
            "total_votes":   int(nbhd_df["total_votes"].sum()),
        }
        tot = city_row["total_votes"]
        city_row["dem_pct"] = round(city_row["dem_votes"] / tot * 100, 2) if tot else float("nan")
        city_row["rep_pct"] = round(city_row["rep_votes"] / tot * 100, 2) if tot else float("nan")
        all_city.append(city_row)

        print(f"  OK  {year} {race_label}: {len(nbhd_df)} nbhds  "
              f"Dem={city_row['dem_pct']:.1f}%  Rep={city_row['rep_pct']:.1f}%  "
              f"({dem_col} vs {rep_col})")

    if all_nbhd:
        out_nbhd = pd.concat(all_nbhd, ignore_index=True)
        out_nbhd.to_csv(OUT_DIR / "federal_by_nbhd.csv", index=False)
        print(f"\nSaved federal_by_nbhd.csv  ({len(out_nbhd)} rows)")

    if all_city:
        out_city = pd.DataFrame(all_city).sort_values(["year", "race_type"])
        out_city.to_csv(OUT_DIR / "federal_by_city.csv", index=False)
        print(f"Saved federal_by_city.csv  ({len(out_city)} rows)")
        print("\nCity-wide summary:")
        print(out_city[["year", "race_label", "dem_candidate", "dem_pct", "rep_pct"]].to_string(index=False))


if __name__ == "__main__":
    run()
