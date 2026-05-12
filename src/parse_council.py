"""
Parse Buffalo Common Council election results from Erie County BOE Excel files.
Outputs: data/processed/council_YYYY_TYPE.csv per election, council_all.csv combined.
"""

import re
import pandas as pd
from pathlib import Path

ROOT       = Path(__file__).parent.parent
COUNCIL_DIR = ROOT / "Elections Data Council Offeset Years"
OUT_DIR    = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WARD_CODES = {
    "delaware":   "DEL",
    "ellicott":   "ELL",
    "fillmore":   "FIL",
    "lovejoy":    "LOV",
    "masten":     "MAS",
    "niagara":    "NIA",
    "north":      "NOR",
    "south":      "SOU",
    "university": "UNI",
}

NON_CANDIDATE_PATTERNS = re.compile(r"blank|void|scatter|total", re.IGNORECASE)
ORDINAL_RE   = re.compile(r"^(\d+)(st|nd|rd|th)\s+[Dd]istrict", re.IGNORECASE)
MODERN_ED_RE = re.compile(r"^([A-Za-z]{2,4})\s+\d")

# Each entry: (year, election_type, subdir, filename, {district_name: sheet_name})
# election_type is "general" or "primary"
# Only contested primary districts are listed; uncontested districts are skipped.
ELECTION_FILES = [
    # ── 2003 ──────────────────────────────────────────────────────────────────
    # Note: 2003 files were placed in the "2023" subfolder by the user
    (2003, "general", "2023", "2003 GENERAL ELECTION results.xls", {
        "delaware":   "Del",  "ellicott":  "Ell",  "fillmore":   "Fil",
        "lovejoy":    "Lov",  "masten":    "Mas",  "niagara":    "Nia",
        "north":      "Nor",  "south":     "Sou",  "university": "Uni",
    }),
    (2003, "primary", "2023", "Democratic RESULTS.xls", {
        "ellicott":   "Ell",  "fillmore":  "Fil",  "lovejoy":    "Lov",
        "niagara":    "Nia",  "south":     "Sou",  "university": "Uni",
    }),

    # ── 2007 ──────────────────────────────────────────────────────────────────
    (2007, "general", "2007", "2007 GENERAL ELECTION.xls", {
        "delaware":   "DelCouncil",  "ellicott":  "EllCouncil",  "fillmore":   "FilCouncil",
        "lovejoy":    "LovCouncil",  "masten":    "MasCouncil",  "niagara":    "NiaCouncil",
        "north":      "NorCouncil",  "south":     "SouCouncil",  "university": "UniCouncil",
    }),
    (2007, "primary", "2007", "Democratic RESULTS.xls", {
        "delaware":  "DelCouncil",  "ellicott": "EllCouncil",
        "fillmore":  "FilCouncil",  "masten":   "MasCouncil",  "niagara": "NiaCouncil",
    }),

    # ── 2011 ──────────────────────────────────────────────────────────────────
    (2011, "general", "2011", "General2011.xls", {
        "delaware":   "DelCouncilMember",  "ellicott":  "EllCouncilMember",
        "fillmore":   "FilCouncilMember",  "lovejoy":   "LovCouncilMember",
        "masten":     "MasCouncilMember",  "niagara":   "NiaCouncilMember",
        "north":      "NorCouncilMember",  "south":     "SouCouncilMember",
        "university": "UniCouncilMember",
    }),
    # Note: 2011 primary Fillmore sheet is "FillCouncilMember" (extra l)
    (2011, "primary", "2011", "DemocraticResults.xls", {
        "fillmore":   "FillCouncilMember",  "masten":    "MasCouncilMember",
        "north":      "NorCouncilMember",   "university": "UniCouncilMember",
    }),

    # ── 2015 ──────────────────────────────────────────────────────────────────
    (2015, "general", "2015", "2015-General-Election-Canvass-Book-.xlsx", {
        "delaware":   "DelCouncilMember",  "ellicott":  "EllCouncilMember",
        "fillmore":   "FilCouncilMember",  "lovejoy":   "LovCouncilMember",
        "masten":     "MasCouncilMember",  "niagara":   "NiaCouncilMember",
        "north":      "NorCouncilMember",  "south":     "SouCouncilMember",
        "university": "UniCouncilMember",
    }),
    (2015, "primary", "2015", "2015-Primary-Democrat.xlsx", {
        "fillmore": "FilCouncilMember",  "masten": "MasCouncilMember",
    }),

    # ── 2019 ──────────────────────────────────────────────────────────────────
    (2019, "general", "2019", "2019-General-Election-Canvass-Book.xlsx", {
        "delaware":   "Delaware Council Member",   "ellicott":  "Ellicott Council Member",
        "fillmore":   "Fillmore Council Member",   "lovejoy":   "Lovejoy Council Member",
        "masten":     "Masten Council Member",     "niagara":   "Niagara Council Member",
        "north":      "North Council Member",      "south":     "South Council Member",
        "university": "University Council Member",
    }),
    (2019, "primary", "2019", "2019-Primary-Canvass-Book-Democratic.xlsx", {
        "fillmore":   "Fillmore Council Member",  "lovejoy":   "Lovejoy Council Member",
        "masten":     "Masten Council Member",    "university": "University Council Member",
    }),

    # ── 2023 ──────────────────────────────────────────────────────────────────
    (2023, "general", "2023", "2023 General Canvass Book (1).xlsx", {
        "delaware":   "Councilmember - Delaware",   "ellicott":  "Councilmember - Ellicott",
        "fillmore":   "Councilmember - Fillmore",   "lovejoy":   "Councilmember - Lovejoy",
        "masten":     "Councilmember - Masten",     "niagara":   "Councilmember - Niagara",
        "north":      "Councilmember - North",      "south":     "Councilmember - South",
        "university": "Councilmember - University",
    }),
    (2023, "primary", "2023", "2023 Primary Canvass Book - Democratic.xlsx", {
        "ellicott":   "Ellicott Council Member",  "lovejoy":   "Lovejoy Council Member",
        "masten":     "Masten Council Member",    "north":     "North Council Member",
        "university": "University Council Member",
    }),
]


