"""Entry point for the app"""

import streamlit as st

from modules import theme  # noqa: F401 - registers the Plotly template
from modules.data_loader import ReservoirControls


class App:
    """Sets up the multipage app and the sidebar controls shared between pages."""

    def __init__(self):
        # The first Streamlit call in the app
        st.set_page_config(page_title="IND320 - Norwegian Hydropower and Power Flows", layout="wide")

        # List the pages to be included in the app
        self.home = st.Page("pages/1_home.py", title="Home", default=True)
        self.map = st.Page("pages/2_map.py", title="Map")
        self.overview = st.Page("pages/3_reservoir_overview.py", title="Data overview")
        self.analysis = st.Page("pages/4_reservoir_analysis.py", title="Seasonal analysis")
        self.forecast = st.Page("pages/5_forecast.py", title="Forecast filling")
        self.outliers = st.Page("pages/6_weather_outliers.py", title="Outliers and anomalies")
        self.correlation = st.Page("pages/7_weather_correlation.py", title="Weather vs reservoirs")
        self.flows = st.Page("pages/8_flows.py", title="Cross-border flows")
        self.currency = st.Page("pages/10_currency.py", title="Currency rates")
        self.contact = st.Page("pages/9_contact.py", title="Contact")
        self.project = st.Page("pages/11_project.py", title="Project")

        # Shared sidebar controls per page, see ReservoirControls.render
        self.controls = {
            self.map.url_path: {"window": True},
            self.overview.url_path: {"window": True, "column": True},
            self.analysis.url_path: {"area": True},
            self.forecast.url_path: {"area": True, "window": True},
            self.outliers.url_path: {"area": True},
            self.correlation.url_path: {"area": True},
        }

    def run(self) -> None:
        # Home and map on top, then the pages grouped by data source, each group with its own
        # colour (modules/theme.py). Clicking a group header folds it in or out
        page = st.navigation({
            "": [self.home, self.map],
            "Reservoirs": [self.overview, self.analysis, self.forecast],
            "Weather": [self.outliers, self.correlation],
            "Power flows": [self.flows, self.currency],
            "About": [self.contact, self.project],
        })

        # Drawn here so the choices stick when switching pages
        if page.url_path in self.controls:
            with theme.data_guard("the reservoir data from NVE"):
                ReservoirControls().render(**self.controls[page.url_path])

        # Renders whichever page is selected
        page.run()


App().run()
