"""Hourly ERA5 data from open-meteo. WeatherClient is used by the notebook, WeatherData by the app."""

import time
from pathlib import Path
from typing import ClassVar

import openmeteo_requests
import pandas as pd
import requests_cache
import streamlit as st
from openmeteo_requests.Client import OpenMeteoRequestsError
from retry_requests import retry

from modules.regions import NVE_REGIONS_SHP, PRICE_AREAS_SHP, region_locations

# Disk cache for the API response, inside the repo
REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO_ROOT / ".cache" / "open_meteo"

# Magasinstatistikk area type -> region name used in modules/regions.py
AREA_TO_REGION = {"EL": "NO{}", "NO": "NO", "VASS": "VASS{}"}

# Locations averaged per region for the weekly analyses (correlation, forecast). One point
# of the 25 km ERA5 grid says little about a whole region, and the disk cache makes the
# extra quota a one-off cost
DEFAULT_LOCATIONS = 5


def region_for_area(area_type: str, area_number: int) -> str:
    """E.g. ("EL", 3) -> "NO3", ("NO", 0) -> "NO", ("VASS", 2) -> "VASS2"."""
    return AREA_TO_REGION[area_type].format(area_number)


# Label, unit and how hours are combined into days/weeks/months. Wind direction is left
# out, since an average of angles is meaningless
VARIABLE_INFO: dict[str, tuple[str, str, str]] = {
    "temperature_2m": ("Temperature", "°C", "mean"),
    "precipitation": ("Precipitation", "mm", "sum"),
    "rain": ("Rain", "mm", "sum"),
    "snowfall": ("Snowfall", "cm", "sum"),
    "relative_humidity_2m": ("Relative humidity", "%", "mean"),
    "wind_speed_10m": ("Wind speed", "m/s", "mean"),
    "wind_gusts_10m": ("Wind gusts", "m/s", "mean"),
    "et0_fao_evapotranspiration": ("Evapotranspiration (ET₀)", "mm", "sum"),
}

# Magasinstatistikk weeks and Norges Bank dates follow Norwegian time
LOCAL_TZ = "Europe/Oslo"


def variable_label(variable: str, with_unit: bool = True) -> str:
    label, unit, _ = VARIABLE_INFO.get(variable, (variable, "", "mean"))
    return f"{label} ({unit})" if with_unit and unit else label


