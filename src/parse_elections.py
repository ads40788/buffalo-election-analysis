"""
Parse Buffalo mayoral election results from Erie County BOE Excel files.
Outputs one CSV per election to data/processed/.
"""

import re
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "Elections Data"
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WARD_CODES = {
    "delaware": "DEL",
    "ellicott": "ELL",
    "fillmore": "FIL",
    "lovejoy": "LOV",
    "masten": "MAS",
    "niagara": "NIA",
    "north": "NOR",
    "south": "SOU",
    "university": "UNI",
}

# Map file → (year, election_type, sheet_name)
ELECTION_FILES = [
    ("Democratic RESULTS (1).xls",              2001, "primary",  "MAYOR"),
    ("2001 GENERAL ELECTION results.xls",        2001, "general",  "Mayor"),
    ("Democratic RESULTS.xls",                   2005, "primary",  "BuffMayor"),
    ("2005 GENERAL ELECTION.xls",                2005, "general",  "BuffMayor"),
    ("2009 DEMOCRATIC PRIMARY.xlsx",             2009, "primary",  "BuffMayor"),
    ("2009 GENERAL ELECTION.xlsx",               2009, "general",  "BuffMayor"),
    ("DemPrimary.xls",                           2013, "primary",  "BuffMayor"),
    ("2013 General Election Resultsnew.xlsx",    2013, "general",  "BuffMayor"),
    ("2017-General-Election-Web.xlsx",           2017, "general",  "BuffMayor"),
    ("2021 Democratic Primary Canvass Book.xlsx",2021, "primary",  "Buffalo Mayor"),
    ("2021 General Canvass Bookup.xlsx",         2021, "general",  "Buffalo Mayor"),
    ("2025 Democratic Primary Canvass Book.xlsx",2025, "primary",  "Buffalo Mayor"),
    ("2025 General Canvass Book.xlsx", 2025, "general", "Buffalo Mayor"),
]

# Columns that are not candidate votes
NON_CANDIDATE_PATTERNS = re.compile(
    r"blank|void|scatter|total", re.IGNORECASE
)


def clean_header_cell(text: str) -> str:
    """Extract candidate name from a verbose header cell."""
    text = re.sub(r"\s+", " ", str(text).replace("\n", " ")).strip()
    # Remove party affiliation suffix — including slash-separated combos like
    # "Republican/Strong Leadership" and multi-word parties
    text = re.sub(
        r"\s+(Democrat(ic)?|Republican[\w/\s]*|Conservative|Independence|"
        r"Working Families|Green( Party)?|Reform|Write-?In|Women.s Equality|"
        r"Liberal|Right to Life|Progressive|WEP|WOR|GRE|REF|IND|CON|REP)$",
        "", text, flags=re.IGNORECASE
    ).strip()
    return text


def normalize_ed_key(ward_code: str, ed_str: str) -> str:
    """Return 'Buffalo DEL 1' style key matching the NYS shapefile."""
    # Extract leading number, ignoring consolidated suffixes like "(2 & NOR 4)"
    m = re.match(r"(\d+)", ed_str.strip())
    if not m:
        return ""
    return f"Buffalo {ward_code} {int(m.group(1))}"


ORDINAL_RE = re.compile(r"^(\d+)(st|nd|rd|th)\s+[Dd]istrict", re.IGNORECASE)
MODERN_ED_RE = re.compile(r"^([A-Za-z]{2,4})\s+\d")


def parse_ed_label(raw: str, current_ward: str = "") -> tuple[str, str]:
    """
    Parse a row label. Handles two formats:
      Modern (2017+): 'Del 001', 'DEL 1 (2 & NOR 4)'
      Old (2001-2013): '1st District .....', '10th District .....'
    Returns (ward_code, ed_number_str).
    """
    raw = str(raw).strip()
    # Old ordinal format: "1st District", "10th District"
    m = ORDINAL_RE.match(raw)
    if m:
        return current_ward, m.group(1)
    # Modern format: "Del 001", "DEL 1 (2 & NOR 4)"
    m = re.match(r"([A-Za-z]{3,4})\s+0*(\d+)", raw)
    if m:
        return m.group(1).upper(), m.group(2)
    return "", ""


