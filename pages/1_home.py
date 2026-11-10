"""Home page of the app."""

import streamlit as st

st.title("Norwegian Hydropower Reservoirs and Power Flows")

# Short introduction to the data sources and a description of each page
st.markdown(
    """
### Welcome!

This app gives an overview of the Norwegian Water Resources and Energy Directorate's hydropower
reservoir statistics (NVE's magasinstatistikk), downloaded directly from the
[NVE Magasinstatistikk API](https://biapi.nve.no/magasinstatistikk/swagger/index.html), and of the
cross-border power flows between Norway and its neighbours from the
[ENTSO-E Transparency Platform](https://transparency.entsoe.eu/), together with hourly weather
(ERA5 reanalysis) from the [open-meteo API](https://open-meteo.com/).

To navigate between the pages of the app you can use the collapsible sidebar to the left.


##### Content of pages
**Reservoirs**
- **Reservoir table:** One row per area of the chosen area type (price areas, national total or
 watercourse areas), with a sparkline of the chosen column over the downloaded interval.
- **Reservoir plot:** An interactive plot with one line per area, or all columns normalized for one area.
  The area type, download interval and column are chosen in the sidebar and shared with the table page.
- **Reservoir analysis:** STL decomposition and a spectrogram of the filling degree for one area.

**Weather**
- **Outliers and anomalies:** Precipitation outliers found with Statistical Process Control, and
  temperature anomalies found with the Local Outlier Factor, for the area chosen in the sidebar.

**Power flows**
- **Cross-border flows:** A pie chart of the yearly energy transferred in each direction of a chosen
  connection, and an hourly line plot for any set of months. The data is read from MongoDB.

**About**
- **Contact:** Page with link to my personal website with contact information.
"""
)
