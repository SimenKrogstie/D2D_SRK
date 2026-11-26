"""Outlier, anomaly and time series analyses, shared by the notebook and the app."""
 
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.fft import dct, idct
from scipy.signal import spectrogram as scipy_spectrogram
from sklearn.neighbors import LocalOutlierFactor
from statsmodels.tsa.seasonal import STL

from modules.weather import VARIABLE_INFO, variable_label
 
OUTLIER_COLOR = "crimson"

# Variables that can't be negative, so the lower SPC limit is clipped at 0
NON_NEGATIVE = {"precipitation", "rain", "snowfall", "relative_humidity_2m", "wind_speed_10m",
                "wind_gusts_10m", "et0_fao_evapotranspiration"}


def spc_outliers(
    series: pd.Series, variable: str | None = None, cutoff_days: float = 30.0, n_std: float = 4.0
) -> tuple[go.Figure, dict]:
    """SPC outliers in a daily weather variable, with limits from the DCT high-passed SATV.

    Hourly data is combined to days first (summed or averaged, see VARIABLE_INFO). For
    precipitation most hours are dry, which makes the MAD almost zero and flags every rainy
    hour as an outlier.
    """
    variable = variable or str(series.name)
    label, unit, rule = VARIABLE_INFO.get(variable, (variable, "", "mean"))
    daily = series.astype(float).resample("D").agg(rule).dropna()
    if len(daily) < 2:
        raise ValueError("Too little data for SPC (needs at least two days)")
    x = daily.to_numpy()
    n = len(x)
 
    # DCT coefficient k has period 2n/k days, so zeroing everything above k_cutoff
    # leaves the slow (seasonal) part
    coefficients = np.asarray(dct(x, type=2, norm="ortho"))
    k_cutoff = int(np.ceil(2 * n / cutoff_days))
    coefficients[k_cutoff:] = 0
    seasonal = np.asarray(idct(coefficients, type=2, norm="ortho"))
    satv = x - seasonal
 
    # Robust sigma from the MAD, so the outliers don't widen their own limits
    median = np.median(satv)
    sigma = 1.4826 * np.median(np.abs(satv - median))
    if sigma == 0:
        sigma = satv.std()
    is_above = satv > median + n_std * sigma
    is_below = satv < median - n_std * sigma
    is_outlier = is_above | is_below
 
    upper = seasonal + median + n_std * sigma
    lower = seasonal + median - n_std * sigma
    if variable in NON_NEGATIVE:
        lower = np.clip(lower, 0, None)

    per_day = f"{unit}/day" if rule == "sum" else unit
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily.index, y=x, mode="lines", name=label,
                             line={"width": 1}))
    fig.add_trace(go.Scatter(x=daily.index, y=upper, mode="lines", name=f"Upper limit (+{n_std}σ)",
                             line={"dash": "dash", "color": "gray"}))
    fig.add_trace(go.Scatter(x=daily.index, y=lower, mode="lines", name=f"Lower limit (-{n_std}σ)",
                             line={"dash": "dash", "color": "gray"}))
    fig.add_trace(go.Scatter(x=daily.index[is_outlier], y=x[is_outlier], mode="markers",
                             name="Outliers", marker={"color": OUTLIER_COLOR, "size": 7}))
    fig.update_layout(title=f"Daily {label.lower()} with SPC limits (cut-off {cutoff_days} days, {n_std} σ)",
                      xaxis_title="Date", yaxis_title=f"{label} ({per_day})")

    # Largest deviation from the seasonal part first
    table = pd.DataFrame({
        "date": daily.index[is_outlier],
        variable: x[is_outlier],
        "lower_limit": lower[is_outlier],
        "upper_limit": upper[is_outlier],
        "deviation": np.abs(satv - median)[is_outlier],
    }).sort_values("deviation", ascending=False, ignore_index=True)
    summary = {
        "n_outliers": int(is_outlier.sum()),
        "share": float(is_outlier.mean()),
        "n_above": int(is_above.sum()),
        "n_below": int(is_below.sum()),
        "satv_median": float(median),
        "satv_sigma": float(sigma),
        "outliers": table,
    }
    return fig, summary
 
 
def precipitation_outliers(
    series: pd.Series, cutoff_days: float = 30.0, n_std: float = 4.0
) -> tuple[go.Figure, dict]:
    """SPC on precipitation, kept so the part 3 notebook still runs."""
    return spc_outliers(series, "precipitation", cutoff_days, n_std)


