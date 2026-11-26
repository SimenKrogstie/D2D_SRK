"""Download and preprocessing of reservoir data from the NVE Magasinstatistikk API."""

from typing import ClassVar

import pandas as pd
import requests
import streamlit as st

from modules import state
from modules.forecast import DEFAULTS as FORECAST_DEFAULTS


class ReservoirClient:
    """Client for the NVE Magasinstatistikk API."""

    API_BASE = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk"

    # Norwegian API columns to English
    RENAME_MAP: ClassVar[dict[str, str]] = {
        "dato_Id": "date",
        "omrType": "area_type",
        "omrnr": "area_number",
        "iso_aar": "iso_year",
        "iso_uke": "iso_week",
        "fyllingsgrad": "fill_degree",
        "kapasitet_TWh": "capacity_twh",
        "fylling_TWh": "filling_twh",
        "neste_Publiseringsdato": "next_publish_date",
        "fyllingsgrad_forrige_uke": "fill_degree_prev_week",
        "endring_fyllingsgrad": "change_in_fill_degree",
    }

    DATE_COL = "date"

    # Numerical columns that can be plotted
    VALUE_COLS: ClassVar[list[str]] = [
        "fill_degree",
        "capacity_twh",
        "filling_twh",
        "fill_degree_prev_week",
        "change_in_fill_degree",
    ]

    # API area codes with labels for the sidebar
    AREA_TYPES: ClassVar[dict[str, str]] = {
        "EL": "Price areas (NO1-NO5)",
        "NO": "Norway (national total)",
        "VASS": "Watercourse areas",
    }

    def __init__(self, timeout: int = 60):
        self.timeout = timeout  # Seconds before a request gives up

    def fetch_raw(self) -> pd.DataFrame:
        """All public reservoir data with the original column names (HentOffentligData)."""
        # One request returns every week for every area
        response = requests.get(f"{self.API_BASE}/HentOffentligData", timeout=self.timeout)
        response.raise_for_status()  # Fail on HTTP errors
        return pd.DataFrame(response.json())

    def fetch_all(self) -> pd.DataFrame:
        """All public reservoir data, renamed and with parsed time columns."""
        return self.preprocess(self.fetch_raw())

    @classmethod
    def preprocess(cls, df: pd.DataFrame) -> pd.DataFrame:
        """"Rename the columns, parse the dates and sort the rows."""
        df = df.rename(columns=cls.RENAME_MAP)

        # Date is the last day of the ISO week. next_publish_date uses
        # 0001-01-01 as a placeholder for old rows, which is turned into NaT
        df[cls.DATE_COL] = pd.to_datetime(df[cls.DATE_COL])
        df["next_publish_date"] = pd.to_datetime(df["next_publish_date"], errors="coerce")
        df.loc[df["next_publish_date"].dt.year < 1900, "next_publish_date"] = pd.NaT

        # Chronological order, then by area
        return df.sort_values([cls.DATE_COL, "area_type", "area_number"]).reset_index(drop=True)

    def fetch_areas_raw(self):
        """Area descriptions as returned by HentOmråder."""
        response = requests.get(f"{self.API_BASE}/HentOmråder", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def fetch_area_names(self) -> dict[tuple[str, int], str]:
        """Map (area_type, area_number) to a readable name, empty if the call fails."""
        try:
            areas = self.fetch_areas_raw()
        except (requests.RequestException, ValueError):
            return {}

        names = {}

        # Walk the nested JSON and pick up every object with an area number.
        # The area type is taken from the object itself or from its parent group
        def walk(node, parent_type=None):
            if isinstance(node, list):
                for item in node:
                    walk(item, parent_type)
            elif isinstance(node, dict):
                area_type = node.get("omrType", parent_type)
                if "omrnr" in node and area_type:
                    name = node.get("navn_langt") or node.get("navn") or node.get("beskrivelse")
                    if name:
                        names[(area_type, int(node["omrnr"]))] = str(name)
                for value in node.values():
                    if isinstance(value, (list, dict)):
                        walk(value, area_type)

        walk(areas)
        return names


class ReservoirData:
    """Streamlit-cached access to the reservoir data.

    `_self` keeps the instance out of the cache hash.
    """

    def __init__(self, client: ReservoirClient | None = None):
        self.client = client or ReservoirClient()

    # Full series for the slider optins, cached for a day
    @st.cache_data(ttl="1d", show_spinner="Checking which months NVE has data for...")
    def all(_self) -> pd.DataFrame:
        return _self.client.fetch_all()

    # Each slider interval triggers a download, cached for an hour
    @st.cache_data(ttl="1h", show_spinner="Downloading the chosen interval from NVE...")
    def interval(_self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Download the data and keep only the rows between start and end.

        `HentOffentligData` has no date parameters, so the request returns the full 
        series and the interval is cut out right after downloading.
        """
        df = _self.client.fetch_all()
        mask = (df[ReservoirClient.DATE_COL] >= start) & (df[ReservoirClient.DATE_COL] <= end)
        return df.loc[mask].reset_index(drop=True)

    # Area names rarely change
    @st.cache_data(ttl="1d")
    def area_names(_self) -> dict[tuple[str, int], str]:
        return _self.client.fetch_area_names()

    def area_label(self, area_type: str, area_number: int) -> str:
        """Readable label for one area, falls back to e.g. 'VASS 1' if no name is known."""
        if area_type == "EL":
            return f"NO{area_number}"
        return self.area_names().get((area_type, area_number)) or f"{area_type} {area_number}"

    def months(self) -> list[str]:
        """All months (YYYY-MM) covered by the API, used as slider options."""
        dates = self.all()[ReservoirClient.DATE_COL]
        return [str(p) for p in pd.period_range(dates.min(), dates.max(), freq="M")]

    def area_numbers(self, area_type: str) -> list[int]:
        """Area numbers with data for an area type."""
        df = self.all()
        return sorted(int(n) for n in df.loc[df["area_type"] == area_type, "area_number"].unique())

    def area_series(self, area_type: str, area_number: int, column: str = "fill_degree") -> pd.Series:
        """Full weekly history of one column for one area."""
        df = self.all()
        mask = (df["area_type"] == area_type) & (df["area_number"] == area_number)
        series = df.loc[mask].set_index(ReservoirClient.DATE_COL)[column].sort_index()
        series.name = column
        return series

    def selection(self, area_type: str, month_range: tuple[str, str]) -> pd.DataFrame:
        """Download the chosen interval and keep the chosen area type, with area labels."""
        # Start of first month to end of last month
        start = pd.Period(month_range[0], freq="M").start_time
        end = pd.Period(month_range[1], freq="M").end_time
        df = self.interval(start, end)

        df = df.loc[df["area_type"] == area_type].copy()

        # Readable area name, used in the plot legend and as row name in the table
        df["area"] = [self.area_label(t, n) for t, n in zip(df["area_type"], df["area_number"])]
        return df


class ReservoirControls:
    """Sidebar controls shared by the pages.

    Rendered from app.py, with the values kept in modules/state.py so they persist across
    pages, also pages that don't draw them (e.g. the map sets the area).
    """

    def __init__(self, data: ReservoirData | None = None):
        self.data = data or ReservoirData()

    def render(self, area: bool = False, window: bool = False, column: bool = False) -> None:
        """Draw the sidebar: always the area type, plus the chosen extra controls.

        area: dropdown with one area of the area type.
        window: month range used as download interval, map time and forecast training data.
        column: the Magasinstatistikk column to show.
        """
        with st.sidebar:
            st.header("Selection")

            area_types = list(ReservoirClient.AREA_TYPES)
            st.radio(
                "Area type",
                options=area_types,
                format_func=lambda t: f"{t} - {ReservoirClient.AREA_TYPES[t]}",
                **state.widget("area_type", area_types),
            )

            if area:
                area_type = self.area_type
                numbers = self.data.area_numbers(area_type)
                # Falls back to the first area if the stored one isn't of this area type
                st.selectbox(
                    "Area",
                    options=numbers,
                    format_func=lambda n: self.data.area_label(area_type, n),
                    **state.widget("area_number", numbers),
                )

            if window:
                months = self.data.months()
                kwargs = state.widget("month_range", months, default=self.default_window(months))
                st.select_slider(
                    "Time window",
                    options=months,
                    help="Download interval for the tables and plots, the time shown on the map "
                         "(the last month) and the training data for the forecast.",
                    **kwargs,
                )

            if column:
                columns = list(ReservoirClient.VALUE_COLS)
                st.selectbox("Column", options=columns, **state.widget("value_col", columns))

    @staticmethod
    def default_window(months: list[str]) -> tuple[str, str]:
        """The history length of the default forecast setting, ending in the last month."""
        n = int(FORECAST_DEFAULTS["history_years"] * 12)
        return months[-min(n, len(months))], months[-1]

    # Sidebar values, so the state keys live in one place
    @property
    def area_type(self) -> str:
        return state.get("area_type")

    @property
    def month_range(self) -> tuple[str, str]:
        stored = state.get("month_range")
        if stored is None:
            return self.default_window(self.data.months())
        return tuple(stored)

    @property
    def value_col(self) -> str:
        return state.get("value_col", ReservoirClient.VALUE_COLS[0])

    @property
    def area_number(self) -> int:
        numbers = self.data.area_numbers(self.area_type)
        stored = state.get("area_number")
        return stored if stored in numbers else numbers[0]

    def select_area(self, area_type: str, area_number: int) -> None:
        """Store an area chosen outside the sidebar, e.g. by a click on the map."""
        state.set("area_type", area_type)
        state.set("area_number", area_number)

    @property
    def area_label(self) -> str:
        return self.data.area_label(self.area_type, self.area_number)

    def selected_data(self) -> pd.DataFrame:
        """ The data matching the current sidebar choices"""
        return self.data.selection(self.area_type, self.month_range)
