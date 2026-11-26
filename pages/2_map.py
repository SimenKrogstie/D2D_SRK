"""Map of the Magasinstatistikk areas, coloured by filling degree or weather. A click selects an area."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules import state, theme
from modules.data_loader import ReservoirClient, ReservoirControls
from modules.regions import load_geojson
from modules.weather import VARIABLE_INFO, WeatherData, aggregate, area_for_region, region_for_area, variable_label


class MapPage:
    """Choropleth of the areas of the chosen area type, for the last month of the time window."""

    FILL = "fill_degree"

    def __init__(self):
        self.controls = ReservoirControls()
        self.weather = WeatherData()

    def fill_values(self, area_type: str, month: pd.Period) -> pd.Series:
        """Filling degree per region in the last week of the month (or the last week before)."""
        df = self.controls.data.all()
        df = df.loc[(df["area_type"] == area_type) & (df[ReservoirClient.DATE_COL] <= month.end_time)]
        if df.empty:
            return pd.Series(dtype=float)
        last = df.loc[df[ReservoirClient.DATE_COL] == df[ReservoirClient.DATE_COL].max()]
        regions = [region_for_area(area_type, n) for n in last["area_number"]]
        return pd.Series(last[self.FILL].to_numpy(), index=regions)

    def weather_values(self, regions: list[str], variable: str, month: pd.Period) -> pd.Series:
        """The weather variable summed or averaged over the month, per region."""
        values = {}
        progress = st.progress(0.0, text="Downloading weather...")
        for i, region in enumerate(regions):
            hourly = self.weather.year(region, month.year)
            monthly = aggregate(hourly, "MS")
            if month.start_time in monthly.index:
                values[region] = monthly.loc[month.start_time, variable]
            progress.progress((i + 1) / len(regions), text=f"Weather for {region} loaded")
        progress.empty()
        return pd.Series(values, dtype=float)

    def render(self) -> None:
        header = theme.page_header("Map of Areas", "Overview",
                                   "Price areas, watercourse areas or all of Norway, coloured by filling degree or a "
                                   "weather variable for the last month of the time window. Click an area to select it "
                                   "for the other pages.")

        area_type = self.controls.area_type
        month = pd.Period(self.controls.month_range[1], freq="M")
        geojson = load_geojson(area_type)
        regions = [f["properties"]["region"] for f in geojson["features"]]

        options = [self.FILL] + list(VARIABLE_INFO)
        color_by = st.selectbox(
            "Colour by", options=options,
            format_func=lambda o: "Filling degree (Magasinstatistikk)" if o == self.FILL else variable_label(o),
            **state.widget("map_color", options),
        )

        with theme.data_guard("the map data"):
            if color_by == self.FILL:
                values = self.fill_values(area_type, month)
                label, colorscale, fmt = "Filling degree", "Blues", ".1%"
            elif month.start_time > self.weather.last_available():
                st.info(f"ERA5 weather is not available for {month} yet. Move the end of the time window back.")
                values, label, colorscale, fmt = pd.Series(dtype=float), variable_label(color_by), "Viridis", ".1f"
            else:
                values = self.weather_values(regions, color_by, month)
                label = variable_label(color_by)
                colorscale = "RdBu_r" if color_by == "temperature_2m" else "Viridis"
                fmt = ".1f"
        values = values.reindex(regions)

        selected = region_for_area(area_type, self.controls.area_number)
        fig = self.figure(geojson, values, selected, label, colorscale, fmt)

        header.caption(f"{ReservoirClient.AREA_TYPES[area_type]}, {month.strftime('%B %Y')}. "
                       "Click an area to select it for the other pages.")
        event = theme.show(fig, on_select="rerun", selection_mode="points", key="area_map")
        self.handle_click(event, regions, selected)

        value = values.get(selected)
        st.metric(f"Selected: {self.controls.area_label}",
                  "–" if value is None or pd.isna(value) else format(value, fmt), help=label)
        if values.isna().all():
            st.info("No values for this month. Try another time window or colour.")

    @staticmethod
    def figure(geojson: dict, values: pd.Series, selected: str, label: str, colorscale: str,
               fmt: str) -> go.Figure:
        regions = list(values.index)
        fig = go.Figure(go.Choroplethmap(
            geojson=geojson, featureidkey="properties.region", locations=regions,
            z=values.to_numpy(), colorscale=colorscale, marker={"opacity": 0.55, "line": {"width": 1, "color": "white"}},
            colorbar={"title": label}, customdata=regions,
            hovertemplate=f"<b>%{{location}}</b><br>{label}: %{{z:{fmt}}}<extra></extra>",
            # Clicking would otherwise fade the other areas
            selected={"marker": {"opacity": 0.55}}, unselected={"marker": {"opacity": 0.55}},
        ))
        # The selected area again on top, with only a thick outline in the contrast colour
        fig.add_trace(go.Choroplethmap(
            geojson=geojson, featureidkey="properties.region", locations=[selected], z=[0],
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
            marker={"line": {"width": 4, "color": theme.CONTRAST}}, hoverinfo="skip",
        ))
        fig.update_layout(
            map={"style": "carto-darkmatter", "center": {"lat": 65.0, "lon": 15.0}, "zoom": 3.4},
            height=650, margin={"l": 0, "r": 0, "t": 10, "b": 0}, clickmode="event+select",
        )
        return fig

    def handle_click(self, event, regions: list[str], selected: str) -> None:
        """Store a clicked area and redraw, so its outline and the other pages follow."""
        points = (event or {}).get("selection", {}).get("points", [])
        for point in points:
            if point.get("curve_number", 0) != 0:
                continue  # The outline layer of the selected area
            region = point.get("location")
            index = point.get("point_index")
            if region is None and index is not None and index < len(regions):
                region = regions[index]
            # A selection left over from another area type is ignored
            if region in regions and region != selected:
                self.controls.select_area(*area_for_region(region))
                st.rerun()


# Streamlit reruns this file on every interaction
MapPage().render()