def is_ward_header(row_vals: list) -> str | None:
    """Return ward code if this row is a ward header, else None."""
    first = str(row_vals[0]).strip().lower()
    rest_empty = all(v == "" for v in row_vals[1:])
    if rest_empty and first in WARD_CODES:
        return WARD_CODES[first]
    return None


def is_ed_row(row_vals: list) -> bool:
    """True if the row looks like an election district data row."""
    label = str(row_vals[0]).strip()
    # Modern: "Del 001", "DEL 1 (2 & NOR 4)"
    if MODERN_ED_RE.match(label):
        return True
    # Old: "1st District .....", "10th District ....."
    if ORDINAL_RE.match(label):
        return True
    return False


def parse_2017_primary(filepath: Path) -> pd.DataFrame | None:
    """
    Parse the 2017 Democratic primary from the side-by-side legacy TSV.
    The 2017 data occupies cols 0–6: col0=ED label, cols 1–4=candidates,
    col5=blank/void/scatter, col6=total.
    """
    raw = pd.read_csv(
        filepath, sep="\t", header=None, dtype=str,
        encoding="latin-1", keep_default_na=False,
    )
    raw = raw.iloc[:, :7].copy()

    # Candidate names from header row (row 0, cols 1–4)
    header = raw.iloc[0].tolist()
    candidate_names = [clean_header_cell(str(header[i])) for i in range(1, 5)]

    records = []
    current_ward = None
    data_started = False

    for i in range(len(raw)):
        row = raw.iloc[i].tolist()
        row_vals = [str(v).strip() for v in row]
        col0 = row_vals[0].strip('"')

        if not data_started:
            if (col0.lower().startswith("city of buffalo")
                    and all(v == "" for v in row_vals[1:])):
                data_started = True
            continue

        if all(v == "" for v in row_vals):
            continue

        ward = is_ward_header(row_vals)
        if ward:
            current_ward = ward
            continue

        if re.search(r"total", col0, re.IGNORECASE):
            continue

        if current_ward and MODERN_ED_RE.match(col0):
            ward_code, ed_num = parse_ed_label(col0, current_ward)
            if not ward_code:
                ward_code = current_ward
            record = {
                "ward":         ward_code,
                "ed_num":       ed_num,
                "ed_label":     col0,
                "shapefile_key": f"Buffalo {ward_code} {ed_num}",
            }
            for j, cand in enumerate(candidate_names):
                val = row_vals[j + 1] if (j + 1) < len(row_vals) else ""
                try:
                    record[cand] = int(float(val)) if val else 0
                except (ValueError, TypeError):
                    record[cand] = 0
            records.append(record)

    return pd.DataFrame(records) if records else None


