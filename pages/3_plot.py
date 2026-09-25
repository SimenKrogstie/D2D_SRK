"""Page with interactive plot of imported data"""

import pandas as pd
import plotly.express as px
import streamlit as st

from data_loader import DATE_COL, VALUE_COLS, load_reservoir_data

st.title("Reservoir Data Over Time")

df = load_reservoir_data()

# Derive the month of each data point
df["_month"] = df[DATE_COL].dt.to_period("M").astype(str)
months = sorted(df["_month"].unique())


# Widget to select what column to plot, or all.
col_choice = st.selectbox("Column to plot", options=["All columns"] + VALUE_COLS)

# Widghet to select a subset of months to show
start_month, end_month = st.select_slider(
    "Month range",
    options=months,
    value=(months[0], months[0]),
    key="month_range",
)

# Restrict the data to the selected month range before plotting.
mask = (df["_month"] >= start_month) & (df["_month"] <= end_month)
plot_df = df.loc[mask]

# Which column(s) to actually draw as lines, based on the dropdown above.
show_all_columns = col_choice == "All columns"
y_cols = VALUE_COLS if show_all_columns else [col_choice]

# Function forn ormaliizing data to between 0 and 1
def normalize(series):
    value_range = series.max() - series.min()
    if value_range == 0:
        return pd.Series(1.0, index=series.index)
    return (series - series.min()) / value_range

# Normalizing if all columns is to be shown to make them comparable on one axis
# since they are on a very different scale
if show_all_columns:
    plot_data = plot_df.copy()
    plot_data[y_cols] = plot_data[y_cols].apply(normalize)
    value_label = "Normalized value (0-1)"
else:
    plot_data = plot_df
    value_label = col_choice

# Build and render the line chart
fig = px.line(
    plot_data,
    x=DATE_COL,
    y=y_cols,
    title="Reservoir data over selected period",
    labels={DATE_COL: "Date", "value": value_label, "variable": "Column"},
)
fig.update_layout(legend_title_text="Column")
st.plotly_chart(fig, width="stretch")
