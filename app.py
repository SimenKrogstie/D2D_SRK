"""Entry point for the app"""

import streamlit as st

from modules.data_loader import ReservoirControls


class App:
    """Sets up the multipage app and the controls shared by the reservoir pages."""

    def __init__(self):
        # The first Streamlit call in the app
        st.set_page_config(page_title="IND320 - Norwegian Hydropower and Power Flows", layout="wide")

        # List the pages to be included in the app
        self.home = st.Page("pages/1_home.py", title="Home", default=True)
        self.table = st.Page("pages/2_table.py", title="Reservoir table")
        self.plot = st.Page("pages/3_plot.py", title="Reservoir plot")
        self.flows = st.Page("pages/4_flows.py", title="Cross-border flows")
        self.contact = st.Page("pages/5_contact.py", title="Contact")

    def run(self) -> None:
        # Wires pages into the sidebar. st.navigation returns the page the user has selected
        page = st.navigation([self.home, self.table, self.plot, self.flows, self.contact])

        # The reservoir controls are drawn here, not on the pages, so the chosen area type
        # and interval are kept when switching between the table and the plot page
        if page.url_path in (self.table.url_path, self.plot.url_path):
            # "All columns" in the column dropdown only makes sense on the plot page
            ReservoirControls().render(allow_all_columns=page.url_path == self.plot.url_path)

        # Renders whichever page is selected
        page.run()


App().run()
