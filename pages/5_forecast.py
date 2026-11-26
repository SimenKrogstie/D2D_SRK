"""SARIMAX forecast of the filling degree for one area, with selectable exogenous variables."""

import pandas as pd
import streamlit as st

from modules import state, theme
from modules.currency import CurrencyData
from modules.data_loader import ReservoirControls, ReservoirData
from modules.forecast import (
    DEFAULTS,
    build_dataset,
    calibration_weeks,
    exog_label,
    forecast_animation,
    forecast_filling,
)
from modules.weather import (
    DEFAULT_LOCATIONS,
    VARIABLE_INFO,
    WeatherData,
    aggregate,
    region_for_area,
)

CURRENCIES = ["EUR_NOK", "USD_NOK"]
# "none" rather than None, which a selectbox treats as no selection
INTERVALS = {
    "quantile": "Quantile loss models",
    "conformal": "Conformal (errors of earlier forecasts)",
    "none": "None",
}
LEVEL = 0.9


def data_span(window: tuple[str, str], horizon: int, interval: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """First and last week to load: the training window, earlier weeks for a conformal
    interval, and the horizon after it for the actual values."""
    start = pd.Period(window[0], freq="M").start_time
    if interval == "conformal":
        start -= pd.Timedelta(weeks=calibration_weeks(horizon))
    end = pd.Period(window[1], freq="M").end_time + pd.Timedelta(weeks=horizon)
    return start, end


def load_dataset(area_type: str, area_number: int, start: pd.Timestamp, end: pd.Timestamp,
                 exog: tuple[str, ...]) -> pd.DataFrame:
    """Weekly filling degree plus the chosen exogenous variables between start and end."""
    target = ReservoirData().area_series(area_type, area_number, "fill_degree").loc[start:end]
    frames = []
    weather_vars = [c for c in exog if c in VARIABLE_INFO]
    if weather_vars:
        weather = WeatherData()
        last = min(end, weather.last_available())
        hourly = weather.years(region_for_area(area_type, area_number), start.year, last.year, DEFAULT_LOCATIONS)
        frames.append(aggregate(hourly, "W-SUN")[weather_vars])
    currencies = [c for c in exog if c in CURRENCIES]
    if currencies:
        rates = CurrencyData().rates(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        frames.append(rates.asfreq("D").ffill().resample("W-SUN").mean()[currencies])
    exog_df = pd.concat(frames, axis=1) if frames else None
    return build_dataset(target, exog_df)


@st.cache_data(show_spinner="Training SARIMAX and forecasting...")
def run_forecast(area_type: str, area_number: int, window: tuple[str, str], horizon: int,
                 params: tuple, exog: tuple[str, ...], deseasonalize: bool, interval: str):
    """Cached on every input, so going back and forth between pages doesn't train again."""
    start = pd.Period(window[0], freq="M").start_time
    cutoff = pd.Period(window[1], freq="M").end_time
    # Data outside the window is only used for the interval, the actual values and climatologies
    df = load_dataset(area_type, area_number, *data_span(window, horizon, interval), exog)
    p, d, q, sp, sd, sq, learning_rate = params
    # The training data is the window, so the rows before it are cut off with history_years
    years = (cutoff - start).days / 365.25
    result, summary = forecast_filling(
        df, exog=exog, horizon=horizon, p=p, d=d, q=q, m=52, sp=sp, sd=sd, sq=sq,
        history_years=years, learning_rate=learning_rate, deseasonalize=deseasonalize,
        interval=None if interval == "none" else interval, level=LEVEL, cutoff=cutoff,
    )
    history = df["fill_degree"].loc[:summary["train_end"]]
    return history, result, summary


class ForecastPage:
    """Model settings in a form, the forecast as an animated Plotly figure."""

    def __init__(self):
        self.controls = ReservoirControls()

    @staticmethod
    def init_form() -> None:
        """Seed the form widgets from the last run, or the defaults from the notebook backtests.

        The widgets have keys and no default values: a default that changes gives the widget a
        new identity, and the next submitted value would be lost. Streamlit drops the keys when
        another page is shown, so they are seeded again on return.
        """
        stored = state.get("forecast_settings")
        if stored:
            p, d, q, sp, sd, sq, lr = stored["params"]
            initial = {"p": p, "d": d, "q": q, "sp": sp, "sd": sd, "sq": sq, "learning_rate": lr,
                       "exog": stored["exog"], "deseasonalize": stored["deseasonalize"],
                       "interval": stored["interval"]}
        else:
            initial = {k: DEFAULTS[k] for k in ("p", "d", "q", "sp", "sd", "sq", "learning_rate",
                                                "exog", "deseasonalize")}
            initial["interval"] = DEFAULTS["interval"] or "none"
        initial["exog"] = list(initial["exog"])
        initial["horizon"] = int(state.get("forecast_horizon"))
        for name, value in initial.items():
            st.session_state.setdefault(f"fc_{name}", value)

    def settings(self) -> dict | None:
        """The form. Returns the stored settings, which are only replaced when the form is sent."""
        self.init_form()
        with st.form("forecast_settings"):
            st.markdown("**Model** – SARIMAX(p, d, q)(sp, sd, sq)₅₂ with a linear regressor")
            cols = st.columns(7)
            p = cols[0].number_input("p", 0, 6, key="fc_p", help="Autoregressive lags")
            d = cols[1].number_input("d", 0, 2, key="fc_d", help="Differencing")
            q = cols[2].number_input("q", 0, 6, key="fc_q", help="Moving average lags")
            sp = cols[3].number_input("sp", 0, 2, key="fc_sp", help="Seasonal autoregressive lags (52 weeks)")
            sd = cols[4].number_input("sd", 0, 1, key="fc_sd", help="Seasonal differencing")
            sq = cols[5].number_input("sq", 0, 2, key="fc_sq", help="Seasonal moving average lags")
            learning_rate = cols[6].select_slider("Learning rate", options=[0.001, 0.003, 0.01, 0.03, 0.1],
                                                  key="fc_learning_rate")

            left, right = st.columns([2, 1])
            exog = left.multiselect(
                "Exogenous variables", options=list(VARIABLE_INFO) + CURRENCIES, format_func=exog_label,
                key="fc_exog",
                help=f"Weather from open-meteo (mean of {DEFAULT_LOCATIONS} locations in the area), "
                     "exchange rates from Norges Bank. Future weeks use only what is known at the "
                     "end of the training data: the weekly climatology for weather, the last value for rates.",
            )
            deseasonalize = left.checkbox(
                "Remove the weekly climatology before training", key="fc_deseasonalize",
                help="The model then forecasts the deviation from a normal year, and the forecast "
                     "returns towards the normal seasonal path instead of extending the recent trend.",
            )
            horizon = right.slider("Horizon (weeks)", 4, 52, key="fc_horizon")
            interval = right.selectbox("90% interval", options=list(INTERVALS), format_func=INTERVALS.get,
                                       key="fc_interval")
            submitted = st.form_submit_button("Run forecast", type="primary")

        if submitted:
            state.set("forecast_horizon", horizon)
            state.set("forecast_settings", {"params": (p, d, q, sp, sd, sq, learning_rate),
                                            "exog": tuple(exog), "horizon": horizon,
                                            "deseasonalize": deseasonalize, "interval": interval})
        return state.get("forecast_settings")

    def render(self) -> None:
        header = theme.page_header("Forecast Reservoir Filling", "Reservoirs",
                                   "A SARIMAX forecast of the weekly filling degree for the chosen area, with weather "
                                   "and exchange rates as optional inputs and a 90% interval.")
        window = self.controls.month_range
        header.caption(f"Training data: {self.controls.area_label}, {window[0]} to {window[1]}. "
                       'The forecast starts after the selected to-date.')

        settings = self.settings()
        if settings is None:
            st.info("Choose the settings and press **Run forecast**. The defaults are the best setting "
                    "from the tests in the part 4 notebook.")
            return

        with theme.data_guard("the data for the forecast"):
            # Weather years are downloaded with a progress bar first, so the cached run is quick
            if any(c in VARIABLE_INFO for c in settings["exog"]):
                self.preload_weather(*data_span(window, settings["horizon"], settings["interval"]))
            try:
                history, result, summary = run_forecast(
                    self.controls.area_type, self.controls.area_number, window, settings["horizon"],
                    settings["params"], settings["exog"], settings["deseasonalize"], settings["interval"],
                )
            except ValueError as error:
                st.warning(f"The forecast could not be made: {error}")
                return

        p, d, q, sp, sd, sq, _ = settings["params"]
        title = (f"{self.controls.area_label}: SARIMAX({p},{d},{q})({sp},{sd},{sq})₅₂"
                 f"{' on deviations from climatology' if settings['deseasonalize'] else ''}, "
                 f"exogenous: {', '.join(exog_label(c) for c in settings['exog']) or 'none'}")
        theme.show(forecast_animation(history, result, title, band_label=f"{LEVEL:.0%} interval"))

        cols = st.columns(5)
        cols[0].metric("Training weeks", summary["n_train"])
        cols[1].metric("Runtime", f"{summary['runtime_s']:.2f} s")
        cols[2].metric("Forecast in last week", f"{result['forecast'].iloc[-1]:.1%}")
        if "mae" in summary:
            cols[3].metric("MAE", f"{summary['mae']:.3f}", help="Mean absolute error against the actual filling")
        if "coverage" in summary:
            cols[4].metric("Interval coverage", f"{summary['coverage']:.0%}",
                           help=f"Share of actual weeks inside the {LEVEL:.0%} interval")

        with st.expander("Forecast table"):
            st.dataframe(result, width="stretch",
                         column_config={c: st.column_config.NumberColumn(format="percent")
                                        for c in result.columns})

    def preload_weather(self, start: pd.Timestamp, end: pd.Timestamp) -> None:
        weather = WeatherData()
        region = region_for_area(self.controls.area_type, self.controls.area_number)
        first, last = start.year, min(end, weather.last_available()).year
        progress = st.progress(0.0, text="Downloading weather...")
        for i, year in enumerate(range(first, last + 1)):
            weather.year(region, year, DEFAULT_LOCATIONS)
            progress.progress((i + 1) / (last - first + 1), text=f"Weather for {year} loaded")
        progress.empty()


# Streamlit reruns this file on every interaction
ForecastPage().render()
