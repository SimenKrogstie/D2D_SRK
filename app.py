"""Entry point for the app"""

import streamlit as st

# The first Streamlit call in the app
st.set_page_config(page_title="IND320 - Norwegian Hydropower Reservoirs", layout="wide")

# List the pages to be included in the app
home = st.Page("pages/1_home.py", title="Home", default=True)
table = st.Page("pages/2_table.py", title="Table")
plot = st.Page("pages/3_plot.py", title="Plot")
contact = st.Page("pages/4_extra.py", title="Contact")

# Wires pages into the sidebar and renders whichever one is selected.
pg = st.navigation([home, table, plot, contact])
pg.run()
