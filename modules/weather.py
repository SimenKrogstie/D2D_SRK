"""Hourly ERA5 data from open-meteo. WeatherClient is used by the notebook, WeatherData by the app."""

from pathlib import Path
from typing import ClassVar

import openmeteo_requests
import pandas as pd
import requests_cache
import streamlit as st
from retry_requests import retry

from modules.regions import NVE_REGIONS_SHP, PRICE_AREAS_SHP, region_locations

# Disk cache for the API response, inside the repo
REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO_ROOT / ".cache" / "open_meteo"

# Magasinstatistikk area type -> region name used in modules/regions.py
AREA_TO_REGION = {"EL": "NO{}", "NO": "NO", "VASS": "VASS{}"}


def region_for_area(area_type: str, area_number: int) -> str:
    """E.g. ("EL", 3) -> "NO3", ("NO", 0) -> "NO", ("VASS", 2) -> "VASS2"."""
    return AREA_TO_REGION[area_type].format(area_number)


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
        responses = self.client.weather_api(self.API_URL, params=params)

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
        """One calendar year, averaged over the locations."""
        df = _self.client.download(region, f"{year}-01-01", f"{year}-12-31", n_locations=n_locations)
        return WeatherClient.average(df)
