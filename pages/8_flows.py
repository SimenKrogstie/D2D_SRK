"""Cross-border power flows to and from Norway, read from MongoDB."""

import calendar
from typing import ClassVar

import pandas as pd
import plotly.express as px
import streamlit as st

from modules import theme
from modules.data_flow import FlowData


class FlowsPage:
    """Yearly pie chart on the left, hourly line plot for chosen months on the right."""

    # Month numbers (stored in MongoDB) mapped to short names
    MONTH_NAMES: ClassVar[dict[int, str]] = {m: calendar.month_abbr[m] for m in range(1, 13)}

    def __init__(self):
        self.data: FlowData  # Cached MongoDB queries, connected in render()

    def render_pie(self) -> tuple[str, int]:
        """Left column: connection and year selection, pie chart of the yearly totals per direction."""
        st.subheader("Yearly total per direction")
        connection = st.radio("Connection", options=self.data.connections(), horizontal=True)
        if connection is None: 
            st.stop()   # Never happens, render() checks for connections first
        years = self.data.years(connection)
        # Default the recent complete year
        year = st.selectbox("Year", options=years, index=max(len(years) - 2, 0))

        with theme.data_guard("the flows from MongoDB"):
            year_df = self.data.flows(connection, year)
        # Sum hourly energy, shown in GWh
        totals = year_df.groupby("direction", as_index=False)["energy_mwh"].sum()
        totals["energy_gwh"] = totals["energy_mwh"] / 1000

        fig = px.pie(totals, names="direction", values="energy_gwh", title=f"{connection}, {year} (GWh)")
        fig.update_traces(textinfo="percent+value")
        theme.show(fig)
        return connection, year

    @staticmethod
    def break_gaps(df: pd.DataFrame) -> pd.DataFrame:
        """An empty row after each gap of more than an hour, per direction.

        Plotly draws a straight line across the months that aren't selected otherwise; a missing
        value breaks the line instead.
        """
        frames = []
        for direction, group in df.sort_values("time").groupby("direction", sort=False):
            gap_starts = group["time"].diff() > pd.Timedelta(hours=1)
            breaks = pd.DataFrame({"direction": direction,
                                   "time": group.loc[gap_starts, "time"] - pd.Timedelta(minutes=30),
                                   "flow_mw": float("nan")})
            frames.append(pd.concat([group[["direction", "time", "flow_mw"]], breaks]).sort_values("time"))
        return pd.concat(frames, ignore_index=True)

    def render_line(self, connection: str, year: int) -> None:
        """Right column: month pills, hourly line plot per direction."""
        st.subheader("Hourly flow for chosen months")
        # Multi-select, January by default
        months = st.pills(
            "Months",
            options=list(self.MONTH_NAMES),
            format_func=lambda m: self.MONTH_NAMES[m],
            selection_mode="multi",
            default=[1],
        )
        if not months:
            st.info("Select one or more months.")
            return

        # Sorted tuple, so the same selectriuon hits the same cache entry
        with theme.data_guard("the flows from MongoDB"):
            month_df = self.data.flows(connection, year, tuple(sorted(months)))
        if month_df.empty:
            st.info("No data for the selected months.")
            return

        fig = px.line(
            self.break_gaps(month_df),
            x="time",
            y="flow_mw",
            color="direction",
            title=f"{connection}, {year}",
            labels={"time": "Time (UTC)", "flow_mw": "Flow (MW)", "direction": "Direction"},
        )
        fig.update_layout(hovermode="x unified")
        theme.show(fig)

    @staticmethod
    def render_source() -> None:
        """Documentation of the data shown on the page."""
        with st.expander("Data source"):
            st.markdown(
                """
- **Source:** [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/),
  *Cross-Border Physical Flows* (document type A11), queried through the
  [ENTSO-E REST API](https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html).
- **Connections:** the bidding-zone borders between Norway (NO1-NO5) and its neighbours,
  each in both directions. Borders where ENTSO-E has no data are left out.
- **Pipeline:** the data for the last two years is downloaded in
  `notebooks/assignment_2.ipynb`, stored in a local Cassandra database with Spark, extracted
  with Spark and inserted into MongoDB, which this page reads from.
- **Units and time:** hourly average flow in MW (15-minute values are averaged to hourly),
  totals in GWh. All times are UTC.
"""
            )

    def render(self) -> None:
        theme.page_header("Cross-border Power Flows", "Power flows",
                          "Physical power flows between Norway and its neighbours from ENTSO-E.")
        # Missing secrets or an unreachable database give a warning instead of a traceback
        with theme.data_guard("the flows from MongoDB"):
            self.data = FlowData()
            connections = self.data.connections()
        if not connections:
            st.warning("No flow data found in MongoDB. Run notebooks/assignment_2.ipynb first.")
            return

        # Then left column's choices alsoi drive the line plot
        left, right = st.columns(2)
        with left:
            connection, year = self.render_pie()
        with right:
            self.render_line(connection, year)

        # Full width below the columns
        self.render_source()


# Streamlit reruns this file on every interaction
FlowsPage().render()
