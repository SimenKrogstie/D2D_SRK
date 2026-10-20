"""Interactive plot of the reservoir data, one line per area"""

import pandas as pd
import plotly.express as px
import streamlit as st

from modules.data_loader import ReservoirClient, ReservoirControls
 

class ReservoirPlotPage:
    """Line plot controlled by the sidebar in app.py."""

    DATE_COL = ReservoirClient.DATE_COL
    VALUE_COLS = ReservoirClient.VALUE_COLS

    def __init__(self):
        self.controls = ReservoirControls()

    @staticmethod
    def normalize(series: pd.Series) -> pd.Series:
        """Scale to 0-1. A constant series is set to 1 to avoid dividing by 0"""
        value_range = series.max() - series.min()
        if value_range == 0:
            return pd.Series(1.0, index=series.index)
        return (series - series.min()) / value_range

    def one_column_all_areas(self, df: pd.DataFrame):
        """One line per area for the chosen column"""
        return px.line(
            df,
            x=self.DATE_COL,
            y=self.controls.value_col,
            color="area",
            title=f"{self.controls.value_col} - {ReservoirClient.AREA_TYPES[self.controls.area_type]}",
            labels={self.DATE_COL: "Date", "area": "Area"},
        )

    def all_columns_one_area(self, df: pd.DataFrame):
        """All columns, normalized, for one area"""
        area = st.selectbox("Area", options=sorted(df["area"].unique()))
        plot_data = df.loc[df["area"] == area].copy()
        plot_data[self.VALUE_COLS] = plot_data[self.VALUE_COLS].apply(self.normalize)
        return px.line(
            plot_data,
            x=self.DATE_COL,
            y=self.VALUE_COLS,
            title=f"All columns for {area} (normalized)",
            labels={self.DATE_COL: "Date", "value": "Normalized value (0-1)", "variable": "Column"},
        )

    def render(self) -> None:
        st.title("Reservoir Data Over Time")

        df = self.controls.selected_data()
        if df.empty:
            st.info("No data in the selected interval.")
            return

        # "All columns" plots one area, otherwise one column for each area
        if self.controls.value_col == ReservoirControls.ALL_COLUMNS:
            fig = self.all_columns_one_area(df)
        else:
            fig = self.one_column_all_areas(df)

        st.plotly_chart(fig, width="stretch")


# Streamlit reruns this file on every interaction
ReservoirPlotPage().render()
