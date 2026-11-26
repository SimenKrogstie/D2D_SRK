"""Forecasts of weekly reservoir filling with SARIMAX, shared by the notebook and the app.

River calls the model SNARIMAX (N for non-linear, since the regressor can be any River model).
With the linear regressor used here it is an ordinary SARIMAX.
"""

import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from river import linear_model, optim, preprocessing, time_series

from modules.weather import variable_label

# Week ending Sunday, same as Magasinstatistikk
FREQ = "W-SUN"

# Best setting from the backtests in notebooks/assignment_4.ipynb, used by the app
DEFAULTS = {
    "p": 1,
    "d": 1,
    "q": 0,
    "m": 52,
    "sp": 0,
    "sd": 0,
    "sq": 0,
    "history_years": 3,
    "learning_rate": 0.01,
    # Without it, d=1 extends the autumn drawdown as a straight line to 0
    "deseasonalize": True,
    # Climatology for future weather added nothing over the deseasonalized model
    "exog": (),
    # Held-out coverage: conformal 92%, quantile models 69% (nominal 90%)
    "interval": "conformal",
}

# Reference forecasts without a model, see baseline_forecast
BASELINES = ("seasonal_naive", "climatology")

# Conformal intervals: forecasts from one year of earlier cutoffs, two weeks apart
CALIBRATION_RUNS = 26
CALIBRATION_STEP_WEEKS = 2


def exog_label(column: str) -> str:
    """Readable name of an exogenous column."""
    if column.endswith("_NOK"):
        return f"{column[:-4]}/NOK"
    return variable_label(column)


def build_dataset(target: pd.Series, exog: pd.DataFrame | None = None) -> pd.DataFrame:
    """Target and exogenous variables on the same weekly index.

    Short gaps in the exogenous variables (up to four weeks) are interpolated. Weeks still
    missing a value are dropped, so the model only sees complete rows.
    """
    target = target.sort_index().resample(FREQ).mean().interpolate(limit=4)
    df = target.to_frame(target.name or "target")
    if exog is not None and not exog.empty:
        exog = exog.sort_index().resample(FREQ).mean().interpolate(limit=4, limit_area="inside")
        df = df.join(exog, how="inner")
    return df.dropna()


def calibration_weeks(horizon: int) -> int:
    """Weeks of data needed before the training window for a conformal interval."""
    return horizon + CALIBRATION_RUNS * CALIBRATION_STEP_WEEKS


def future_exog(past: pd.DataFrame, columns: list[str], index: pd.DatetimeIndex,
                known: pd.DataFrame | None = None) -> pd.DataFrame:
    """Exogenous values for the forecast weeks, from what is known at the cutoff.

    Weather gets its weekly climatology (mean for the week of year in `past`) and exchange
    rates their last value, since future weather and rates are unknown. With `known`, its
    values are used where it covers the week instead (an oracle, to see what a perfect
    weather forecast would add).
    """
    if known is not None:
        values = known[columns].reindex(index)
    else:
        values = pd.DataFrame(np.nan, index=index, columns=columns)
    week = past.index.isocalendar().week.to_numpy()
    for column in columns:
        missing = values[column].isna()
        if not missing.any():
            continue
        if column.endswith("_NOK"):
            fill = pd.Series(past[column].iloc[-1], index=index)
        else:
            climatology = past[column].groupby(week).mean()
            fill = pd.Series(index.isocalendar().week.map(climatology).to_numpy(), index=index, dtype=float)
            fill = fill.fillna(past[column].mean())  # Week 53
        values.loc[missing, column] = fill[missing]
    return values


def _model(p, d, q, m, sp, sd, sq, learning_rate, loss=None) -> time_series.SNARIMAX:
    """SARIMAX with a standardised linear regressor, optionally with a quantile loss."""
    regressor = preprocessing.StandardScaler() | linear_model.LinearRegression(
        optimizer=optim.SGD(learning_rate), intercept_lr=learning_rate, loss=loss
    )
    return time_series.SNARIMAX(p=p, d=d, q=q, m=m, sp=sp, sd=sd, sq=sq, regressor=regressor)


def _history(df: pd.DataFrame, cutoff, history_years: float | None) -> pd.DataFrame:
    """Training rows: up to the cutoff, and only the last `history_years` of them."""
    history = df.loc[:cutoff] if cutoff is not None else df
    if history_years and not history.empty:
        # In days, so fractional years work (the app passes the length of its time window)
        history = history.loc[history.index[-1] - pd.Timedelta(days=round(history_years * 365.25)):]
    return history


