"""STL decomposition and spectrogram of the reservoir filling degree for one area."""

import pandas as pd
import streamlit as st

from modules import theme
from modules.analysis import spectrogram, stl_decomposition
from modules.data_loader import ReservoirControls


class ReservoirAnalysisPage:
    """STL and spectrogram tabs for the area chosen in the sidebar.

    The years are chosen here, since both analyses need several years of data.
    """

    def __init__(self):
        self.controls = ReservoirControls()

    def render(self) -> None:
        header = theme.page_header("Seasonal Analysis", "Reservoirs",
                                   "The weekly filling degree of the chosen area split into trend, yearly cycle and "
                                   "remainder (STL), and how its periodic patterns change over time (spectrogram).")

        with theme.data_guard("the reservoir data from NVE"):
            series = self.controls.data.area_series(self.controls.area_type, self.controls.area_number)
        series = series.dropna()
        if series.empty:
            st.info("No filling degree data for this area.")
            return

        # Local year range, defaulting to the last ten years
        index_years = pd.DatetimeIndex(series.index).year   
        years = list(range(int(index_years.min()), int(index_years.max()) + 1))
        first, last = st.select_slider(
            "Years", options=years, value=(max(years[0], years[-1] - 9), years[-1])
        )
        series = series.loc[str(first):str(last)]
        header.caption(f"Weekly filling degree for {self.controls.area_label}, {first}–{last}.")

        stl_tab, spectrogram_tab = st.tabs(["STL decomposition", "Spectrogram"])
        with stl_tab:
            self.render_stl(series)
        with spectrogram_tab:
            self.render_spectrogram(series)

    @staticmethod
    def render_stl(series) -> None:
        """STL settings and plot."""
        # Smoother lengths in weeks. STL needs odd numbers, so the inputs step by 2
        left, middle, right = st.columns(3)
        seasonal = left.number_input("Seasonal smoother (weeks)", min_value=7, max_value=101,
                                     value=13, step=2)
        trend = middle.number_input("Trend smoother (weeks)", min_value=53, max_value=521,
                                    value=105, step=2)
        robust = right.checkbox("Robust fitting", value=True,
                                help="Down-weights outliers when fitting the smoothers")
        # Invalid settings show a warning instead of crashing the page
        try:
            theme.show(stl_decomposition(series, seasonal=seasonal, trend=trend, robust=robust))
        except ValueError as error:
            st.warning(str(error))

    @staticmethod
    def render_spectrogram(series) -> None:
        """Spectrogram settings and plot."""
        # Window and overlap in weeks, the overlap is limited to be shorter than the window
        left, right = st.columns(2)
        window = left.slider("Window length (weeks)", min_value=26, max_value=260, value=104, step=2)
        overlap = right.slider("Window overlap (weeks)", min_value=0, max_value=window - 1,
                               value=min(78, window - 1))
        try:
            theme.show(spectrogram(series, window_weeks=window, overlap_weeks=overlap))
        except ValueError as error:
            st.warning(str(error))


# Streamlit reruns this file on every interaction
ReservoirAnalysisPage().render()
