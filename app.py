# Entry point for the whole app. Only sets up page config and navigation;
# actual page content lives in the individual files under pages/.
import streamlit as st

# Must be the first Streamlit call in the whole app, and must only appear here.
st.set_page_config(page_title="IND320 - Norwegian Hydropower Reservoirs", layout="wide")

# Each page is its own .py file under pages/; st.navigation renders the
# sidebar menu automatically from this list, so no manual sidebar code is needed.
home = st.Page("pages/1_home.py", title="Home", default=True)
table = st.Page("pages/2_table.py", title="Table")
plot = st.Page("pages/3_plot.py", title="Plot")
contact = st.Page("pages/4_extra.py", title="Contact")

# Wires the pages into the sidebar and renders whichever one is selected.
pg = st.navigation([home, table, plot, contact])
pg.run()