def weekly_climatology(series: pd.Series, index: pd.DatetimeIndex) -> np.ndarray:
    """Mean of `series` for the week of year of each date in `index` (week 53 gets the overall mean)."""
    climatology = series.groupby(series.index.isocalendar().week.to_numpy()).mean()
    return index.isocalendar().week.map(climatology).astype(float).fillna(series.mean()).to_numpy()


def _fit_predict(history: pd.DataFrame, df: pd.DataFrame, target: str, exog: list[str], horizon: int,
                 order: dict, learning_rate: float, losses: dict, known_future: bool,
                 deseasonalize: bool = False) -> pd.DataFrame:
    """Train one model per loss on `history` one week at a time, then forecast `horizon` weeks.

    With `deseasonalize`, the models learn the deviation from the weekly climatology (all data
    before the cutoff), which is added back to the forecast.
    """
    # Fill degree is a share (0-1). In percent the weekly changes are of order 1, which suits
    # the SGD step size
    scale = 100.0 if history[target].abs().max() <= 1.5 else 1.0
    y = history[target] * scale
    index = pd.date_range(history.index[-1] + pd.Timedelta(weeks=1), periods=horizon, freq=FREQ)
    seasonal_past, seasonal_future = 0.0, 0.0
    if deseasonalize:
        past_target = df[target].loc[:history.index[-1]] * scale
        seasonal_past = weekly_climatology(past_target, history.index)
        seasonal_future = weekly_climatology(past_target, index)
        y = y - seasonal_past
    models = {name: _model(**order, learning_rate=learning_rate, loss=loss) for name, loss in losses.items()}

    xs_train = history[exog].to_dict("records") if exog else [None] * len(history)
    for value, x in zip(y.to_numpy(), xs_train):
        for model in models.values():
            model.learn_one(float(value), x)

    xs_future = None
    if exog:
        past = df.loc[:history.index[-1]]
        xs_future = future_exog(past, exog, index, known=df if known_future else None).to_dict("records")
    result = pd.DataFrame(index=index)
    for name, model in models.items():
        forecast = np.asarray(model.forecast(horizon=horizon, xs=xs_future), dtype=float)
        result[name] = (forecast + seasonal_future) / scale
    return result


def _conformal_widths(df: pd.DataFrame, history: pd.DataFrame, target: str, exog: list[str], horizon: int,
                      order: dict, learning_rate: float, level: float, known_future: bool,
                      deseasonalize: bool) -> np.ndarray:
    """Half-width of the interval for each week ahead, from the errors of earlier forecasts.

    The same setting forecasts from CALIBRATION_RUNS earlier cutoffs whose horizon ends before
    the training data does, so only data known at the cutoff is used. The conformal quantile
    of the absolute errors per week ahead gives the width.
    """
    n_train = len(history)
    errors = []
    for k in range(CALIBRATION_RUNS):
        cutoff = history.index[-1] - pd.Timedelta(weeks=horizon + CALIBRATION_STEP_WEEKS * k)
        past = df.loc[:cutoff].iloc[-n_train:]
        if len(past) < n_train:
            break  # Earlier cutoffs have even less data
        forecast = _fit_predict(past, df, target, exog, horizon, order, learning_rate,
                                {"forecast": None}, known_future, deseasonalize)["forecast"]
        errors.append((forecast - df[target].reindex(forecast.index)).abs().to_numpy())
    if len(errors) < 5:
        raise ValueError(f"Too little data before the training window for a conformal interval: "
                         f"it needs {calibration_weeks(horizon)} weeks more")
    errors = np.vstack(errors)
    n = len(errors)
    q = min(1.0, np.ceil((n + 1) * level) / n)
    return np.nanquantile(errors, q, axis=0, method="higher")


def _summary(result: pd.DataFrame, history: pd.DataFrame, started: float) -> dict:
    """Training span, runtime and, where the actual values are known, the errors."""
    summary = {"n_train": len(history), "train_start": history.index[0], "train_end": history.index[-1],
               "runtime_s": time.perf_counter() - started}
    known = result.dropna(subset=["actual"])
    if not known.empty:
        errors = known["forecast"] - known["actual"]
        summary["mae"] = float(errors.abs().mean())
        summary["rmse"] = float(np.sqrt((errors ** 2).mean()))
        if {"lower", "upper"} <= set(known.columns):
            inside = (known["actual"] >= known["lower"]) & (known["actual"] <= known["upper"])
            summary["coverage"] = float(inside.mean())
    return summary