def parse_sheet(df_raw: pd.DataFrame) -> pd.DataFrame | None:
    """
    Parse a raw sheet DataFrame into a tidy results table.
    Returns columns: ward, ed_code, ed_label, shapefile_key, <candidate...>, total
    """
    # Find header row: the one whose first cell contains "Mayor" or "Vote"
    header_row_idx = None
    for i, row in df_raw.iterrows():
        cell = str(row.iloc[0])
        if re.search(r"mayor|vote for", cell, re.IGNORECASE):
            header_row_idx = i
            break
    if header_row_idx is None:
        return None

    header = df_raw.iloc[header_row_idx].tolist()

    # Build candidate column map: col_index → clean candidate name.
    # Skip col 0 (race title). For generals, multiple cols per candidate
    # (party lines) are summed later.
    col_map = {}   # col_idx → candidate_name
    for idx, cell in enumerate(header):
        if idx == 0:
            continue  # col 0 is the race title, not a candidate
        cell_str = str(cell).strip()
        if not cell_str or cell_str.lower() == "nan":
            continue
        name = clean_header_cell(cell_str)
        if name:
            col_map[idx] = name

    if not col_map:
        return None

    # Merge duplicate candidate names (multi-line party entries for generals)
    # We'll collect all col indices per candidate name
    candidate_cols: dict[str, list[int]] = {}
    for idx, name in col_map.items():
        candidate_cols.setdefault(name, []).append(idx)

    records = []
    current_ward = None

    for i in range(header_row_idx + 1, len(df_raw)):
        row = df_raw.iloc[i].tolist()
        row_vals = [str(v).strip() if str(v).strip() != "nan" else "" for v in row]

        # Skip blank rows
        if all(v == "" for v in row_vals):
            continue

        # Skip year row (first cell is a 4-digit year)
        if re.match(r"^20\d{2}$|^19\d{2}$", row_vals[0]):
            continue

        # Skip "City of Buffalo" banner row
        if row_vals[0].lower().startswith("city of buffalo") and all(
            v == "" for v in row_vals[1:]
        ):
            continue

        # Ward header?
        ward = is_ward_header(row_vals)
        if ward:
            current_ward = ward
            continue

        # Totals row for the ward?
        if re.search(r"total", row_vals[0], re.IGNORECASE):
            continue

        # ED data row?
        if current_ward and is_ed_row(row_vals):
            ward_code, ed_num = parse_ed_label(row_vals[0], current_ward)
            if not ward_code:
                ward_code = current_ward
            shapefile_key = f"Buffalo {ward_code} {ed_num}"
            ed_label = row_vals[0]

            record = {
                "ward": ward_code,
                "ed_num": ed_num,
                "ed_label": ed_label,
                "shapefile_key": shapefile_key,
            }

            # Sum votes per candidate across all their party-line columns
            for cand_name, col_indices in candidate_cols.items():
                total_votes = 0
                for col_idx in col_indices:
                    if col_idx < len(row):
                        try:
                            v = row[col_idx]
                            total_votes += int(float(str(v))) if str(v).strip() not in ("", "nan") else 0
                        except (ValueError, TypeError):
                            pass
                record[cand_name] = total_votes

            records.append(record)

    if not records:
        return None

    return pd.DataFrame(records)


def run():
    all_results = []

    # 2017 Democratic primary — data lives in the side-by-side legacy TSV
    legacy_file = ROOT / "BuffaloMayoralElectionData"
    if legacy_file.exists():
        df_2017 = parse_2017_primary(legacy_file)
        if df_2017 is not None and not df_2017.empty:
            df_2017.insert(0, "year", 2017)
            df_2017.insert(1, "election_type", "primary")
            df_2017.to_csv(OUT_DIR / "mayoral_2017_primary.csv", index=False)
            cands = [c for c in df_2017.columns
                     if c not in ("year", "election_type", "ward", "ed_num", "ed_label", "shapefile_key")]
            print(f"  OK  mayoral_2017_primary.csv: {len(df_2017)} EDs, candidates: {cands}")
            all_results.append(df_2017)
        else:
            print("  NO DATA: BuffaloMayoralElectionData (2017 primary)")
    else:
        print("  MISSING: BuffaloMayoralElectionData")

    for filename, year, etype, sheet_name in ELECTION_FILES:
        fpath = RAW_DIR / filename
        if not fpath.exists():
            print(f"  MISSING: {filename}")
            continue

        engine = "xlrd" if filename.endswith(".xls") else "openpyxl"
        try:
            df_raw = pd.read_excel(fpath, sheet_name=sheet_name, header=None, engine=engine)
        except Exception as e:
            print(f"  ERROR reading {filename} / {sheet_name}: {e}")
            continue

        df = parse_sheet(df_raw)
        if df is None or df.empty:
            print(f"  NO DATA: {filename} / {sheet_name}")
            continue

        df.insert(0, "year", year)
        df.insert(1, "election_type", etype)

        out_name = f"mayoral_{year}_{etype}.csv"
        df.to_csv(OUT_DIR / out_name, index=False)
        print(f"  OK  {out_name}: {len(df)} EDs, candidates: {[c for c in df.columns if c not in ('year','election_type','ward','ed_num','ed_label','shapefile_key')]}")
        all_results.append(df)

    if all_results:
        combined = pd.concat(all_results, ignore_index=True)
        combined.to_csv(OUT_DIR / "mayoral_all.csv", index=False)
        print(f"\nWrote mayoral_all.csv ({len(combined)} rows total)")


if __name__ == "__main__":
    run()
