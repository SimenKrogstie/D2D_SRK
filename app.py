import streamlit as st

st.set_page_config(page_title="IND320 - Reservoirs", page_icon="\U0001F4A7", layout="wide")

home = st.Page("pages/1_home.py", title="Home", default=True)
table = st.Page("pages/2_table.py", title="Table")
plot = st.Page("pages/3_plot.py", title="Plot")
extra = st.Page("pages/4_extra.py", title="Extra")

pg = st.navigation([home, table, plot, extra])
pg.run()
