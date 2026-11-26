"""EUR and USD exchange rates: download from the Norges Bank (NB) SDMX API, storage in MongoDB."""

import io
import time

import pandas as pd
import pymongo
import requests
import streamlit as st


class CurrencyClient:
    """Daily exchange rates (NOK per unit of foreign currency) from data.norges-bank.no.

    Rates are published on Norwegian business days around 14:15 Norwegian time, as dates
    without time of day.
    """

    API_URL = "https://data.norges-bank.no/api/data/EXR"

    def __init__(self, timeout: tuple[float, float] = (10, 30), max_seconds: float = 45):
        # (connect, read) in seconds. The read timeout restarts with every chunk received, so a
        # slow response could run forever; max_seconds limits the whole download
        self.timeout = timeout
        self.max_seconds = max_seconds

    def _get_text(self, url: str, params: dict) -> tuple[int, str]:
        """Status code and body, giving up with TimeoutError after max_seconds in total."""
        started = time.monotonic()
        with requests.get(url, params=params, timeout=self.timeout, stream=True) as response:
            chunks = []
            for chunk in response.iter_content(chunk_size=65536):
                chunks.append(chunk)
                if time.monotonic() - started > self.max_seconds:
                    raise TimeoutError(f"Norges Bank did not answer within {self.max_seconds:.0f} s")
            return response.status_code, b"".join(chunks).decode(response.encoding or "utf-8")

    def fetch_raw(self, currencies: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
        """The CSV response as a DataFrame, one row per currency and date (empty if no rates)."""
        # Series key: frequency B (business day), base currencies, quote NOK, spot rate
        key = f"B.{'+'.join(currencies)}.NOK.SP"
        params = {"format": "csv", "startPeriod": start, "endPeriod": end, "locale": "en"}
        status, text = self._get_text(f"{self.API_URL}/{key}", params)
        # SDMX answers 404 when the period has no rates, e.g. the first days of a year
        if status == 404 or not text.strip():
            return pd.DataFrame(columns=["BASE_CUR", "TIME_PERIOD", "OBS_VALUE"])
        if status >= 400:
            raise requests.HTTPError(f"Norges Bank answered {status}: {text[:200]}")
        # The separator has varied between ';' and ',', so it is sniffed
        return pd.read_csv(io.StringIO(text), sep=None, engine="python")

    def _parse(self, raw: pd.DataFrame) -> pd.DataFrame:
        """The long CSV table to one column per currency (NOK per unit), indexed by date."""
        missing = {"BASE_CUR", "TIME_PERIOD", "OBS_VALUE"} - set(raw.columns)
        if missing:
            raise ValueError(f"Unexpected response from Norges Bank, missing columns {missing}")
        # Some series are quoted per 100 units (e.g. SEK), UNIT_MULT says how many
        values = pd.to_numeric(raw["OBS_VALUE"], errors="coerce")
        if "UNIT_MULT" in raw.columns:
            values = values / 10 ** pd.to_numeric(raw["UNIT_MULT"], errors="coerce").fillna(0)
        rates = (
            raw.assign(date=pd.to_datetime(raw["TIME_PERIOD"]), value=values)
            .pivot_table(index="date", columns="BASE_CUR", values="value")
            .sort_index()
        )
        rates.columns.name = None
        rates.columns = [f"{c}_NOK" for c in rates.columns]
        return rates

    def fetch(self, currencies: tuple[str, ...] = ("EUR", "USD"), start: str = "2024-01-01",
              end: str | None = None) -> pd.DataFrame:
        """One column per currency (NOK per unit), indexed by date. start/end as "YYYY-MM-DD".

        Long spans are requested one year at a time, so no single request runs into max_seconds.
        """
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end) if end else pd.Timestamp.now().normalize()
        frames = []
        for year in range(start_ts.year, end_ts.year + 1):
            chunk_start = max(start_ts, pd.Timestamp(f"{year}-01-01"))
            chunk_end = min(end_ts, pd.Timestamp(f"{year}-12-31"))
            raw = self.fetch_raw(tuple(currencies), chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"))
            if not raw.empty:
                frames.append(self._parse(raw))
        if not frames:
            return pd.DataFrame(columns=[f"{c}_NOK" for c in currencies], index=pd.DatetimeIndex([], name="date"))
        return pd.concat(frames).sort_index()

    @staticmethod
    def weekly(rates: pd.DataFrame) -> pd.DataFrame:
        """Weekly means on Magasinstatistikk weeks (ending Sunday).

        Weekends and holidays have no rate, so the last rate is carried forward first.
        """
        daily = rates.asfreq("D").ffill()
        return daily.resample("W-SUN").mean()


class CurrencyRepository:
    """Exchange rates in MongoDB (ind320, collection exchange_rates), one document per currency and day.

    Filled by notebooks/assignment_4.ipynb (Norges Bank -> Spark -> Cassandra -> MongoDB) and read
    by the app, so the pages don't wait for the Norges Bank API.
    """

    DB_NAME = "ind320"
    COLLECTION = "exchange_rates"
    CURRENCIES = ("EUR_NOK", "USD_NOK")

    def __init__(self, uri: str):
        # Fails after 10 s instead of 30 s when the database can't be reached
        self.client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=10_000)
        self.collection = self.client[self.DB_NAME][self.COLLECTION]

    def ping(self) -> None:
        """Fails if the URI or the IP access list is wrong."""
        self.client.admin.command("ping")

    @staticmethod
    def to_long(rates: pd.DataFrame) -> pd.DataFrame:
        """Wide rates (one column per currency) to rows of currency, year, date and rate.

        The year is part of the Cassandra partition key, like for the flows.
        """
        long = (rates.rename_axis("date").reset_index()
                .melt(id_vars="date", var_name="currency", value_name="rate").dropna())
        long["date"] = pd.to_datetime(long["date"])
        long["year"] = long["date"].dt.year
        return long[["currency", "year", "date", "rate"]].reset_index(drop=True)

    def replace_all(self, df: pd.DataFrame) -> int:
        """Replace the collection content with df (long format), so re-running doesn't duplicate data."""
        self.collection.delete_many({})
        self.collection.insert_many(df[["currency", "year", "date", "rate"]].to_dict("records"), ordered=False)
        # Index matching the query from the app
        self.collection.create_index([("currency", pymongo.ASCENDING), ("date", pymongo.ASCENDING)])
        return self.collection.count_documents({})

    def rates(self, start: str, end: str, currencies: tuple[str, ...] = CURRENCIES) -> pd.DataFrame:
        """One column per currency between start and end ("YYYY-MM-DD"), indexed by date."""
        query = {"currency": {"$in": list(currencies)},
                 "date": {"$gte": pd.Timestamp(start).to_pydatetime(), "$lte": pd.Timestamp(end).to_pydatetime()}}
        docs = list(self.collection.find(query, {"_id": 0, "currency": 1, "date": 1, "rate": 1}))
        if not docs:
            return pd.DataFrame(columns=list(currencies), index=pd.DatetimeIndex([], name="date"))
        wide = pd.DataFrame(docs).pivot_table(index="date", columns="currency", values="rate").sort_index()
        wide.columns.name = None
        return wide.reindex(columns=list(currencies))

    def last_date(self) -> pd.Timestamp | None:
        """Last stored date, to show how up to date the data is."""
        doc = self.collection.find_one({}, {"_id": 0, "date": 1}, sort=[("date", pymongo.DESCENDING)])
        return pd.Timestamp(doc["date"]) if doc else None

    def close(self) -> None:
        self.client.close()


# One shared MongoDB client per app process
@st.cache_resource
def get_currency_repository() -> CurrencyRepository:
    # Same URI as the flows, from .streamlit/secrets.toml locally and the app settings on streamlit.io
    return CurrencyRepository(st.secrets["mongo"]["uri"])


class CurrencyData:
    """Cached MongoDB queries for the app. `_self` keeps the instance out of the cache key."""

    def __init__(self, repository: CurrencyRepository | None = None):
        self.repository = repository or get_currency_repository()

    # Cached for an hour, so data stored by the notebook shows up in the app within an hour
    @st.cache_data(ttl="1h", show_spinner="Loading exchange rates from MongoDB...")
    def rates(_self, start: str, end: str) -> pd.DataFrame:
        return _self.repository.rates(start, end)

    @st.cache_data(ttl="1h")
    def last_date(_self) -> pd.Timestamp | None:
        return _self.repository.last_date()
