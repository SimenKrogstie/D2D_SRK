# Page 2: shows the imported data as a table, one row per column, with a
# sparkline of each column's first month of values.
import pandas as pd
import streamlit as st

from data_loader import DATE_COL, VALUE_COLS, load_reservoir_data

st.title("Data Table")
st.caption("One row per data column; sparkline shows the first month of values.")

df = load_reservoir_data()

# Slice out just the first calendar month, used for the sparkline previews below.
first_month_cutoff = df[DATE_COL].min() + pd.DateOffset(months=1)
first_month_df = df[df[DATE_COL] < first_month_cutoff]

# One row per data column (a transpose of the usual orientation), so
# LineChartColumn can draw a sparkline of each column's first-month values.
display_df = pd.DataFrame(
    {
        "column": VALUE_COLS,
        "first_month": [first_month_df[c].tolist() for c in VALUE_COLS],
    }
)

# Render the table itself, using LineChartColumn to turn each row's list
# of values into a small sparkline chart.
st.dataframe(
    display_df,
    column_config={
        "first_month": st.column_config.LineChartColumn("First month", width="medium"),
    },
    hide_index=True,
    width="stretch",
)

# Collapsed by default; lets the user peek at the underlying (untransposed) data.
with st.expander("Raw data preview"):
    st.dataframe(df.head(20), width="stretch")