def clean_header_cell(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text).replace("\n", " ")).strip()
    text = re.sub(
        r"\s+(Democrat(ic)?|Republican[\w/\s]*|Conservative|Independence|"
        r"Working Families|Green( Party)?|Reform|Write-?In|Women.s Equality|"
        r"Liberal|Right to Life|Progressive|WEP|WOR|GRE|REF|IND|CON|REP|"
        r"Save Our City)$",
        "", text, flags=re.IGNORECASE,
    ).strip()
    return text


def parse_ed_label(raw: str, current_ward: str = "") -> tuple[str, str]:
    raw = str(raw).strip()
    m = ORDINAL_RE.match(raw)
    if m:
        return current_ward, m.group(1)
    m = re.match(r"([A-Za-z]{3,4})\s+0*(\d+)", raw)
    if m:
        return m.group(1).upper(), m.group(2)
    return "", ""


def is_ward_header(row_vals: list) -> str | None:
    first = str(row_vals[0]).strip().lower()
    rest_empty = all(v == "" for v in row_vals[1:])
    if rest_empty and first in WARD_CODES:
        return WARD_CODES[first]
    return None


def is_ed_row(row_vals: list) -> bool:
    label = str(row_vals[0]).strip()
    return bool(MODERN_ED_RE.match(label) or ORDINAL_RE.match(label))


