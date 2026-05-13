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

# Try to make the collapsed-sidebar toggle more visible on mobile.
# Streamlit changes data-testid values between versions, so we cast a wide net.
st.markdown("""
<style>
@media (max-width: 768px) {
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="stSidebarNavLink"] ~ button {
        background-color: #1d4ed8 !important;
        border-radius: 0 8px 8px 0 !important;
        box-shadow: 2px 4px 10px rgba(0,0,0,0.25) !important;
    }
    [data-testid="collapsedControl"] svg,
    [data-testid="stSidebarCollapsedControl"] svg {
        fill: white !important;
    }
}
</style>
""", unsafe_allow_html=True)

pg = st.navigation([
    st.Page("pages/Home.py",                title="Dashboard",         icon="🗳️"),
    st.Page("pages/1_Compare_Elections.py", title="Compare Elections", icon="📊"),
    st.Page("pages/2_Coalition_Analysis.py",title="Coalition Analysis",icon="🔍"),
    st.Page("pages/3_Council_Districts.py", title="Council Districts",  icon="🏛️"),
    # Preliminary Results — hidden until ready for public release
    # st.Page("pages/4_Preliminary_Results.py", title="Preliminary Results", icon="📈"),
])
pg.run()
add_footer()
