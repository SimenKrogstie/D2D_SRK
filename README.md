# Norwegian Hydropower and Power Flows

Course project in IND320 (Data to Decision) at NMBU. A Streamlit app and one Jupyter notebook per
part of the project, which collect, store and analyse data on Norwegian hydropower, weather,
exchange rates and power flows.

**Live app:** [d2dsrk.streamlit.app](https://d2dsrk.streamlit.app/)

## Data sources
- **NVE Magasinstatistikk** – weekly reservoir filling per price area (NO1–NO5), watercourse area and for Norway
- **open-meteo** – hourly ERA5 reanalysis weather for random locations in each region
- **Norges Bank** – daily EUR and USD exchange rates against NOK
- **ENTSO-E Transparency Platform** – hourly cross-border physical flows between Norway and its neighbours
- **NVE Atlas** – outlines of the price areas and NVE regions, used for the map and for sampling weather locations

## The app
The pages are grouped by data source in the sidebar, each group with its own colour. The area and
time window chosen on one page (or by clicking the map) follow to the other pages.

| Group | Page | Content |
|---|---|---|
| | Home | Short description and a link card per page |
| | Map | GeoJSON map of the areas, coloured by filling degree or a weather variable; a click selects the area |
| Reservoirs | Data overview | Plot and sparkline table of the Magasinstatistikk data |
| | Seasonal analysis | STL decomposition and spectrogram of the filling degree |
| | Forecast filling | SARIMAX forecast (River) with selectable parameters and exogenous variables, as a Plotly animation |
| Weather | Outliers and anomalies | SPC outliers (DCT) and LOF anomalies for any weather variable |
| | Weather vs reservoirs | Sliding window correlation with selectable lag and window length |
| Power flows | Cross-border flows | Yearly totals and hourly flows per connection |
| | Currency rates | EUR/NOK and USD/NOK |
| About | Contact, Project | Contact information and a description of the project |

## Project parts
1. Reservoir data from a CSV file, and the first Streamlit app
2. NVE and ENTSO-E APIs, Cassandra with Spark, MongoDB, and the cross-border flows page
3. NVE Atlas regions, ERA5 weather, outliers (SPC, LOF), STL and spectrogram
4. Norges Bank exchange rates, time zones, SARIMAX forecasting, the map, sliding window
   correlation, and a refactor of the app (theme, navigation, Plotly only)

## Repository
- `app.py`, `pages/` – the Streamlit app
- `modules/` – data clients and analyses shared by the app and the notebooks
  (`data_loader`, `weather`, `currency`, `data_flow`, `regions`, `analysis`, `forecast`,
  `spark_cassandra`, `state`, `theme`)
- `notebooks/` – `assignment_1.ipynb` to `assignment_4.ipynb`, each with a log and AI declaration
- `data/` – NVE Atlas shapefiles and the GeoJSON exported from them

The flows and exchange rates are downloaded in the notebooks, stored in Cassandra with Spark and
moved to MongoDB, which the app reads from. Weather and reservoir data are fetched by the app
directly from the APIs and cached.

## Running locally
```bash
uv sync
uv run streamlit run app.py
```
The app needs `.streamlit/secrets.toml` with `[mongo]` `uri` (cross-border flows and currency
pages). The notebooks also need an ENTSO-E token in the same file, and parts 2 and 4 need a local
Cassandra database (Docker) and Java 17 for Spark.
