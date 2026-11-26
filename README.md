# Norwegian Hydropower and Power Flows

Course project in IND320 (Data to Decision) at NMBU. A Streamlit app and a set of Jupyter
notebooks that collect, store and analyse data on Norwegian hydropower, electricity and weather.

## Data sources
- **NVE Magasinstatistikk** – weekly reservoir filling per price area (NO1–NO5), watercourse area and nationally
- **ENTSO-E Transparency Platform** – hourly cross-border physical flows between Norway and its neighbours
- **open-meteo** – hourly ERA5 reanalysis weather for random locations in each region
- **Norges Bank** – daily EUR and USD exchange rates

## Contents
- `app.py`, `pages/` – the Streamlit app, grouped by data source:
  - home page with a link box per page, and an interactive map of the areas (click to select)
  - **Reservoirs:** data overview, STL and spectrogram, SARIMAX forecast of the filling degree
  - **Weather:** outliers (SPC) and anomalies (LOF), sliding window correlation with the reservoirs
  - **Power flows:** cross-border flows and EUR/USD exchange rates
  - **About:** contact and project description
- `modules/` – data clients and analyses shared by the app and the notebooks
- `notebooks/` – one notebook per part of the project, with log and AI declaration
- `data/` – NVE Atlas shapefiles and the GeoJSON exported from them

The flow data and the exchange rates are stored in Cassandra with Spark and moved to MongoDB,
which the app reads from.

## Running locally
```bash
uv sync
uv run streamlit run app.py
```
The app needs `.streamlit/secrets.toml` with a `[mongo]` `uri` for the flow page.
