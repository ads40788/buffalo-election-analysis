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
