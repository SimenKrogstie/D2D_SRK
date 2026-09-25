# Page 3: an interactive plot of the imported data, with a column selector
# and a month-range slider.
import pandas as pd
import plotly.express as px
import streamlit as st

from data_loader import DATE_COL, VALUE_COLS, load_reservoir_data

st.title("Reservoir Data Over Time")

df = load_reservoir_data()

# Derive a "YYYY-MM" column so the slider below can select by month rather than
# by exact weekly date.
df["_month"] = df[DATE_COL].dt.to_period("M").astype(str)
months = sorted(df["_month"].unique())

# Widgets controlling what's plotted: a single column vs. all of them,
# and which month range to show.
col_choice = st.selectbox("Column to plot", options=["All columns"] + VALUE_COLS)

# key="month_range" keeps the selection when navigating away to another page and back.
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


def normalize(series):
    value_range = series.max() - series.min()
    if value_range == 0:
        # Constant column (e.g. capacity_twh for the national total) has no
        # shape to normalize - show it as a flat line at the top instead of NaN.
        return pd.Series(1.0, index=series.index)
    return (series - series.min()) / value_range


if show_all_columns:
    # Columns have very different scales (e.g. fill_degree is 0-1, capacity_twh
    # is ~0-90), so min-max normalize each one to make them comparable on one axis.
    plot_data = plot_df.copy()
    plot_data[y_cols] = plot_data[y_cols].apply(normalize)
    value_label = "Normalized value (0-1)"
else:
    plot_data = plot_df
    value_label = col_choice

# Build and render the line chart, with a title, axis labels, and legend.
fig = px.line(
    plot_data,
    x=DATE_COL,
    y=y_cols,
    title="Reservoir data over selected period",
    labels={DATE_COL: "Date", "value": value_label, "variable": "Column"},
)
fig.update_layout(legend_title_text="Column")
st.plotly_chart(fig, width="stretch")
