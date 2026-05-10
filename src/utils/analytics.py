import streamlit as st


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

    st.html(f"""
    <script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{ga_id}', {{
        page_title: document.title,
        page_location: window.location.href
      }});
    </script>
    """)