def lof_anomalies(
    series: pd.Series, variable: str | None = None, contamination: float = 0.01, n_neighbors: int = 20
) -> tuple[go.Figure, dict]:
    """Anomalies in an hourly weather variable with the Local Outlier Factor.

    LOF runs on standardised time and value, so an hour is an anomaly when it stands out
    from the hours around it, not just for being cold in winter.
    """
    variable = variable or str(series.name)
    label, unit, _ = VARIABLE_INFO.get(variable, (variable, "", "mean"))
    series = series.astype(float).dropna()
    if len(series) <= n_neighbors:
        raise ValueError(f"LOF needs more hours of data than neighbours ({n_neighbors})")
    x = series.to_numpy()
    hours = (series.index - series.index[0]) / pd.Timedelta(hours=1)
    features = np.column_stack([np.asarray(hours, dtype=float), x])
    # A constant column would divide by zero
    std = features.std(axis=0)
    features = (features - features.mean(axis=0)) / np.where(std == 0, 1, std)

    # LOF
    lof = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
    is_anomaly = lof.fit_predict(features) == -1
    score = -lof.negative_outlier_factor_
 
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=x, mode="lines", name=label,
                             line={"width": 1}))
    fig.add_trace(go.Scatter(x=series.index[is_anomaly], y=x[is_anomaly], mode="markers",
                             name="Anomalies (LOF)", marker={"color": OUTLIER_COLOR, "size": 6}))
    fig.update_layout(title=f"{label} with LOF anomalies (proportion {contamination:.1%})",
                      xaxis_title="Time", yaxis_title=f"{label} ({unit})" if unit else label)

    table = pd.DataFrame({
        "time": series.index[is_anomaly],
        variable: x[is_anomaly],
        "lof_score": score[is_anomaly],
    }).sort_values("lof_score", ascending=False, ignore_index=True)
    summary = {
        "n_anomalies": int(is_anomaly.sum()),
        "share": float(is_anomaly.mean()),
        "anomalies": table,
    }
    return fig, summary


def temperature_anomalies(
    series: pd.Series, contamination: float = 0.01, n_neighbors: int = 20
) -> tuple[go.Figure, dict]:
    """LOF on temperature, kept so the part 3 notebook still runs."""
    return lof_anomalies(series, "temperature_2m", contamination, n_neighbors)


def sliding_window_correlation(
    weather: pd.Series, reservoir: pd.Series, window: int = 26, lag: int = 0
) -> tuple[go.Figure, dict]:
    """Rolling Pearson correlation between two weekly series, with the weather leading.

    lag shifts the weather `lag` weeks forward, so the correlation at week t compares the
    reservoir at t with the weather at t - lag (e.g. snow that melts months later).
    """
    if window < 3:
        raise ValueError("The window must be at least 3 weeks")
    df = pd.concat({"weather": weather.shift(lag, freq="W-SUN"), "reservoir": reservoir},
                   axis=1, join="inner").dropna()
    if len(df) < window:
        raise ValueError(f"Too few overlapping weeks ({len(df)}) for a {window}-week window")
    correlation = df["weather"].rolling(window).corr(df["reservoir"])

    weather_name, reservoir_name = str(weather.name), str(reservoir.name)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.55, 0.45],
                        subplot_titles=["Standardised series", f"Correlation ({window}-week window)"])
    for column, name in [("weather", f"{variable_label(weather_name, False)} (lag {lag} w)"),
                         ("reservoir", reservoir_name)]:
        values = df[column]
        fig.add_trace(go.Scatter(x=df.index, y=(values - values.mean()) / values.std(), mode="lines",
                                 name=name), row=1, col=1)
    fig.add_trace(go.Scatter(x=correlation.index, y=correlation, mode="lines", name="Correlation",
                             fill="tozeroy"), row=2, col=1)
    fig.add_hline(y=0, line={"color": "gray", "width": 1}, row=2, col=1)
    fig.update_yaxes(range=[-1.05, 1.05], title_text="r", row=2, col=1)
    fig.update_yaxes(title_text="z-score", row=1, col=1)
    fig.update_layout(height=650, hovermode="x unified",
                      title=f"Sliding window correlation, {variable_label(weather_name, False)} vs {reservoir_name}")

    summary = {
        "overall": float(df["weather"].corr(df["reservoir"])),
        "mean": float(correlation.mean()),
        "min": float(correlation.min()),
        "max": float(correlation.max()),
        "n_weeks": len(df),
        "correlation": correlation.dropna(),
    }
    return fig, summary
 
 
