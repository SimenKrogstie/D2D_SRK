"""Download and preprocessing of reservoir data from the NVE Magasinstatistikk API."""

import pandas as pd
import requests
import streamlit as st


class ReservoirClient:
    """Client for the NVE Magasinstatistikk API."""

    API_BASE = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk"

    # Norwegian API columns to English
    RENAME_MAP = {
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

    VALUE_COLS = [
        "fill_degree",
        "capacity_twh",
        "filling_twh",
        "fill_degree_prev_week",
        "change_in_fill_degree",
    ]

    AREA_TYPES = {
        "EL": "Price areas (NO1-NO5)",
        "NO": "Norway (national total)",
        "VASS": "Watercourse areas",
    }

    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    def fetch_raw(self) -> pd.DataFrame:
        """All public reservoir data with the original column names (HentOffentligData)."""
        # One request returns every week for every area
        response = requests.get(f"{self.API_BASE}/HentOffentligData", timeout=self.timeout)
        response.raise_for_status() # Fail on HTTP errors
        return pd.DataFrame(response.json())

    def fetch_all(self) -> pd.DataFrame:
        """All public reservoir data, renamed and with parsed time columns."""
        return self.preprocess(self.fetch_raw())

    @classmethod
    def preprocess(cls, df: pd.DataFrame) -> pd.DataFrame:
        df = df.rename(columns=cls.RENAME_MAP)

        # Date is the last day of the ISO week. next_publish_date uses
        # 0001-01-01 as a placeholder for old rows, which is turned into NaT
        df[cls.DATE_COL] = pd.to_datetime(df[cls.DATE_COL])
        df["next_publish_date"] = pd.to_datetime(df["next_publish_date"], errors="coerce")
        df.loc[df["next_publish_date"].dt.year < 1900, "next_publish_date"] = pd.NaT

        # Sorting API rows in chronological order and then by area
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
        """Download the data and keep only the rows between start and end (inclusive).

        HentOffentligData has no date parameters, so the request returns the full 
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
    """Sidebar controls shared by the reservoir pages.

    Rendered from app.py so choises persist across pages.
    """

    ALL_COLUMNS = "All columns"

    def __init__(self, data: ReservoirData | None = None):
        self.data = data or ReservoirData()

    def render(self, allow_all_columns: bool = False) -> None:
        """Draw the sidebar. allow_all_columns adds "All columns" to the column dropdown,
        used on the plot page only since the table's sparkline shows one column."""
        with st.sidebar:
            st.header("Reservoir data")

            st.radio(
                "Area type",
                options=list(ReservoirClient.AREA_TYPES),
                format_func=lambda t: f"{t} - {ReservoirClient.AREA_TYPES[t]}",
                key="area_type",
            )

            # The slider decides which interval of data is downloaded and shown
            months = self.data.months()
            # Drop a stored value that is not a (start, end) pair, e.g. from an older session
            stored = st.session_state.get("month_range")
            if stored is not None and not (isinstance(stored, (tuple, list)) and len(stored) == 2):
                del st.session_state["month_range"]
            # Range slider, defaults to the last 12 months
            st.select_slider(
                "Download interval",
                options=months,
                value=(months[-12], months[-1]),
                key="month_range",
            )

            # Dropdown for the column to show, with "All columns" first on the plot page
            columns = list(ReservoirClient.VALUE_COLS)
            if allow_all_columns:
                columns = [self.ALL_COLUMNS] + columns
            elif st.session_state.get("value_col") == self.ALL_COLUMNS:
                del st.session_state["value_col"]
            st.selectbox("Column", options=columns, key="value_col")

    # Sidebar values, so sessiuon-_state keys live in one place
    @property
    def area_type(self) -> str:
        return st.session_state["area_type"]

    @property
    def month_range(self) -> tuple[str, str]:
        return st.session_state["month_range"]

    @property
    def value_col(self) -> str:
        return st.session_state["value_col"]

    def selected_data(self) -> pd.DataFrame:
        """ The data matching the current sidebar choices"""
        return self.data.selection(self.area_type, self.month_range)
