"""EUR and USD exchange rates against NOK from Norges Bank, read from MongoDB."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules import theme
from modules.currency import CurrencyClient, CurrencyData

CURRENCIES = {"EUR_NOK": "EUR/NOK", "USD_NOK": "USD/NOK"}
RESOLUTIONS = {"Daily": "D", "Weekly": "W-SUN", "Monthly": "MS"}


class CurrencyPage:
    """Rates for a chosen period and resolution, with the latest values as key numbers."""

    # First year of the shortest dataset in the app: the ENTSO-E flows in MongoDB, downloaded for
    # the last two years in notebooks/assignment_2.ipynb (from October 2024). MongoDB holds rates
    # from 2006 for the forecast page, but this page shows the same period as the flows
    FIRST_YEAR = 2024

    @staticmethod
    def resample(rates: pd.DataFrame, resolution: str) -> pd.DataFrame:
        """Business-day rates to the chosen resolution.

        Weekends and holidays have no rate, so the last rate is carried forward before the means.
        """
        freq = RESOLUTIONS[resolution]
        if freq == "D":
            return rates
        if freq == "W-SUN":
            return CurrencyClient.weekly(rates)
        return rates.asfreq("D").ffill().resample(freq).mean()

    def render(self) -> None:
        header = theme.page_header("Currency Rates", "Power flows",
                                   "Norges Bank's daily exchange rates, in NOK per unit of foreign currency. Power is "
                                   "traded in euros on the Nordic market, so the EUR/NOK rate affects Norwegian power prices.")

        today = pd.Timestamp.now()
        left, middle, right = st.columns([2, 3, 2])
        currencies = left.multiselect("Currencies", options=list(CURRENCIES), default=list(CURRENCIES),
                                      format_func=CURRENCIES.get)
        first, last = middle.select_slider("Years", options=list(range(self.FIRST_YEAR, today.year + 1)),
                                           value=(self.FIRST_YEAR, today.year))
        resolution = right.radio("Resolution", options=list(RESOLUTIONS), index=1, horizontal=True)
        if not currencies:
            st.info("Choose at least one currency.")
            return

        # Stored in MongoDB by the part 4 notebook, so the page doesn't wait for the Norges Bank API
        with theme.data_guard("the exchange rates from MongoDB"):
            data = CurrencyData()
            rates = data.rates(f"{first}-01-01", f"{last}-12-31")
            stored_until = data.last_date()
        rates = rates.reindex(columns=currencies).dropna(how="all")
        if rates.empty:
            st.warning("No exchange rates stored for the chosen years. They are downloaded from Norges Bank "
                       "and stored in MongoDB by notebooks/assignment_4.ipynb.")
            return
        if stored_until is not None:
            header.caption(f"Stored in MongoDB up to {stored_until:%d %B %Y}.")

        self.key_numbers(rates)
        theme.show(self.figure(self.resample(rates, resolution), resolution))

        with st.expander("Data table"):
            table = self.resample(rates, resolution).rename(columns=CURRENCIES).sort_index(ascending=False)
            st.dataframe(table, width="stretch",
                         column_config={c: st.column_config.NumberColumn(format="%.4f") for c in table.columns})
        with st.expander("Data source"):
            st.markdown(
                """
- **Source:** [Norges Bank open data](https://www.norges-bank.no/en/topics/Statistics/open-data/),
  SDMX series `EXR/B.EUR+USD.NOK.SP` (business-day spot rates).
- **Pipeline:** `notebooks/assignment_4.ipynb` downloads the rates, stores them in a local
  Cassandra database with Spark, reads them back with Spark and inserts them into MongoDB,
  which this page reads from (the same route as the cross-border flows).
- **Time:** the rates are dates without time of day, fixed around 14:15 Norwegian time on
  Norwegian business days, so they need no time-zone conversion.
- **Weekly and monthly values:** the last rate is carried forward over weekends and holidays
  before the mean, and the weeks run Monday–Sunday like Magasinstatistikk.
"""
            )

    @staticmethod
    def key_numbers(rates: pd.DataFrame) -> None:
        """Latest rate per currency, with the change from one year earlier."""
        columns = st.columns(len(rates.columns))
        for column, currency in zip(columns, rates.columns):
            series = rates[currency].dropna()
            latest_date = series.index[-1]
            year_ago = series.asof(latest_date - pd.DateOffset(years=1))
            delta = None if pd.isna(year_ago) else f"{series.iloc[-1] / year_ago - 1:+.1%} in a year"
            column.metric(f"{CURRENCIES[currency]} on {latest_date:%d %b %Y}", f"{series.iloc[-1]:.4f}",
                          delta=delta, delta_color="off")

    @staticmethod
    def figure(rates: pd.DataFrame, resolution: str) -> go.Figure:
        fig = go.Figure()
        for currency in rates.columns:
            fig.add_trace(go.Scatter(x=rates.index, y=rates[currency], mode="lines", name=CURRENCIES[currency],
                                     hovertemplate="%{y:.4f} NOK"))
        fig.update_layout(title=f"{resolution} exchange rates", xaxis_title="Date", yaxis_title="NOK per unit",
                          hovermode="x unified", height=500, xaxis={"rangeslider": {"visible": True}})
        return fig


# Streamlit reruns this file on every interaction
CurrencyPage().render()
