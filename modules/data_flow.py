"""Cross-border power flows between Norway and its neighbours."""

import time
import xml.etree.ElementTree as ET

import pandas as pd
import pymongo
import requests
import streamlit as st


class EntsoeClient:
    """Client for cross-border flows from the ENTSO-E Transparency Platform."""

    API_URL = "https://web-api.tp.entsoe.eu/api"

    # EIC codes of the bidding zones
    ZONES = {
        "NO1": "10YNO-1--------2",
        "NO2": "10YNO-2--------T",
        "NO3": "10YNO-3--------J",
        "NO4": "10YNO-4--------9",
        "NO5": "10Y1001A1001A48H",
        "SE1": "10Y1001A1001A44P",
        "SE2": "10Y1001A1001A45N",
        "SE3": "10Y1001A1001A46L",
        "FI": "10YFI-1--------U",
        "DK1": "10YDK-1--------W",
        "NL": "10YNL----------L",
        "DE_LU": "10Y1001A1001A82H",
        "GB": "10YGB----------A",
    }

    # Norwegian borders as (Norwegian zone, foreign zone)
    CONNECTIONS = [
        ("NO1", "SE3"),
        ("NO3", "SE2"),
        ("NO4", "SE1"),
        ("NO4", "SE2"),
        ("NO4", "FI"),
        ("NO2", "DK1"),
        ("NO2", "NL"),
        ("NO2", "DE_LU"),
        ("NO2", "GB"),
    ]

    RESOLUTIONS = {"PT15M": "15min", "PT30M": "30min", "PT60M": "60min"}

    def __init__(self, token: str, pause: float = 0.5, timeout: int = 120):
        self.token = token
        self.pause = pause  # Seconds between requests (rate limit)
        self.timeout = timeout

    @classmethod
    def parse(cls, xml_text: str) -> pd.Series:
        """Parse an A11 XML document into MW values indexed by UTC time.

        - Resolution is read per period
        - Curve type A03 only lists points where the value changes, so missing positions
          are forward-filled.
        - An Acknowledgement means no data (empty Series).
        """
        root = ET.fromstring(xml_text)

        # "{*}" matches any namespace version
        if root.tag.endswith("Acknowledgement_MarketDocument"):
            return pd.Series(dtype=float)

        parts = []
        for period in root.iterfind(".//{*}TimeSeries/{*}Period"):
            start = pd.Timestamp(period.find("{*}timeInterval/{*}start").text)
            end = pd.Timestamp(period.find("{*}timeInterval/{*}end").text)
            freq = cls.RESOLUTIONS[period.find("{*}resolution").text]

            # Every timestamp in the period, so missing positions can be filled
            index = pd.date_range(start, end, freq=freq, inclusive="left")
            values = pd.Series(index=range(1, len(index) + 1), dtype=float)
            for point in period.iterfind("{*}Point"):
                values[int(point.find("{*}position").text)] = float(point.find("{*}quantity").text)

            parts.append(pd.Series(values.ffill().to_numpy(), index=index))

        if not parts:
            return pd.Series(dtype=float)
        return pd.concat(parts).sort_index()

    def fetch(self, out_zone: str, in_zone: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
        """Flow from out_zone to in_zone, fetched in chunks of up to one year."""
        chunks = []
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + pd.DateOffset(years=1), end)
            params = {
                "securityToken": self.token,
                "documentType": "A11",
                "out_Domain": self.ZONES[out_zone],
                "in_Domain": self.ZONES[in_zone],
                "periodStart": chunk_start.strftime("%Y%m%d%H%M"),
                "periodEnd": chunk_end.strftime("%Y%m%d%H%M"),
            }
            response = requests.get(self.API_URL, params=params, timeout=self.timeout)
            # "No data" may come back as 400
            if response.status_code not in (200, 400):
                response.raise_for_status()
            chunks.append(self.parse(response.text))

            chunk_start = chunk_end
            time.sleep(self.pause)

        chunks = [c for c in chunks if not c.empty]
        if not chunks:
            return pd.Series(dtype=float)
        flows = pd.concat(chunks)
        return flows[~flows.index.duplicated()].sort_index()

    def fetch_all(self, start: pd.Timestamp, end: pd.Timestamp, verbose: bool = True) -> pd.DataFrame:
        """Hourly flows in both directions for all connections, as one long DataFrame.

        Directions without data are skipped.
        """
        frames = []
        for no_zone, foreign_zone in self.CONNECTIONS:
            connection = f"{no_zone}-{foreign_zone}"

            # Export and import
            for out_zone, in_zone in [(no_zone, foreign_zone), (foreign_zone, no_zone)]:
                flows = self.fetch(out_zone, in_zone, start, end)
                if flows.empty:
                    if verbose:
                        print(f"{out_zone} -> {in_zone}: no data, skipped")
                    continue

                # Average to hourly MW. The energy in an hour (MWh) equals the hourly mean MW times 1 h
                hourly = flows.resample("1h").mean().dropna()
                frames.append(
                    pd.DataFrame(
                        {
                            "connection": connection,
                            "direction": f"{out_zone} -> {in_zone}",
                            "from_zone": out_zone,
                            "to_zone": in_zone,
                            "time": hourly.index,
                            "flow_mw": hourly.to_numpy(),
                            "energy_mwh": hourly.to_numpy() * 1.0,
                        }
                    )
                )
                if verbose:
                    print(f"{out_zone} -> {in_zone}: {len(hourly)} hours")

        df = pd.concat(frames, ignore_index=True)

        # Naive UTC times, the year is part of the Cassandra partition key
        df["time"] = df["time"].dt.tz_convert("UTC").dt.tz_localize(None)
        df["year"] = df["time"].dt.year
        return df


