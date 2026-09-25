"""Data table page."""

import pandas as pd
import streamlit as st

from data_loader import DATE_COL, VALUE_COLS, load_reservoir_data

st.title("Data Table")
st.caption("One row per data column; sparkline shows the first month of values.")

df = load_reservoir_data()

# Slice out just the first calendar month, used for the data series preview
first_month_cutoff = df[DATE_COL].min() + pd.DateOffset(months=1)
first_month_df = df[df[DATE_COL] < first_month_cutoff]

# One row per data column
display_df = pd.DataFrame(
    {
        "column": VALUE_COLS,
        "first_month": [first_month_df[c].tolist() for c in VALUE_COLS],
    }
)

# Render the table, LineChartColumn draws a sparklin of each columns first month
st.dataframe(
    display_df,
    column_config={
        "first_month": st.column_config.LineChartColumn("First month", width="medium"),
    },
    hide_index=True,
    width="stretch",
)

# Collapseble table of raw data
with st.expander("Raw data preview"):
    st.dataframe(df.head(20), width="stretch")
