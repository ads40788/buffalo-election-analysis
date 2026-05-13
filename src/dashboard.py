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

# Global mobile styles — apply to every page
st.markdown("""
<style>
/* Make the collapsed-sidebar toggle button obvious on mobile */
@media (max-width: 768px) {
    div[data-testid="collapsedControl"] {
        background-color: #1d4ed8 !important;
        border-radius: 0 8px 8px 0 !important;
        box-shadow: 2px 4px 10px rgba(0,0,0,0.25) !important;
        padding: 0.65rem 0.55rem !important;
    }
    div[data-testid="collapsedControl"] svg {
        fill: white !important;
    }
    .mobile-nav-hint { display: flex !important; }
}
.mobile-nav-hint { display: none; }
</style>
<div class="mobile-nav-hint" style="align-items:center;gap:0.4rem;
     background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;
     padding:0.35rem 0.8rem;font-size:0.78rem;color:#1e40af;margin-bottom:0.5rem;">
  &#9776;&nbsp; Tap the blue arrow on the left to open controls &amp; switch pages
</div>
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
