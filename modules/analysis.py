"""Outlier, anomaly and time series analyses, shared by the notebook and the app."""
 
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.fft import dct, idct
from scipy.signal import spectrogram as scipy_spectrogram
from sklearn.neighbors import LocalOutlierFactor
from statsmodels.tsa.seasonal import STL
 
OUTLIER_COLOR = "crimson"
 
 
def precipitation_outliers(
    series: pd.Series, cutoff_days: float = 30.0, n_std: float = 4.0
) -> tuple[go.Figure, dict]:
    """SPC outliers in daily precipitation, with limits from the DCT high-passed SATV.
 
    Hourly data is summed to days first. Most hours are dry, which makes the MAD
    almost zero and flags every rainy hour as an outlier.
    """
    daily = series.astype(float).resample("D").sum()
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
    lower = np.clip(seasonal + median - n_std * sigma, 0, None)  # No negative precipitation
 
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily.index, y=x, mode="lines", name="Precipitation",
                             line={"width": 1}))
    fig.add_trace(go.Scatter(x=daily.index, y=upper, mode="lines", name=f"Upper limit (+{n_std}σ)",
                             line={"dash": "dash", "color": "gray"}))
    fig.add_trace(go.Scatter(x=daily.index, y=lower, mode="lines", name=f"Lower limit (-{n_std}σ)",
                             line={"dash": "dash", "color": "gray"}))
    fig.add_trace(go.Scatter(x=daily.index[is_outlier], y=x[is_outlier], mode="markers",
                             name="Outliers", marker={"color": OUTLIER_COLOR, "size": 7}))
    fig.update_layout(title=f"Daily precipitation with SPC limits (cut-off {cutoff_days} days, {n_std} σ)",
                      xaxis_title="Date", yaxis_title="Precipitation (mm/day)")
 
    table = pd.DataFrame({
        "date": daily.index[is_outlier],
        "precipitation": x[is_outlier],
        "lower_limit": lower[is_outlier],
        "upper_limit": upper[is_outlier],
    }).sort_values("precipitation", ascending=False, ignore_index=True)
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
 
 
def temperature_anomalies(
    series: pd.Series, contamination: float = 0.01, n_neighbors: int = 20
) -> tuple[go.Figure, dict]:
    """Temperature anomalies with the Local Outlier Factor.
 
    LOF runs on standardised time and temperature, so an hour is an anomaly when it
    stands out from the hours around it, not just for being cold in winter.
    """
    x = series.astype(float).to_numpy()
    hours = (series.index - series.index[0]) / pd.Timedelta(hours=1)
    features = np.column_stack([np.asarray(hours, dtype=float), x])
    features = (features - features.mean(axis=0)) / features.std(axis=0)

    # LOF
    lof = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
    is_anomaly = lof.fit_predict(features) == -1
    score = -lof.negative_outlier_factor_
 
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=x, mode="lines", name="Temperature",
                             line={"width": 1}))
    fig.add_trace(go.Scatter(x=series.index[is_anomaly], y=x[is_anomaly], mode="markers",
                             name="Anomalies (LOF)", marker={"color": OUTLIER_COLOR, "size": 6}))
    fig.update_layout(title=f"Temperature with LOF anomalies (proportion {contamination:.1%})",
                      xaxis_title="Time", yaxis_title="Temperature (°C)")
 
    table = pd.DataFrame({
        "time": series.index[is_anomaly],
        "temperature": x[is_anomaly],
        "lof_score": score[is_anomaly],
    }).sort_values("lof_score", ascending=False, ignore_index=True)
    summary = {
        "n_anomalies": int(is_anomaly.sum()),
        "share": float(is_anomaly.mean()),
        "anomalies": table,
    }
    return fig, summary
 
 
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