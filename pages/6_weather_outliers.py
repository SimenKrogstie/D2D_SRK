"""Outliers (SPC) and anomalies (LOF) in a chosen weather variable for one area."""

import pandas as pd
import streamlit as st

from modules import state, theme
from modules.analysis import lof_anomalies, spc_outliers
from modules.data_loader import ReservoirControls
from modules.weather import VARIABLE_INFO, WeatherData, region_for_area, variable_label


class WeatherOutliersPage:
    """SPC and LOF tabs for the area chosen in the sidebar.

    The weather is downloaded and cached when the area, year or number of locations changes.
    """

    def __init__(self):
        self.controls = ReservoirControls()
        self.weather = WeatherData()

    def render(self) -> None:
        header = theme.page_header("Weather Outliers and Anomalies", "Weather",
                                   "Unusual weather in the chosen area: outliers from the seasonal pattern with "
                                   "Statistical Process Control (SPC), and anomalies with the Local Outlier Factor (LOF).")

        if not self.weather.available():
            st.warning("The region shapefiles are missing from data/.")
            return

        # Reservoir area -> weather region, e.g. ("EL", 3) -> "NO3"
        region = region_for_area(self.controls.area_type, self.controls.area_number)

        # The variable is shared with the correlation page and the map, the rest stays local
        left, middle, right = st.columns(3)
        variables = list(VARIABLE_INFO)
        variable = left.selectbox("Weather variable", options=variables, format_func=variable_label,
                                  **state.widget("weather_variable", variables))
        last_full_year = pd.Timestamp.now().year - 1
        year = middle.selectbox("Year", options=list(range(last_full_year, 1999, -1)),
                                index=last_full_year - 2024 if last_full_year >= 2024 else 0)
        n_locations = right.number_input(
            "Locations to average", min_value=1, max_value=20, value=1,
            help="Random locations from the 1000 sampled in the region. More locations give a "
                 "better regional average, but use more of the free API quota.",
        )
        # Cached, so moving the SPC or LOF sliders does not download again
        with theme.data_guard("the weather data from open-meteo"):
            weather = self.weather.year(region, year, n_locations)
        series = weather[variable]
        if series.isna().all():
            st.warning(f"No {variable_label(variable, False).lower()} values for this area and year.")
            return
        header.caption(f"Hourly ERA5 data for {self.controls.area_label}, {year}, "
                       f"averaged over {n_locations} location(s). {series.isna().sum()} missing hours.")

        spc_tab, lof_tab = st.tabs(["Outliers (SPC)", "Anomalies (LOF)"])
        with spc_tab:
            self.render_spc(series, variable)
        with lof_tab:
            self.render_lof(series, variable)

        with st.expander("Data source"):
            st.markdown(
                """
- **Source:** [open-meteo historical weather API](https://open-meteo.com/en/docs/historical-weather-api),
  ERA5 reanalysis (about 25 km grid), hourly values in UTC.
- **Locations:** 1000 random points per region from the NVE Atlas polygons. The chosen number
  of them is downloaded and averaged.
- **SPC:** on daily values (sums for precipitation, rain, snowfall and evapotranspiration,
  means for the rest). The DCT removes the seasonal part, and the limits come from the median
  and MAD of what is left (the SATV).
- **LOF:** on time and value, so an anomaly stands out from the hours around it.
"""
            )

    @staticmethod
    def render_spc(series: pd.Series, variable: str) -> None:
        """SPC settings, plot, key numbers and largest outliers."""
        left, right = st.columns(2)
        cutoff = left.slider("DCT cut-off (days)", min_value=2, max_value=120, value=30,
                             help="Variation slower than this counts as seasonal")
        n_std = right.slider("Number of standard deviations", min_value=1.0, max_value=10.0,
                             value=4.0, step=0.5)
        try:
            fig, summary = spc_outliers(series, variable, cutoff_days=cutoff, n_std=n_std)
        except ValueError as error:
            st.warning(str(error))
            return
        theme.show(fig)

        # Key numbers and the 20 largest outliers
        a, b, c = st.columns(3)
        a.metric("Outliers", summary["n_outliers"])
        b.metric("Share of days", f"{summary['share']:.1%}")
        c.metric("Above / below", f"{summary['n_above']} / {summary['n_below']}")
        st.dataframe(summary["outliers"].head(20), hide_index=True, width="stretch")

    @staticmethod
    def render_lof(series: pd.Series, variable: str) -> None:
        """LOF settings, plot, key numbers and the strongest anomalies."""
        left, right = st.columns(2)
        contamination = left.slider("Proportion of outliers", min_value=0.001, max_value=0.10,
                                    value=0.01, step=0.001, format="%.3f")
        n_neighbors = right.slider("Neighbours", min_value=5, max_value=100, value=20)
        try:
            fig, summary = lof_anomalies(series, variable, contamination=contamination,
                                         n_neighbors=n_neighbors)
        except ValueError as error:
            st.warning(str(error))
            return
        theme.show(fig)

        # Key numbers and the 20 strongest anomalies
        a, b = st.columns(2)
        a.metric("Anomalies", summary["n_anomalies"])
        b.metric("Share of hours", f"{summary['share']:.1%}")
        st.dataframe(summary["anomalies"].head(20), hide_index=True, width="stretch")


# Streamlit reruns this file on every interaction
WeatherOutliersPage().render()
