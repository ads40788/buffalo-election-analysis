"""
Scrape Buffalo Common Council roll-call votes from IQM2 (buffalony.iqm2.com).

Pipeline:
  1. Fetch the meeting calendar for each year to collect meeting IDs.
  2. For each meeting, fetch the detail page to extract the MinutesID (Summary PDF ID).
  3. Download and parse each Summary PDF for RESULT/MOVER/SECONDER/AYES/NAYS data.
  4. Write data/processed/council_votes.csv.

Notes:
  - Most routine items only show RESULT (APPROVED/REFERRED/etc.) without
    a per-member breakdown. Member-level Aye/Nay data appears only on
    motioned/contested votes. Both types of records are written.
  - Rate-limited to ~1 req/sec to be polite to the public portal.
"""

import re
import time
import io
import requests
import pdfplumber
import pandas as pd
from bs4 import BeautifulSoup
from pathlib import Path

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "data" / "processed"
PDF_DIR = ROOT / "data" / "council_vote_pdfs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://buffalony.iqm2.com/Citizens"
BOARD_ID  = 1000   # Common Council
YEARS     = list(range(2020, 2027))
SLEEP_SEC = 1.0

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Buffalo-Election-Research/1.0"})


# ── IQM2 fetchers ──────────────────────────────────────────────────────────────

def fetch_meeting_ids(year: int) -> list[int]:
    """Return all Common Council meeting IDs for a given year."""
    url = (f"{BASE}/Calendar.aspx"
           f"?From=1/1/{year}&To=12/31/{year}&BoardID={BOARD_ID}")
    resp = SESSION.get(url, timeout=30)
    soup = BeautifulSoup(resp.text, "html.parser")
    ids = []
    for a in soup.find_all("a", href=True):
        m = re.search(r"Detail_Meeting\.aspx\?ID=(\d+)", a["href"])
        if m:
            ids.append(int(m.group(1)))
    return sorted(set(ids))


def fetch_minutes_id(meeting_id: int) -> int | None:
    """
    Fetch the meeting detail page and extract the MinutesID,
    which is the ID needed to download the Summary PDF.
    """
    url = f"{BASE}/Detail_Meeting.aspx?ID={meeting_id}"
    resp = SESSION.get(url, timeout=30)
    soup = BeautifulSoup(resp.text, "html.parser")

    # The Summary PDF link: FileOpen.aspx?Type=15&ID=XXXX
    for a in soup.find_all("a", href=True):
        m = re.search(r"FileOpen\.aspx\?Type=15&ID=(\d+)", a["href"])
        if m:
            return int(m.group(1))

    # Fallback: look for MinutesID= in any link on the page
    for a in soup.find_all("a", href=True):
        m = re.search(r"MinutesID=(\d+)", a["href"])
        if m:
            return int(m.group(1))

    return None


def fetch_meeting_date(meeting_id: int, soup: BeautifulSoup) -> str:
    """Extract meeting date string from already-fetched detail page."""
    # IQM2 puts the date in the page title or a header element
    title = soup.find("title")
    if title:
        m = re.search(r"(\w+ \d+, \d{4})", title.get_text())
        if m:
            return m.group(1)
    # Fallback: look for a date-like string near the top
    for tag in soup.find_all(["h1", "h2", "h3", "span", "div"]):
        text = tag.get_text(strip=True)
        m = re.search(r"\b(\w+ \d{1,2},\s*\d{4})\b", text)
        if m:
            return m.group(1)
    return ""


def fetch_meeting_detail(meeting_id: int) -> tuple[int | None, str]:
    """Return (minutes_id, meeting_date_str) for a meeting."""
    url = f"{BASE}/Detail_Meeting.aspx?ID={meeting_id}"
    try:
        resp = SESSION.get(url, timeout=30)
    except requests.RequestException:
        return None, ""
    soup = BeautifulSoup(resp.text, "html.parser")

    minutes_id = None
    for a in soup.find_all("a", href=True):
        m = re.search(r"FileOpen\.aspx\?Type=15&ID=(\d+)", a["href"])
        if m:
            minutes_id = int(m.group(1))
            break
    if minutes_id is None:
        for a in soup.find_all("a", href=True):
            m = re.search(r"MinutesID=(\d+)", a["href"])
            if m:
                minutes_id = int(m.group(1))
                break

    date_str = fetch_meeting_date(meeting_id, soup)
    return minutes_id, date_str


def download_summary_pdf(minutes_id: int) -> bytes | None:
    """Download the Summary PDF for a given MinutesID."""
    cache_path = PDF_DIR / f"summary_{minutes_id}.pdf"
    if cache_path.exists():
        return cache_path.read_bytes()

    url = f"{BASE}/FileOpen.aspx?Type=15&ID={minutes_id}&Inline=True"
    try:
        resp = SESSION.get(url, timeout=60)
    except requests.RequestException:
        return None
    if resp.status_code != 200 or b"%PDF" not in resp.content[:10]:
        return None

    cache_path.write_bytes(resp.content)
    return resp.content


# ── PDF parser ─────────────────────────────────────────────────────────────────

MEMBER_LAST_NAMES = [
    "Bollman", "Everhart", "Feroleto", "Golombek", "Halton-Pope",
    "Halton Pope", "Nowakowski", "Rivera", "Scanlon", "Wyatt",
    # Earlier members
    "Pridgen", "Fontana", "Franczyk", "Herbert", "Wingo",
    "LoCurto", "Kearns", "Russell", "Golombek Jr",
    "Smith", "Ferguson", "Grant", "Howard", "Hornig",
]


