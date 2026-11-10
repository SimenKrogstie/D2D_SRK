"""Outliers in precipitation (SPC) and anomalies in temperature (LOF) for one area."""

import pandas as pd
import streamlit as st

from modules.analysis import precipitation_outliers, temperature_anomalies
from modules.data_loader import ReservoirControls
from modules.weather import WeatherData, region_for_area


class WeatherOutliersPage:
    """SPC and LOF tabs for the area chosen in the sidebar.

    The weather is downloaded and cached when the area, year or number of locations changes.
    """

    def __init__(self):
        self.controls = ReservoirControls()
        self.weather = WeatherData()

    def render(self) -> None:
        st.title("Weather Outliers and Anomalies")

        if not self.weather.available():
            st.warning("The region shapefiles are missing from data/.")
            return

        # Reservoir area -> weather region, e.g. ("EL", 3) -> "NO3"
        region = region_for_area(self.controls.area_type, self.controls.area_number)

        # Only this page uses these, so they stay local
        left, right = st.columns(2)
        last_full_year = pd.Timestamp.now().year - 1
        year = left.selectbox("Year", options=list(range(last_full_year, 1999, -1)),
                              index=last_full_year - 2024 if last_full_year >= 2024 else 0)
        n_locations = right.number_input(
            "Locations to average", min_value=1, max_value=20, value=1,
            help="Random locations from the 1000 sampled in the region. More locations give a "
                 "better regional average, but use more of the free API quota.",
        )
        # Cached, so moving the SPC or LOF sliders does not download again
        weather = self.weather.year(region, year, n_locations)
        st.caption(f"Hourly ERA5 data for {self.controls.area_label} (region {region}), {year}, "
                   f"averaged over {n_locations} location(s).")

        spc_tab, lof_tab = st.tabs(["Outliers (SPC)", "Anomalies (LOF)"])
        with spc_tab:
            self.render_spc(weather["precipitation"])
        with lof_tab:
            self.render_lof(weather["temperature_2m"])

        with st.expander("Data source"):
            st.markdown(
                """
- **Source:** [open-meteo historical weather API](https://open-meteo.com/en/docs/historical-weather-api),
  ERA5 reanalysis (about 25 km grid), hourly values in UTC.
- **Locations:** 1000 random points per region from the NVE Atlas polygons. The chosen number
  of them is downloaded and averaged.
- **SPC:** on daily totals. The DCT removes the seasonal part, and the limits come from the
  median and MAD of what is left.
- **LOF:** on time and temperature, so an anomaly stands out from the hours around it.
"""
            )

    @staticmethod
    def render_spc(precipitation: pd.Series) -> None:
        """SPC settings, plot, key numbers and largest outliers."""
        left, right = st.columns(2)
        cutoff = left.slider("DCT cut-off (days)", min_value=2, max_value=120, value=30,
                             help="Variation slower than this counts as seasonal")
        n_std = right.slider("Number of standard deviations", min_value=1.0, max_value=10.0,
                             value=4.0, step=0.5)
        fig, summary = precipitation_outliers(precipitation, cutoff_days=cutoff, n_std=n_std)
        st.plotly_chart(fig, width="stretch")

        # Key numbers and the 20 largest outliers
        a, b, c = st.columns(3)
        a.metric("Outliers", summary["n_outliers"])
        b.metric("Share of days", f"{summary['share']:.1%}")
        c.metric("Above / below", f"{summary['n_above']} / {summary['n_below']}")
        st.dataframe(summary["outliers"].head(20), hide_index=True, width="stretch")

    @staticmethod
    def render_lof(temperature: pd.Series) -> None:
        """LOF settings, plot, key numbers and the strongest anomalies."""
        left, right = st.columns(2)
        contamination = left.slider("Proportion of outliers", min_value=0.001, max_value=0.10,
                                    value=0.01, step=0.001, format="%.3f")
        n_neighbors = right.slider("Neighbours", min_value=5, max_value=100, value=20)
        fig, summary = temperature_anomalies(temperature, contamination=contamination,
                                             n_neighbors=n_neighbors)
        st.plotly_chart(fig, width="stretch")

        # Key numbers and the 20 strongest anomalies
        a, b = st.columns(2)
        a.metric("Anomalies", summary["n_anomalies"])
        b.metric("Share of hours", f"{summary['share']:.1%}")
        st.dataframe(summary["anomalies"].head(20), hide_index=True, width="stretch")


# Streamlit reruns this file on every interaction
WeatherOutliersPage().render()