def forecast_filling(
    df: pd.DataFrame,
    target: str = "fill_degree",
    exog: list[str] | tuple[str, ...] = (),
    horizon: int = 26,
    p: int = DEFAULTS["p"],
    d: int = DEFAULTS["d"],
    q: int = DEFAULTS["q"],
    m: int = DEFAULTS["m"],
    sp: int = DEFAULTS["sp"],
    sd: int = DEFAULTS["sd"],
    sq: int = DEFAULTS["sq"],
    history_years: float | None = DEFAULTS["history_years"],
    learning_rate: float = DEFAULTS["learning_rate"],
    deseasonalize: bool = DEFAULTS["deseasonalize"],
    interval: str | None = DEFAULTS["interval"],
    level: float = 0.9,
    cutoff: str | pd.Timestamp | None = None,
    known_future: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Dynamic multi-step forecast of the target `horizon` weeks after `cutoff`.

    The model learns one week at a time on the last `history_years` before the cutoff (the
    whole frame when cutoff is None), and then forecasts all weeks at once, feeding its own
    forecasts back as lags. Future exogenous values come from `future_exog`. With
    `deseasonalize`, the model forecasts the deviation from the weekly climatology.

    interval: "quantile" trains two extra models with a quantile loss for the bounds,
    "conformal" widens the forecast by the errors of earlier forecasts (needs
    `calibration_weeks(horizon)` weeks of data before the training window), None gives none.
    Returns the forecast frame and a summary.
    """
    started = time.perf_counter()
    exog = list(exog)
    order = {"p": p, "d": d, "q": q, "m": m, "sp": sp, "sd": sd, "sq": sq}
    history = _history(df, cutoff, history_years)
    needed = max(p, q, m * max(sp, sd, sq)) + d + m * sd + 10
    if len(history) < needed:
        raise ValueError(f"Too little training data: {len(history)} weeks, the settings need at least {needed}")

    losses = {"forecast": None}
    if interval == "quantile":
        losses["lower"] = optim.losses.Quantile(alpha=(1 - level) / 2)
        losses["upper"] = optim.losses.Quantile(alpha=(1 + level) / 2)
    elif interval not in (None, "conformal"):
        raise ValueError(f"Unknown interval '{interval}'")
    result = _fit_predict(history, df, target, exog, horizon, order, learning_rate, losses, known_future,
                          deseasonalize)

    if interval == "quantile":
        # The quantile models are trained separately, so they can cross the point forecast
        result["lower"] = np.minimum(result["lower"], result["forecast"])
        result["upper"] = np.maximum(result["upper"], result["forecast"])
    elif interval == "conformal":
        widths = _conformal_widths(df, history, target, exog, horizon, order, learning_rate, level,
                                   known_future, deseasonalize)
        result["lower"] = result["forecast"] - widths
        result["upper"] = result["forecast"] + widths
    if history[target].abs().max() <= 1.5:
        result = result.clip(0, 1)  # A share can't leave 0-1
    result["actual"] = df[target].reindex(result.index)
    result.index.name = "date"
    return result, _summary(result, history, started)


def baseline_forecast(df: pd.DataFrame, target: str = "fill_degree", horizon: int = 26,
                      method: str = "climatology", cutoff: str | pd.Timestamp | None = None
                      ) -> tuple[pd.DataFrame, dict]:
    """Reference forecasts without a model, to judge whether SARIMAX adds anything.

    seasonal_naive: the value in the same week one year earlier.
    climatology: the mean for the week of year (all data before the cutoff) plus the
    deviation from it in the last observed week, so the forecast starts at the observed
    level and then follows the usual seasonal path.
    """
    started = time.perf_counter()
    history = df.loc[:cutoff] if cutoff is not None else df
    y = history[target]
    index = pd.date_range(y.index[-1] + pd.Timedelta(weeks=1), periods=horizon, freq=FREQ)
    if method == "seasonal_naive":
        values = y.asof(index - pd.Timedelta(weeks=52)).to_numpy()
    elif method == "climatology":
        anomaly = y.iloc[-1] - weekly_climatology(y, y.index[-1:])[0]
        values = weekly_climatology(y, index) + anomaly
    else:
        raise ValueError(f"Unknown baseline '{method}'")

    result = pd.DataFrame({"forecast": values}, index=index)
    if y.abs().max() <= 1.5:
        result = result.clip(0, 1)
    result["actual"] = df[target].reindex(index)
    result.index.name = "date"
    return result, _summary(result, history, started)


def rolling_cutoffs(start: str, end: str, step: str = "2MS") -> list[str]:
    """Cutoff dates from start to end, `step` apart (pandas frequency, e.g. "MS" or "2MS")."""
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, end, freq=step)]


def backtest(df: pd.DataFrame, settings: list[dict], cutoffs: list[str], horizon: int = 26,
             target: str = "fill_degree", baselines: tuple[str, ...] = BASELINES) -> pd.DataFrame:
    """Run every setting and baseline from every cutoff and collect the errors, one row per run.

    The `model` column is "SARIMAX" or the baseline name.
    """
    rows = []
    runs = [("SARIMAX", setting) for setting in settings] + [(name, None) for name in baselines]
    for model, setting in runs:
        for cutoff in cutoffs:
            try:
                if setting is None:
                    _, summary = baseline_forecast(df, target, horizon, method=model, cutoff=cutoff)
                else:
                    _, summary = forecast_filling(df, target=target, horizon=horizon, cutoff=cutoff, **setting)
            except ValueError as error:
                summary = {"error": str(error)}
            row = {k: (", ".join(v) if isinstance(v, (list, tuple)) else v) for k, v in (setting or {}).items()}
            rows.append({"model": model, **row, "cutoff": cutoff,
                         **{k: summary.get(k) for k in ("mae", "rmse", "coverage", "runtime_s", "error")}})
    return pd.DataFrame(rows)


def forecast_animation(history: pd.Series, result: pd.DataFrame, title: str = "",
                       history_weeks: int = 156, y_title: str = "Filling degree",
                       band_label: str = "90% interval") -> go.Figure:
    """History, actual values and the forecast, with frames revealing one forecast week at a time."""
    history = history.iloc[-history_weeks:]
    has_band = {"lower", "upper"} <= set(result.columns)
    # The forecast starts from the last observed week, so the line connects to the history
    start = pd.DataFrame({c: [history.iloc[-1]] for c in ("forecast", "lower", "upper")},
                         index=[history.index[-1]])
    path = pd.concat([start, result[["forecast"] + (["lower", "upper"] if has_band else [])]])

    def forecast_traces(k: int) -> list[go.Scatter]:
        part = path.iloc[:k + 1]
        traces = []
        if has_band:
            traces.append(go.Scatter(x=part.index, y=part["upper"], mode="lines", line={"width": 0},
                                     showlegend=False, hoverinfo="skip"))
            traces.append(go.Scatter(x=part.index, y=part["lower"], mode="lines", line={"width": 0},
                                     fill="tonexty", fillcolor="rgba(242,165,65,0.25)", name=band_label))
        traces.append(go.Scatter(x=part.index, y=part["forecast"], mode="lines+markers",
                                 line={"color": "#F2A541", "width": 2.5}, marker={"size": 4},
                                 name="Forecast"))
        return traces

    static = [go.Scatter(x=history.index, y=history, mode="lines", name="History", line={"color": "#4FA3D9"})]
    # The actual values only exist when the forecast weeks are in the past (backtesting)
    if result["actual"].notna().any():
        static.append(go.Scatter(x=result.index, y=result["actual"], mode="lines", name="Actual",
                                 line={"color": "#C9D1D9", "dash": "dot"}))
    fig = go.Figure(data=[*static, *forecast_traces(1)])
    n_static = len(static)
    animated = list(range(n_static, len(fig.data)))
    fig.frames = [go.Frame(data=forecast_traces(k), traces=animated, name=str(k))
                  for k in range(1, len(path))]

    values = pd.concat([history, path.stack(), result["actual"].dropna()])
    pad = (values.max() - values.min()) * 0.05
    play = {"label": "Play", "method": "animate",
            "args": [None, {"frame": {"duration": 120, "redraw": True}, "fromcurrent": True,
                            "transition": {"duration": 0}}]}
    pause = {"label": "Pause", "method": "animate",
             "args": [[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}]}
    fig.update_layout(
        title=title,
        xaxis={"range": [history.index[0], result.index[-1]], "title": "Week"},
        yaxis={"range": [values.min() - pad, values.max() + pad], "title": y_title},
        hovermode="x unified",
        updatemenus=[{"type": "buttons", "direction": "left", "x": 0, "y": -0.12, "xanchor": "left",
                      "buttons": [play, pause]}],
        sliders=[{"x": 0.18, "y": -0.08, "len": 0.82, "currentvalue": {"prefix": "Weeks ahead: "},
                  "steps": [{"label": str(k), "method": "animate",
                             "args": [[str(k)], {"frame": {"duration": 0, "redraw": True}, "mode": "immediate"}]}
                            for k in range(1, len(path))]}],
        margin={"b": 110},
    )
    return fig