def aggregate(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Hourly UTC data (tz-naive index) to days, weeks or months in Norwegian time.

    Days come first, so that a W-SUN week holds Monday to Sunday (resampling the hours
    directly would put Sunday's hours in the next week).
    """
    columns = [c for c in df.columns if c in VARIABLE_INFO]
    rules = {c: VARIABLE_INFO[c][2] for c in columns}
    local = df[columns].copy()
    local.index = pd.DatetimeIndex(local.index).tz_localize("UTC").tz_convert(LOCAL_TZ).tz_localize(None)
    daily = local.resample("D").agg(rules)
    if freq == "D":
        return daily
    # A period with no hours at all is NaN, not 0
    counts = local.resample("D").size().resample(freq).sum()
    result = daily.resample(freq).agg(rules)
    return result.loc[counts > 0]


def area_for_region(region: str) -> tuple[str, int]:
    """Inverse of region_for_area: "NO3" -> ("EL", 3), "VASS2" -> ("VASS", 2), "NO" -> ("NO", 0)."""
    if region == "NO":
        return "NO", 0
    if region.startswith("VASS"):
        return "VASS", int(region[4:])
    return "EL", int(region[2:])


class WeatherClient:
    """open-meteo archive API with the ERA5 model."""

    API_URL = "https://archive-api.open-meteo.com/v1/archive"
    MODEL = "era5"

    VARIABLES: ClassVar[list[str]] = [
        "temperature_2m",
        "precipitation",
        "rain",
        "snowfall",
        "relative_humidity_2m",
        "wind_speed_10m",
        "wind_gusts_10m",
        "wind_direction_10m",
        "et0_fao_evapotranspiration",
    ]

    # ERA5 grid in degrees
    GRID = 0.25

    def __init__(self):
        # Historical data doesn't change, so the disk cache never expires
        session = requests_cache.CachedSession(str(CACHE_PATH), expire_after=-1)
        retry_session = retry(session, retries=5, backoff_factor=0.5)
        self.client = openmeteo_requests.Client(session=retry_session)  # pyright: ignore[reportArgumentType]

    def locations(self, region: str) -> pd.DataFrame:
        """The 1000 sampled lon/lat pairs for a region."""
        locations = region_locations()
        selected = locations.loc[locations["region"] == region, ["lon", "lat"]]
        if selected.empty:
            raise ValueError(f"No locations for region '{region}'")
        return selected.reset_index(drop=True)

    def _request(self, params: dict, attempts: int = 3) -> list:
        """The API call, waiting out the per-minute limit of the free tier.

        Other API errors become ConnectionError (an OSError), which theme.data_guard shows as a
        warning; the client's own error class is a plain Exception.
        """
        for attempt in range(attempts):
            try:
                return self.client.weather_api(self.API_URL, params=params)
            except OpenMeteoRequestsError as error:
                if "minutely" in str(error).lower() and attempt < attempts - 1:
                    time.sleep(61)
                    continue
                raise ConnectionError(f"open-meteo refused the request: {error}") from error
        raise AssertionError("unreachable")

    def download(
        self,
        region: str,
        start: str,
        end: str,
        n_locations: int = 1,
        seed: int = 0,
        variables: list[str] | None = None,
    ) -> pd.DataFrame:
        """Hourly data for random locations in a region, start and end as "YYYY-MM-DD".

        One location by default, since the free API quota runs out quickly.
        """
        variables = variables or self.VARIABLES

        # Same seed gives same locations
        # Skip locations in a grid cell that is already picked
        picked = self.locations(region).sample(n=n_locations, random_state=seed)
        cells = (picked / self.GRID).round()
        picked = picked.loc[~cells.duplicated()]

        params = {
            "latitude": picked["lat"].tolist(),
            "longitude": picked["lon"].tolist(),
            "start_date": start,
            "end_date": end,
            "hourly": variables,
            "models": self.MODEL,
            "timezone": "GMT",
        }
        # One request for all locations, one response per location
        responses = self._request(params)

        frames = []
        for location, response in enumerate(responses):
            hourly = response.Hourly()
            if hourly is None:
                raise ValueError("The response has no hourly data.")
            # Timestamps from the start, end and step in the response
            times = pd.date_range(
                start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
                end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
                freq=pd.Timedelta(seconds=hourly.Interval()),
                inclusive="left",
            )
            frame = pd.DataFrame({"time": times.tz_localize(None)})
            # Variables come back in the requested order
            for i, name in enumerate(variables):
                variable = hourly.Variables(i)
                if variable is None:
                    raise ValueError(f"The response has no data for {name}")
                frame[name] = variable.ValuesAsNumpy()
            # lat/lon of the grid cell, not the requested point
            frame.insert(0, "location", location)
            frame.insert(1, "lat", response.Latitude())
            frame.insert(2, "lon", response.Longitude())
            frames.append(frame)

        df = pd.concat(frames, ignore_index=True)
        df.insert(0, "region", region)
        return df

    @staticmethod
    def average(df: pd.DataFrame) -> pd.DataFrame:
        """Hourly average over the locations."""
        values = df.drop(columns=["region", "location", "lat", "lon"])
        return values.groupby("time").mean()

    def download_years(self, region: str, first: int, last: int, n_locations: int = 1) -> pd.DataFrame:
        """Hourly averages for whole years, one request per year.

        The free API weighs a request by locations times days, and many years for several
        locations in one request goes over the per-minute limit. The years are also the same
        requests as WeatherData.year in the app, so the disk cache is shared.
        """
        frames = []
        for year in range(first, last + 1):
            end = min(pd.Timestamp(f"{year}-12-31"), WeatherData.last_available())
            frames.append(self.average(self.download(region, f"{year}-01-01", end.strftime("%Y-%m-%d"),
                                                     n_locations=n_locations)))
        return pd.concat(frames).sort_index()


class WeatherData:
    """Cached downloads for the app. 
    
    `_self` keeps the instance out of the cache key.
    """

    def __init__(self, client: WeatherClient | None = None):
        self.client = client or WeatherClient()

    @staticmethod
    def available() -> bool:
        """The locations are sampled from the Atlas shapefiles in data/."""
        return PRICE_AREAS_SHP.exists() and NVE_REGIONS_SHP.exists()

    @st.cache_data(ttl="1d", show_spinner="Downloading ERA5 weather data from open-meteo...")
    def year(_self, region: str, year: int, n_locations: int = 1) -> pd.DataFrame:
        """One calendar year, averaged over the locations.

        The current year stops a week ago, since ERA5 is published with about five days' delay.
        """
        return _self.client.download_years(region, year, year, n_locations)

    def years(self, region: str, first: int, last: int, n_locations: int = 1) -> pd.DataFrame:
        """Several years, one cached request per year so overlapping ranges reuse downloads."""
        frames = [self.year(region, y, n_locations) for y in range(first, last + 1)]
        return pd.concat(frames).sort_index()

    @staticmethod
    def last_available() -> pd.Timestamp:
        """Last day the year() downloads include."""
        return pd.Timestamp.now().normalize() - pd.Timedelta(days=7)
