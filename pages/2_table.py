"""Data table page, one row per area of the chosen area type."""

import pandas as pd
import streamlit as st

from modules.data_loader import ReservoirClient, ReservoirControls


class ReservoirTablePage:
    """Table with one sparkline per area, controlled by the sidebar in app.py."""

    def __init__(self):
        self.controls = ReservoirControls()

    def summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """One row per area, with the full series of the chosen column for the sparkline."""
        value_col = self.controls.value_col
        rows = []
        for (area_number, area), group in df.groupby(["area_number", "area"]):
            # Sorted so the sparkline reads left to right
            series = group.sort_values(ReservoirClient.DATE_COL)[value_col]
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

    def render(self) -> None:
        start_month, end_month = self.controls.month_range
        value_col = self.controls.value_col

        st.title("Reservoir Table")
        st.caption(
            f"{ReservoirClient.AREA_TYPES[self.controls.area_type]}, {start_month} to {end_month}. "
            f"The sparkline shows `{value_col}` for each area over the downloaded interval."
        )

        # Downloads the interval, or reuses the cached one
        df = self.controls.selected_data()
        if df.empty:
            st.info("No data in the selected interval.")
            return

        # LineChartColumn draws a sparkline per area
        st.dataframe(
            self.summary(df),
            column_config={
                "area": "Area",
                "area_number": "Area number",
                "series": st.column_config.LineChartColumn(value_col, width="large"),
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

        # Collapsible documentation of where the data comes from
        with st.expander("Data source"):
            st.markdown(
                """
Data is downloaded from the [NVE Magasinstatistikk API](https://biapi.nve.no/magasinstatistikk/swagger/index.html)
(`HentOffentligData`). The sidebar slider controls the download: each new interval makes a
new request to the API, and only the chosen interval is kept (the endpoint has no date
parameters, so the interval is cut out right after downloading). Each interval is cached for
an hour. Each date is the last day of the ISO week the statistics describe.
"""
            )


# Streamlit reruns this file on every interaction
ReservoirTablePage().render()
