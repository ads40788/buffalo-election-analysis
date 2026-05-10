# Buffalo Mayoral Elections Dashboard

Interactive Streamlit dashboard exploring neighborhood-level vote returns in Buffalo, NY mayoral races from 2001 through 2025.

**Live app:** [buffalo-election-analysis.streamlit.app](https://buffalo-election-analysis.streamlit.app) *(link active after deployment)*

## What's inside

- **Election Explorer** — choropleth maps of every mayoral race at the neighborhood or election-district level; click to compare areas
- **Coalition Shift Analysis** — tracks Byron Brown's coalition inversion between 2017 and 2021, with demographic overlays and presidential partisan context
- **Preliminary Results** — regression analysis, storyboard maps, and the "best two-of-three" coalition theory illustrated by the 2025 primary

## Data sources

- **Election returns:** Erie County Board of Elections official canvass books (2001–2025)
- **Geography:** NYS GIS election district boundaries, dissolved to Buffalo neighborhoods
- **Demographics:** ACS 2020 5-year estimates (Census Bureau)
- **Federal baseline:** Erie County BOE congressional and presidential canvass books (2002–2024)

## Running locally

```bash
pip install -r requirements.txt
streamlit run src/dashboard.py
```

The processed data files in `data/` are committed to the repo. The raw BOE Excel canvass books are not (too large); contact the Erie County Board of Elections to obtain them.

## Project structure

```
src/
  dashboard.py              # Home page (election explorer)
  pages/
    1_Compare_Elections.py  # Side-by-side election comparison
    2_Coalition_Analysis.py # Coalition shift + demographics
    3_Preliminary_Results.py # Regression results + 2025 analysis
  parse_elections.py        # Parses mayoral BOE canvass books → CSVs
  parse_federal.py          # Parses presidential/congressional data → CSVs
  spatial_join.py           # Joins election districts to neighborhoods
  fetch_demographics.py     # Downloads ACS data via Census API
data/
  geo/buffalo_eds.geojson   # Election district boundaries
  processed/                # Cleaned CSVs (election returns, demographics)
```
