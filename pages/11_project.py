"""About the course project: purpose, data sources, pipeline and code."""

import streamlit as st

from modules import theme

theme.page_header("About the Project", "About")

st.markdown(
    """
This app is the course project in **IND320 Data to Decision** at NMBU. It collects, stores and
analyses data on Norwegian hydropower, weather, exchange rates and power flows, in four parts
over the semester: data collection and plots, databases, analyses of anomalies and seasons, and
finally forecasting, a map and this refactored app.

#### Data sources
| Source | Data | Resolution |
|---|---|---|
| [NVE Magasinstatistikk](https://biapi.nve.no/magasinstatistikk/swagger/index.html) | Reservoir filling per price area, watercourse area and for Norway | Weekly |
| [open-meteo](https://open-meteo.com/) | ERA5 reanalysis weather for random points in each region | Hourly |
| [Norges Bank](https://www.norges-bank.no/en/topics/Statistics/open-data/) | EUR and USD exchange rates against NOK | Business days |
| [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/) | Physical cross-border flows between Norway and its neighbours | Hourly |

#### How the data moves
- **Reservoirs and weather** are downloaded directly from the APIs and cached.
- **Power flows and exchange rates** are downloaded in the notebooks and go through Spark into
  Cassandra, and on to MongoDB, which this app reads.
- **Time zones:** everything is stored in UTC. Hourly data is converted to Norwegian time before
  it is combined with the weekly reservoir data, so the weeks run Monday–Sunday like Magasinstatistikk.

#### Code
The app and the Jupyter notebooks share the same Python modules, so the analyses and plots are
the same in both. The source code and the notebooks are on
[GitHub](https://github.com/SimenKrogstie/D2D_SRK).
"""
)