def lag_correlation(weather: pd.Series, reservoir: pd.Series, max_lag: int = 30,
                    current_lag: int | None = None) -> tuple[go.Figure, pd.Series]:
    """Overall Pearson correlation for every lag from 0 to max_lag weeks (weather leading).

    Shows at which lead time the weather says most about the reservoir, which is the lag
    worth giving a forecast model.
    """
    lags = range(max_lag + 1)
    values = []
    for lag in lags:
        df = pd.concat({"weather": weather.shift(lag, freq="W-SUN"), "reservoir": reservoir},
                       axis=1, join="inner").dropna()
        values.append(df["weather"].corr(df["reservoir"]) if len(df) > 2 else np.nan)
    correlation = pd.Series(values, index=pd.Index(lags, name="lag_weeks"), name="r")
    if correlation.isna().all():
        raise ValueError("Too few overlapping weeks to correlate")

    best = int(correlation.abs().idxmax())
    fig = go.Figure(go.Bar(x=correlation.index, y=correlation, name="r",
                           hovertemplate="Lag %{x} weeks: r = %{y:.2f}<extra></extra>"))
    fig.add_annotation(x=best, y=correlation[best], text=f"Strongest: {best} w (r = {correlation[best]:.2f})",
                       showarrow=True, arrowhead=2, yshift=10 if correlation[best] >= 0 else -10)
    if current_lag is not None:
        fig.add_vline(x=current_lag, line={"color": "gray", "dash": "dash"})
    fig.update_layout(title=f"Overall correlation by lag, {variable_label(str(weather.name), False)} "
                            f"vs {reservoir.name}",
                      xaxis_title="Lag (weeks the weather leads)", yaxis_title="r", yaxis_range=[-1, 1],
                      height=350, showlegend=False)
    return fig, correlation


def _weekly(series: pd.Series) -> pd.Series:
    """Evenly spaced weekly series, with gaps interpolated."""
    return series.sort_index().resample("W").mean().interpolate()
 
 
def stl_decomposition(
    series: pd.Series, period: int = 52, seasonal: int = 13, trend: int = 105, robust: bool = True
) -> go.Figure:
    """STL of a weekly series. The smoother lengths are in weeks and must be odd."""
    if seasonal % 2 == 0 or trend % 2 == 0:
        raise ValueError("The seasonal and trend smoothers must be odd numbers")
    if trend <= period:
        raise ValueError(f"The trend smoother must be longer than the period ({period})")
 
    weekly = _weekly(series)
    if len(weekly) < 2 * period:
        raise ValueError(f"STL needs at least two periods of data ({2 * period} weeks)")
    result = STL(weekly, period=period, seasonal=seasonal, trend=trend, robust=robust).fit()
 
    components = {"Observed": result.observed, "Trend": result.trend,
                  "Seasonal": result.seasonal, "Residual": result.resid}
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, subplot_titles=list(components))
    for row, (name, values) in enumerate(components.items(), start=1):
        fig.add_trace(go.Scatter(x=weekly.index, y=values, mode="lines", name=name,
                                 showlegend=False), row=row, col=1)
    fig.update_layout(height=800, title=(f"STL of {series.name or 'series'} "
                                         f"(seasonal={seasonal}, trend={trend}, robust={robust})"))
    return fig
 
 
def spectrogram(series: pd.Series, window_weeks: int = 104, overlap_weeks: int = 78) -> go.Figure:
    """Spectrogram of a weekly series, with frequencies in cycles per year."""
    if overlap_weeks >= window_weeks:
        raise ValueError("The window overlap must be shorter than the window length")
 
    weekly = _weekly(series)
    if len(weekly) < window_weeks:
        raise ValueError(f"The series is shorter than the window ({window_weeks} weeks)")
 
    # Weeks per year, so frequencies are in cycles per year and times in years.
    # fs=52 would make the dates drift about 1.25 days per year
    weeks_per_year = 365.25 / 7
    frequencies, times, power = scipy_spectrogram(
        weekly.to_numpy(), fs=weeks_per_year, nperseg=window_weeks, noverlap=overlap_weeks,
        detrend="constant",
    )
    centres = weekly.index[0] + pd.to_timedelta(times * 365.25, unit="D")
 
    fig = go.Figure(go.Heatmap(x=centres, y=frequencies, z=10 * np.log10(power + 1e-12),
                               colorscale="Viridis", colorbar={"title": "Power (dB)"}))
    fig.update_layout(title=(f"Spectrogram of {series.name or 'series'} "
                             f"(window {window_weeks} weeks, overlap {overlap_weeks} weeks)"),
                      xaxis_title="Time (window centre)", yaxis_title="Frequency (cycles per year)")
    return fig