class FlowRepository:
    """Cross-border flows in MongoDB (ind320.collection cross_border_flows)."""

    DB_NAME = "ind320"
    COLLECTION = "cross_border_flows"

    def __init__(self, uri: str):
        # The client keeps a connection pool
        self.client = pymongo.MongoClient(uri)
        self.collection = self.client[self.DB_NAME][self.COLLECTION]

    def ping(self) -> None:
        """Fails if the URI or the IP access list is wrong."""
        self.client.admin.command("ping")

    def replace_all(self, df: pd.DataFrame) -> int:
        """Replace the collection content with df, so re-running does not duplicate data."""
        self.collection.delete_many({})
        self.collection.insert_many(df.to_dict("records"), ordered=False)

        # Index matching the query from the app
        self.collection.create_index(
            [("connection", pymongo.ASCENDING), ("year", pymongo.ASCENDING),
             ("month", pymongo.ASCENDING), ("time", pymongo.ASCENDING)]
        )
        return self.collection.count_documents({})

    # Widget optinons
    def connections(self) -> list[str]:
        return sorted(self.collection.distinct("connection"))

    def years(self, connection: str) -> list[int]:
        return sorted(self.collection.distinct("year", {"connection": connection}))

    def flows(self, connection: str, year: int, months: tuple[int, ...] | None = None) -> pd.DataFrame:
        """Hourly flows for one connection and year, optionally limited to some months."""
        query = {"connection": connection, "year": year}
        if months is not None:
            query["month"] = {"$in": list(months)}

        # Only fetch the fields used by the plots
        projection = {"_id": 0, "direction": 1, "time": 1, "month": 1, "flow_mw": 1, "energy_mwh": 1}
        df = pd.DataFrame(list(self.collection.find(query, projection)))
        if not df.empty:
            df = df.sort_values("time").reset_index(drop=True)
        return df

    def close(self) -> None:
        self.client.close()


# One shared MongoDB client per app process
@st.cache_resource
def get_repository() -> FlowRepository:
    # URI from .streamlit/secrets.toml locally and in the app settings on streamlit.io
    return FlowRepository(st.secrets["mongo"]["uri"])


class FlowData:
    """Streamlit-cached MongoDB querioes. `_self` keeps the instance out 
    of the cache hash.
    """

    def __init__(self, repository: FlowRepository | None = None):
        self.repository = repository or get_repository()

    # Query results are cached for an hour, so widget changes don't query MongoDB again and
    # data inserted by the notebook shows up in the app within an hour
    @st.cache_data(ttl="1h")
    def connections(_self) -> list[str]:
        return _self.repository.connections()

    @st.cache_data(ttl="1h")
    def years(_self, connection: str) -> list[int]:
        return _self.repository.years(connection)

    @st.cache_data(ttl="1h", show_spinner="Loading flows from MongoDB...")
    def flows(_self, connection: str, year: int, months: tuple[int, ...] | None = None) -> pd.DataFrame:
        return _self.repository.flows(connection, year, months)