def parse_sheet(df_raw: pd.DataFrame) -> pd.DataFrame | None:
    header_row_idx = None
    for i, row in df_raw.iterrows():
        cell = str(row.iloc[0])
        if re.search(r"mayor|vote for|council", cell, re.IGNORECASE):
            header_row_idx = i
            break
    if header_row_idx is None:
        return None

    header = df_raw.iloc[header_row_idx].tolist()

    col_map: dict[int, str] = {}
    for idx, cell in enumerate(header):
        if idx == 0:
            continue
        cell_str = str(cell).strip()
        if not cell_str or cell_str.lower() == "nan":
            continue
        name = clean_header_cell(cell_str)
        if name:
            col_map[idx] = name

    if not col_map:
        return None

    candidate_cols: dict[str, list[int]] = {}
    for idx, name in col_map.items():
        candidate_cols.setdefault(name, []).append(idx)

    records = []
    current_ward = None

    for i in range(header_row_idx + 1, len(df_raw)):
        row = df_raw.iloc[i].tolist()
        row_vals = [str(v).strip() if str(v).strip() != "nan" else "" for v in row]

        if all(v == "" for v in row_vals):
            continue
        if re.match(r"^20\d{2}$|^19\d{2}$", row_vals[0]):
            continue
        if row_vals[0].lower().startswith("city of buffalo") and all(
            v == "" for v in row_vals[1:]
        ):
            continue

        ward = is_ward_header(row_vals)
        if ward:
            current_ward = ward
            continue

        if re.search(r"total", row_vals[0], re.IGNORECASE):
            continue

        if current_ward and is_ed_row(row_vals):
            ward_code, ed_num = parse_ed_label(row_vals[0], current_ward)
            if not ward_code:
                ward_code = current_ward
            record = {
                "ward":          ward_code,
                "ed_num":        ed_num,
                "ed_label":      row_vals[0],
                "shapefile_key": f"Buffalo {ward_code} {ed_num}",
            }
            for cand_name, col_indices in candidate_cols.items():
                total = 0
                for col_idx in col_indices:
                    if col_idx < len(row):
                        try:
                            v = row[col_idx]
                            total += int(float(str(v))) if str(v).strip() not in ("", "nan") else 0
                        except (ValueError, TypeError):
                            pass
                record[cand_name] = total
            records.append(record)

    return pd.DataFrame(records) if records else None


def run():
    all_results = []

    for year, etype, subdir, filename, district_sheets in ELECTION_FILES:
        fpath = COUNCIL_DIR / subdir / filename
        if not fpath.exists():
            print(f"  MISSING: {subdir}/{filename}")
            continue

        engine = "xlrd" if filename.endswith(".xls") else "openpyxl"

        year_records = []
        for district, sheet_name in district_sheets.items():
            try:
                df_raw = pd.read_excel(
                    fpath, sheet_name=sheet_name, header=None, engine=engine
                )
            except Exception as e:
                print(f"  ERROR  {year} {etype} {district} / {sheet_name}: {e}")
                continue

            df = parse_sheet(df_raw)
            if df is None or df.empty:
                print(f"  NO DATA  {year} {etype} {district} / {sheet_name}")
                continue

            df.insert(0, "district", district)
            year_records.append(df)

        if not year_records:
            print(f"  NO DATA  {year} {etype} — all districts failed")
            continue

        combined = pd.concat(year_records, ignore_index=True)
        combined.insert(0, "year",           year)
        combined.insert(1, "election_type",  etype)

        out_name = f"council_{year}_{etype}.csv"
        combined.to_csv(OUT_DIR / out_name, index=False)
        cands = [
            c for c in combined.columns
            if c not in ("year", "election_type", "district", "ward",
                         "ed_num", "ed_label", "shapefile_key")
        ]
        print(f"  OK  {out_name}: {len(combined)} EDs across "
              f"{combined['district'].nunique()} districts — {cands}")
        all_results.append(combined)

    if all_results:
        council_all = pd.concat(all_results, ignore_index=True)
        council_all.to_csv(OUT_DIR / "council_all.csv", index=False)
        print(f"\nWrote council_all.csv ({len(council_all)} rows total)")


if __name__ == "__main__":
    run()
