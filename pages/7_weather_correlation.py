"""Sliding window correlation between a weather variable and the reservoir filling."""

import pandas as pd
import streamlit as st

from modules import state, theme
from modules.analysis import lag_correlation, sliding_window_correlation
from modules.data_loader import ReservoirControls
from modules.weather import (DEFAULT_LOCATIONS, VARIABLE_INFO, WeatherData, aggregate, region_for_area,
                             variable_label)


class WeatherCorrelationPage:
    """Weekly weather against a Magasinstatistikk variable for the area chosen in the sidebar."""

    RESERVOIR_VARIABLES = {
        "change_in_fill_degree": "Weekly change in filling degree",
        "fill_degree": "Filling degree",
    }

    def __init__(self):
        self.controls = ReservoirControls()
        self.weather = WeatherData()

    def render(self) -> None:
        theme.page_header("Weather vs Reservoirs", "Weather",
                          "How does the weather in an area relate to its reservoirs, and how many weeks "
                          "later? The correlation is computed in a window that slides over the weeks.")

        area_type, area_number = self.controls.area_type, self.controls.area_number
        region = region_for_area(area_type, area_number)

        left, right = st.columns(2)
        variables = list(VARIABLE_INFO)
        variable = left.selectbox("Weather variable", options=variables, format_func=variable_label,
                                  **state.widget("weather_variable", variables))
        reservoir_variable = right.selectbox(
            "Reservoir variable", options=list(self.RESERVOIR_VARIABLES),
            format_func=self.RESERVOIR_VARIABLES.get,
            help="The weekly change follows inflow, which reacts to the weather, while the filling "
                 "degree itself is dominated by the yearly cycle.",
        )

        # Each year is one weather download, so the default is kept short
        last_year = self.weather.last_available().year
        first, last = st.select_slider("Years", options=list(range(2000, last_year + 1)),
                                       value=(last_year - 4, last_year))
        left, right = st.columns(2)
        lag = left.slider("Lag (weeks the weather leads)", min_value=0, max_value=30, value=0,
                          help="E.g. snow in winter fills the reservoirs during the melt in spring.")
        window = right.slider("Window length (weeks)", min_value=4, max_value=104, value=26, step=2)

        with theme.data_guard("the data"):
            reservoir = self.controls.data.area_series(area_type, area_number, reservoir_variable)
            reservoir = reservoir.resample("W-SUN").mean()
            progress = st.progress(0.0, text="Downloading weather...")
            frames = []
            for i, year in enumerate(range(first, last + 1)):
                frames.append(self.weather.year(region, year, DEFAULT_LOCATIONS))
                progress.progress((i + 1) / (last - first + 1), text=f"Weather for {year} loaded")
            progress.empty()
            weather = aggregate(pd.concat(frames).sort_index(), "W-SUN")[variable]

        reservoir = reservoir.loc[str(first):str(last)].rename(self.RESERVOIR_VARIABLES[reservoir_variable])
        try:
            fig, summary = sliding_window_correlation(weather.rename(variable), reservoir, window=window, lag=lag)
        except ValueError as error:
            st.warning(str(error))
            return
        theme.show(fig)

        a, b, c, d = st.columns(4)
        a.metric("Overall correlation", f"{summary['overall']:.2f}")
        b.metric("Mean windowed", f"{summary['mean']:.2f}")
        c.metric("Lowest", f"{summary['min']:.2f}")
        d.metric("Highest", f"{summary['max']:.2f}")

        # Which lead time says most, to choose the lag above and lagged inputs for a forecast
        lag_fig, _ = lag_correlation(weather.rename(variable), reservoir, max_lag=30, current_lag=lag)
        theme.show(lag_fig)

        with st.expander("Method"):
            st.markdown(
                f"""
- **Area:** {self.controls.area_label} (weather region {region}, mean of {DEFAULT_LOCATIONS} sampled locations).
- **Weeks:** the hourly ERA5 data is converted from UTC to Norwegian time and combined to
  Monday–Sunday weeks, the same weeks as Magasinstatistikk (sums for precipitation-like
  variables, means for the rest).
- **Lag:** the weather series is shifted {lag} weeks forward, so each reservoir week is compared
  with the weather {lag} weeks earlier.
- **Correlation:** Pearson correlation in a {window}-week window that slides one week at a time.
  The bar chart gives the correlation over all chosen years for every lag, with the chosen lag dashed.
"""
            )


# Streamlit reruns this file on every interaction
WeatherCorrelationPage().render()
