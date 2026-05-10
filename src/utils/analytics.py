import streamlit as st


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
