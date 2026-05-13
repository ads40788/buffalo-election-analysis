import streamlit as st
import streamlit.components.v1 as components


def add_footer() -> None:
    st.markdown(
        """
        <div style="margin-top:3rem;padding-top:1rem;border-top:1px solid #e8e8e8;
                    text-align:center;color:#999;font-size:0.78rem;">
            Made by <a href="https://antoniosirianni.com" target="_blank"
                       style="color:#999;text-decoration:none;border-bottom:1px solid #ccc;">Tony</a>
            &nbsp;·&nbsp;
            <a href="https://github.com/ads40788/" target="_blank"
               style="color:#999;text-decoration:none;border-bottom:1px solid #ccc;">GitHub</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mobile_hint() -> None:
    """Render a mobile-only banner prompting users to open the sidebar.
    Call once near the top of each page's main content."""
    st.markdown(
        """
        <div id="mob-hint" style="display:none;">
          &#9776;&ensp;Tap the <strong>&rsaquo;</strong> arrow in the top-left
          to open controls &amp; switch pages
        </div>
        <style>
        @media (max-width: 768px) {
            #mob-hint {
                display: flex !important;
                align-items: center;
                background: #eff6ff;
                border: 1px solid #bfdbfe;
                border-radius: 6px;
                padding: 0.35rem 0.85rem;
                font-size: 0.8rem;
                color: #1e40af;
                margin-bottom: 0.6rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_ga() -> None:
    """Inject GA4 tracking snippet if a measurement ID is configured."""
    try:
        ga_id = st.secrets.get("GA_MEASUREMENT_ID", "")
    except Exception:
        ga_id = ""

    if not ga_id:
        return

    # st.html() runs in a sandboxed srcdoc iframe — window.location.href resolves
    # to about:srcdoc and GA4 rejects the hit. components.html(height=0) uses a
    # proper hidden iframe where gtag.js fires correctly.
    components.html(f"""
    <script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{ga_id}');
    </script>
    """, height=0)
