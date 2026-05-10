"""
Buffalo Mayoral Elections — app entry point.
Defines navigation; page content lives in src/pages/.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from utils.analytics import inject_ga, add_footer

st.set_page_config(
    page_title="Buffalo Mayoral Elections",
    layout="wide",
    initial_sidebar_state="auto",
    page_icon="🗳️",
)
inject_ga()

pg = st.navigation([
    st.Page("pages/Home.py",                title="Dashboard",         icon="🗳️"),
    st.Page("pages/1_Compare_Elections.py", title="Compare Elections", icon="📊"),
    st.Page("pages/2_Coalition_Analysis.py",title="Coalition Analysis",icon="🔍"),
    # Preliminary Results — hidden until ready for public release
    # st.Page("pages/3_Preliminary_Results.py", title="Preliminary Results", icon="📈"),
])
pg.run()
add_footer()