def parse_summary_pdf(pdf_bytes: bytes, meeting_id: int,
                      minutes_id: int, date_str: str) -> list[dict]:
    """
    Parse a Summary PDF into a list of vote records.
    Each record has: meeting_id, minutes_id, date, item_title, result,
    mover, seconder, ayes (list → semicolon-joined), nays (list → semicolon-joined),
    ayes_count, nays_count.
    """
    records = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
    except Exception:
        return records

    # Split on agenda item blocks. Items tend to start with a line that is
    # all-caps or a numbered heading, followed by RESULT: on a nearby line.
    # We look for "RESULT:" as the anchor and walk backward for the title.
    blocks = re.split(r"\n(?=\S)", full_text)   # split on lines with non-whitespace start

    # Simpler approach: find all RESULT: occurrences and extract context
    item_re = re.compile(
        r"(.{0,300}?)\s*RESULT:\s*([A-Z &/\[\]]+)"
        r"(?:.*?MOVER:\s*([^\n]+))?"
        r"(?:.*?SECONDER:\s*([^\n]+))?"
        r"(?:.*?AYES?:\s*([^\n]+))?"
        r"(?:.*?NAYS?:\s*([^\n]+))?",
        re.DOTALL,
    )

    # Use a line-by-line state machine instead — more reliable
    lines = full_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line.upper().startswith("RESULT:"):
            i += 1
            continue

        result_val = re.sub(r"^RESULT:\s*", "", line, flags=re.IGNORECASE).strip()

        # Walk back to find item title (last non-empty line before RESULT)
        title_lines = []
        j = i - 1
        while j >= 0 and len(title_lines) < 4:
            prev = lines[j].strip()
            if prev and not re.match(r"^\d+\s*$", prev):
                title_lines.insert(0, prev)
            j -= 1
        title = " ".join(title_lines[-2:]).strip()  # last 2 lines as title

        # Walk forward for MOVER / SECONDER / AYES / NAYS
        mover = seconder = ayes_raw = nays_raw = ""
        k = i + 1
        while k < len(lines) and k < i + 10:
            nxt = lines[k].strip()
            if re.match(r"^MOVER:", nxt, re.I):
                mover = re.sub(r"^MOVER:\s*", "", nxt, flags=re.I).strip()
            elif re.match(r"^SECONDER:", nxt, re.I):
                seconder = re.sub(r"^SECONDER:\s*", "", nxt, flags=re.I).strip()
            elif re.match(r"^AYES?:", nxt, re.I):
                ayes_raw = re.sub(r"^AYES?:\s*", "", nxt, flags=re.I).strip()
            elif re.match(r"^NAYS?:", nxt, re.I):
                nays_raw = re.sub(r"^NAYS?:\s*", "", nxt, flags=re.I).strip()
            elif re.match(r"^RESULT:", nxt, re.I):
                break  # next item
            k += 1

        def split_names(raw: str) -> list[str]:
            if not raw:
                return []
            # Remove bracketed notes like [UNANIMOUS]
            raw = re.sub(r"\[.*?\]", "", raw).strip()
            return [n.strip() for n in re.split(r"[,;]", raw) if n.strip()]

        ayes_list = split_names(ayes_raw)
        nays_list = split_names(nays_raw)

        records.append({
            "meeting_id":  meeting_id,
            "minutes_id":  minutes_id,
            "date":        date_str,
            "item_title":  title,
            "result":      result_val,
            "mover":       mover,
            "seconder":    seconder,
            "ayes":        "; ".join(ayes_list),
            "nays":        "; ".join(nays_list),
            "ayes_count":  len(ayes_list),
            "nays_count":  len(nays_list),
        })
        i = k  # jump past the block we just parsed

    return records


# ── Main ───────────────────────────────────────────────────────────────────────

def run(years: list[int] = YEARS) -> None:
    all_records: list[dict] = []
    meeting_index: list[dict] = []

    for year in years:
        print(f"\n=== {year} ===")
        try:
            meeting_ids = fetch_meeting_ids(year)
        except Exception as e:
            print(f"  ERROR fetching calendar for {year}: {e}")
            continue
        print(f"  Found {len(meeting_ids)} meetings: {meeting_ids[:5]}{'...' if len(meeting_ids) > 5 else ''}")

        for mid in meeting_ids:
            time.sleep(SLEEP_SEC)
            try:
                minutes_id, date_str = fetch_meeting_detail(mid)
            except Exception as e:
                print(f"  ERROR detail MID={mid}: {e}")
                continue

            if not minutes_id:
                print(f"  SKIP  MID={mid} — no summary PDF found")
                continue

            meeting_index.append({
                "meeting_id": mid,
                "minutes_id": minutes_id,
                "date":       date_str,
                "year":       year,
            })

            time.sleep(SLEEP_SEC)
            try:
                pdf_bytes = download_summary_pdf(minutes_id)
            except Exception as e:
                print(f"  ERROR PDF  MID={mid} MinutesID={minutes_id}: {e}")
                continue

            if not pdf_bytes:
                print(f"  SKIP  MID={mid} — PDF download failed")
                continue

            records = parse_summary_pdf(pdf_bytes, mid, minutes_id, date_str)
            all_records.extend(records)
            print(f"  OK    MID={mid} date={date_str or '?'} "
                  f"MinutesID={minutes_id} → {len(records)} items")

    # Write meeting index
    pd.DataFrame(meeting_index).to_csv(
        OUT_DIR / "council_meeting_index.csv", index=False
    )

    # Write vote records
    if all_records:
        df = pd.DataFrame(all_records)
        df.to_csv(OUT_DIR / "council_votes.csv", index=False)
        contested = df[df["ayes_count"] > 0]
        print(f"\nWrote council_votes.csv: {len(df)} item records, "
              f"{len(contested)} with member-level vote data")
    else:
        print("\nNo vote records collected.")


if __name__ == "__main__":
    run()
