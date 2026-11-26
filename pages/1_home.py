"""Home page of the app: a short description and one coloured link box per page."""

import streamlit as st

from modules import theme

# Short introduction to the data sources as the page description
theme.page_header(
    "Norwegian Hydropower Reservoirs and Power Flows", "Overview",
    """
This app explores the Norwegian Water Resources and Energy Directorate's hydropower reservoir
statistics ([NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/)),
hourly weather (ERA5 reanalysis) from [open-meteo](https://open-meteo.com/), exchange rates from
[Norges Bank](https://www.norges-bank.no/en/topics/Statistics/open-data/), and the cross-border
power flows between Norway and its neighbours from the
[ENTSO-E Transparency Platform](https://transparency.entsoe.eu/).
Pick an area on the **Map** or in the sidebar, and the other pages use the same area and time window.
""",
)

# One row per group, in the same order as the sidebar
GROUPS = {
    "Reservoirs": [
        ("pages/3_reservoir_overview.py", "Data overview", "Plot and sparkline table of Magasinstatistikk"),
        ("pages/4_reservoir_analysis.py", "Seasonal analysis", "STL decomposition and spectrogram"),
        ("pages/5_forecast.py", "Forecast", "SARIMAX forecast of the filling degree"),
    ],
    "Weather": [
        ("pages/6_weather_outliers.py", "Outliers & anomalies", "SPC and LOF for any weather variable"),
        ("pages/7_weather_correlation.py", "Weather vs. reservoirs", "Sliding window correlation with lag"),
    ],
    "Power flows": [
        ("pages/8_flows.py", "Cross-border flows", "Yearly totals and hourly flows per connection"),
        ("pages/10_currency.py", "Currency rates", "EUR and USD against NOK from Norges Bank"),
    ],
    "About": [
        ("pages/9_contact.py", "Contact", "Where to find me"),
        ("pages/11_project.py", "Project", "The course project, data and pipeline"),
    ],
}


def card_key(group: str) -> str:
    """Container key, which Streamlit also adds as the CSS class st-key-<key>."""
    return "card_" + group.lower().replace(" ", "_")


# Each card is a dark box with the title in the group colour and a short description below.
# The border takes the group colour on hover
rules = [
    f"""[class*="st-key-{card_key(group)}"] a[data-testid="stPageLink-NavLink"] p {{ color: {color}; }}
[class*="st-key-{card_key(group)}"]:hover {{ border-color: {color}; }}"""
    for group, color in ((g, theme.GROUP_COLORS[g]) for g in GROUPS)
]
st.markdown(
    f"""
<style>
[class*="st-key-card_"] {{
    background: {theme.SECONDARY_BACKGROUND}; border: 1px solid {theme.GRID}; border-radius: 0.6rem;
    padding: 0.8rem 1rem; min-height: 6.5rem; gap: 0.2rem; transition: border-color 0.15s, transform 0.15s;
}}
[class*="st-key-card_"]:hover {{ transform: translateY(-2px); }}
[class*="st-key-card_"] a[data-testid="stPageLink-NavLink"] {{ padding: 0; background: transparent; }}
[class*="st-key-card_"] a[data-testid="stPageLink-NavLink"]:hover {{ background: transparent; }}
[class*="st-key-card_"] a[data-testid="stPageLink-NavLink"] p {{ font-weight: 700; font-size: 1.15rem; }}
[class*="st-key-card_"] a[data-testid="stPageLink-NavLink"]:hover p {{ text-decoration: underline; }}
{chr(10).join(rules)}
</style>
""",
    unsafe_allow_html=True,
)

for group, pages in GROUPS.items():
    columns = st.columns(3)
    for i, (path, title, text) in enumerate(pages):
        with columns[i].container(key=f"{card_key(group)}_{i}"):
            st.page_link(path, label=title, width="stretch")
            st.caption(text)
