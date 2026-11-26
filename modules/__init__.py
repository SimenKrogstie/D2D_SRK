"""Shared modules used by the Streamlit app and the Jupyter Notebook.

- data_loader: NVE Magasinstatistikk API (reservoir data) and the shared sidebar controls
- data_flow: ENTSO-E API (cross-border flows) and the MongoDB repository the app reads from
- spark_cassandra: storing and extracting the flows in the local Cassandra database with Spark
- weather: open-meteo ERA5 weather and aggregation to Norwegian days, weeks and months
- currency: EUR and USD exchange rates from Norges Bank
- regions: region polygons from the NVE Atlas shapefiles and their GeoJSON export
- analysis: SPC, LOF, STL, spectrogram and sliding window correlation
- forecast: SARIMAX forecasts of the filling degree
- state, theme: shared selections across pages, colours, Plotly template and error feedback
"""
