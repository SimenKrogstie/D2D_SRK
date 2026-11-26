"""Overview of the Magasinstatistikk data: a sparkline table and an interactive plot."""

import pandas as pd
import plotly.express as px
import streamlit as st

from modules import theme
from modules.data_loader import ReservoirClient, ReservoirControls


class ReservoirOverviewPage:
    """Plot and table tabs, controlled by the sidebar in app.py."""

    DATE_COL = ReservoirClient.DATE_COL
    VALUE_COLS = ReservoirClient.VALUE_COLS

    def __init__(self):
        self.controls = ReservoirControls()

    def summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """One row per area, with the full series of the chosen column for the sparkline."""
        value_col = self.controls.value_col
        rows = []
        for (area_number, area), group in df.groupby(["area_number", "area"]):
            # Sorted so the sparkline reads left to right
            series = group.sort_values(self.DATE_COL)[value_col]
            rows.append(
                {
                    "area": area,
                    "area_number": area_number,
                    "series": series.tolist(),
                    "latest": series.iloc[-1],
                    "min": series.min(),
                    "max": series.max(),
                }
            )
        return pd.DataFrame(rows)

    def render_table(self, df: pd.DataFrame) -> None:
        # LineChartColumn draws a sparkline per area
        st.dataframe(
            self.summary(df),
            column_config={
                "area": "Area",
                "area_number": "Area number",
                "series": st.column_config.LineChartColumn(self.controls.value_col, width="large"),
                "latest": st.column_config.NumberColumn("Latest", format="%.3f"),
                "min": st.column_config.NumberColumn("Min", format="%.3f"),
                "max": st.column_config.NumberColumn("Max", format="%.3f"),
            },
            hide_index=True,
            width="stretch",
        )
        # Collapsible table of the downloaded data
        with st.expander("Downloaded data"):
            st.dataframe(df, width="stretch", hide_index=True)

    @staticmethod
    def normalize(series: pd.Series) -> pd.Series:
        """Scale to 0-1. A constant series is set to 1 to avoid dividing by 0"""
        value_range = series.max() - series.min()
        if value_range == 0:
            return pd.Series(1.0, index=series.index)
        return (series - series.min()) / value_range

    def render_plot(self, df: pd.DataFrame) -> None:
        """One line per area for the chosen column, or all columns normalised for one area."""
        all_columns = st.toggle("All columns for one area (normalised)")
        if all_columns:
            area = st.selectbox("Area", options=sorted(df["area"].unique()))
            plot_data = df.loc[df["area"] == area].copy()
            plot_data[self.VALUE_COLS] = plot_data[self.VALUE_COLS].apply(self.normalize)
            fig = px.line(
                plot_data,
                x=self.DATE_COL,
                y=self.VALUE_COLS,
                title=f"All columns for {area} (normalised)",
                labels={self.DATE_COL: "Date", "value": "Normalised value (0-1)", "variable": "Column"},
            )
        else:
            fig = px.line(
                df,
                x=self.DATE_COL,
                y=self.controls.value_col,
                color="area",
                title=f"{self.controls.value_col} - {ReservoirClient.AREA_TYPES[self.controls.area_type]}",
                labels={self.DATE_COL: "Date", "area": "Area"},
            )
        fig.update_layout(hovermode="x unified")
        theme.show(fig)

    def render(self) -> None:
        header = theme.page_header("Reservoir Data Overview", "Reservoirs",
                                   "The Magasinstatistikk data for the chosen area type and time window, as an "
                                   "interactive plot and a table with a sparkline per area.")
        start_month, end_month = self.controls.month_range
        header.caption(
            f"{ReservoirClient.AREA_TYPES[self.controls.area_type]}, {start_month} to {end_month}. "
            f"Area type, time window and column are chosen in the sidebar."
        )

        # Downloads the interval, or reuses the cached one
        with theme.data_guard("the reservoir data from NVE"):
            df = self.controls.selected_data()
        if df.empty:
            st.info("No data in the selected interval.")
            return

        # The plot first, so it is the tab shown when the page opens
        plot_tab, table_tab = st.tabs(["Plot", "Table"])
        with plot_tab:
            self.render_plot(df)
        with table_tab:
            self.render_table(df)

        # Collapsible documentation of where the data comes from
        with st.expander("Data source"):
            st.markdown(
                """
Data is downloaded from the [NVE Magasinstatistikk API](https://biapi.nve.no/magasinstatistikk/swagger/index.html)
(`HentOffentligData`). The sidebar time window controls the download: each new interval makes a
new request to the API, and only the chosen interval is kept (the endpoint has no date
parameters, so the interval is cut out right after downloading). Each interval is cached for
an hour. Each date is the last day (Sunday) of the ISO week the statistics describe.
"""
            )


# Streamlit reruns this file on every interaction
ReservoirOverviewPage().render()
