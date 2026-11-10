"""Entry point for the app"""

import streamlit as st

from modules.data_loader import ReservoirControls


class App:
    """Sets up the multipage app and the controls shared by the reservoir and weather pages."""

    def __init__(self):
        # The first Streamlit call in the app
        st.set_page_config(page_title="IND320 - Norwegian Hydropower and Power Flows", layout="wide")

        # List the pages to be included in the app
        self.home = st.Page("pages/1_home.py", title="Home", default=True)
        self.table = st.Page("pages/2_table.py", title="Reservoir table")
        self.plot = st.Page("pages/3_plot.py", title="Reservoir plot")
        self.analysis = st.Page("pages/4_reservoir_analysis.py", title="Reservoir analysis")
        self.weather = st.Page("pages/5_weather_outliers.py", title="Outliers and anomalies")
        self.flows = st.Page("pages/6_flows.py", title="Cross-border flows")
        self.contact = st.Page("pages/7_contact.py", title="Contact")

    def run(self) -> None:
        # Pages grouped by topic in the sidebar
        page = st.navigation({
            "": [self.home],
            "Reservoirs": [self.table, self.plot, self.analysis],
            "Weather": [self.weather],
            "Power flows": [self.flows],
            "About": [self.contact],
        })

        # Drawn here so the choices stick when switching pages
        if page.url_path in (self.table.url_path, self.plot.url_path):
            # "All columns" in the column dropdown only makes sense on the plot page
            ReservoirControls().render(allow_all_columns=page.url_path == self.plot.url_path)
        elif page.url_path in (self.analysis.url_path, self.weather.url_path):
            # One area at a time on the analysis and weather pages
            ReservoirControls().render(single_area=True)

        # Renders whichever page is selected
        page.run()


App().run()
