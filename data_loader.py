# Single shared place where the reservoir CSV is read and shaped for the app.
# Every page imports load_reservoir_data() (plus the DATE_COL/VALUE_COLS
# constants) from here instead of reading the CSV or hardcoding column names itself.
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_PATH = Path(__file__).resolve().parent / "data" / "reservoirs.csv"

# Maps the raw Norwegian CSV headers to English, understandable names.
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

# Shared constants so pages never hardcode column names themselves.
DATE_COL = "date"

VALUE_COLS = [
    "fill_degree",
    "capacity_twh",
    "filling_twh",
    "fill_degree_prev_week",
    "change_in_fill_degree",
]


# Cached so the CSV is only read/parsed once per session, not on every page render.
@st.cache_data
def load_reservoir_data() -> pd.DataFrame:
    # Read the raw CSV and translate its headers to the English names above.
    df = pd.read_csv(DATA_PATH, parse_dates=["dato_Id"])
    df = df.rename(columns=RENAME_MAP)

    # National total only (area_type == "NO"); raw data has 5 price areas + 3
    # watercourse areas interleaved per date, matching notebooks/assignment_1.ipynb.
    df = df.loc[df["area_type"] == "NO", [DATE_COL] + VALUE_COLS]

    # Put rows in chronological order once here, so pages never need to re-sort.
    df = df.sort_values(DATE_COL).reset_index(drop=True)

    return df
