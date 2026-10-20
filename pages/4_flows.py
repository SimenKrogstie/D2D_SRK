"""Cross-border power flows to and from Norway, read from MongoDB."""

import calendar

import plotly.express as px
import streamlit as st

from modules.data_flow import FlowData


class FlowsPage:
    """Yearly pie chart on the left, hourly line plot for chosen months on the right."""

    # Month numbers (stored in MongoDB) mapped to short names (shown on the pills)
    MONTH_NAMES = {m: calendar.month_abbr[m] for m in range(1, 13)}

    def __init__(self):
        self.data = FlowData() # Cached MongoDB queries

    def render_pie(self) -> tuple[str, int]:
        """Left column: connection and year selection, pie chart of the yearly totals per direction."""
        st.subheader("Yearly total per direction")
        connection = st.radio("Connection", options=self.data.connections(), horizontal=True)
        years = self.data.years(connection)
        # Default the recent complete year
        year = st.selectbox("Year", options=years, index=max(len(years) - 2, 0))

        year_df = self.data.flows(connection, year)
        # Sum hourly energy, shown in GWh
        totals = year_df.groupby("direction", as_index=False)["energy_mwh"].sum()
        totals["energy_gwh"] = totals["energy_mwh"] / 1000

        fig = px.pie(totals, names="direction", values="energy_gwh", title=f"{connection}, {year} (GWh)")
        fig.update_traces(textinfo="percent+value")
        st.plotly_chart(fig, width="stretch")
        return connection, year

    def render_line(self, connection: str, year: int) -> None:
        """Right column: month pills, hourly line plot per direction."""
        st.subheader("Hourly flow for chosen months")
        # Multi-select, January by default
        months = st.pills(
            "Months",
            options=list(self.MONTH_NAMES),
            format_func=self.MONTH_NAMES.get,
            selection_mode="multi",
            default=[1],
        )
        if not months:
            st.info("Select one or more months.")
            return

        # Sorted tuple, so the same selectriuon hits the same cache entry
        month_df = self.data.flows(connection, year, tuple(sorted(months)))
        if month_df.empty:
            st.info("No data for the selected months.")
            return

        fig = px.line(
            month_df,
            x="time",
            y="flow_mw",
            color="direction",
            title=f"{connection}, {year}",
            labels={"time": "Time (UTC)", "flow_mw": "Flow (MW)", "direction": "Direction"},
        )
        st.plotly_chart(fig, width="stretch")

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
        st.title("🔌 Cross-border Power Flows")
        if not self.data.connections():
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
