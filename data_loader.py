"Preprocessing of the data"

from pathlib import Path

import pandas as pd
import streamlit as st

DATA_PATH = Path(__file__).resolve().parent / "data" / "reservoirs.csv"

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


# Caching data so its only read once per session
@st.cache_data
def load_reservoir_data() -> pd.DataFrame:
    # Read the raw CSV and translate its headers to the English names above.
    df = pd.read_csv(DATA_PATH, parse_dates=["dato_Id"])
    df = df.rename(columns=RENAME_MAP)

    # National total only
    df = df.loc[df["area_type"] == "NO", [DATE_COL] + VALUE_COLS]

    # Sorting rows in chronological order
    df = df.sort_values(DATE_COL).reset_index(drop=True)

    return df
