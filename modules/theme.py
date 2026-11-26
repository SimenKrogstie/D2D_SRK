"""App theme: colours, the Plotly template, page headers and error feedback."""

from contextlib import contextmanager

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from pymongo.errors import PyMongoError

# Same colours as .streamlit/config.toml
PRIMARY = "#4FA3D9"
BACKGROUND = "#0F1720"
SECONDARY_BACKGROUND = "#1A2532"
TEXT = "#E6EDF3"
GRID = "#2A3747"
CONTRAST = "#FFD166"  # Highlights, e.g. the selected area on the map
FONT = "SF Pro Rounded, ui-rounded, sans-serif"  # Same as .streamlit/config.toml
DESCRIPTION_GAP = "1rem"  # Space between the line under the title and the page description

# One accent colour per sidebar group
GROUP_COLORS = {
    "Overview": "#C9D1D9",
    "Reservoirs": "#4FA3D9",
    "Weather": "#5CC28A",
    "Power flows": "#F2A541",
    "About": "#B48EE0",
}

COLORWAY = ["#4FA3D9", "#F2A541", "#5CC28A", "#E5646E", "#B48EE0", "#FFD166", "#56C7C7", "#C9D1D9"]

# Transparent background so the plots sit on the app background
pio.templates["ind320"] = go.layout.Template(
    layout=go.Layout(
        colorway=COLORWAY,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXT, "family": FONT},
        xaxis={"gridcolor": GRID, "zerolinecolor": GRID},
        yaxis={"gridcolor": GRID, "zerolinecolor": GRID},
        legend={"bgcolor": "rgba(0,0,0,0)"},
        hoverlabel={"bgcolor": SECONDARY_BACKGROUND},
    )
)
pio.templates.default = "plotly_dark+ind320"


def show(fig: go.Figure, **kwargs):
    """st.plotly_chart with the app template. theme=None, since Streamlit's theme would replace it."""
    return st.plotly_chart(fig, theme=None, width="stretch", **kwargs)


# The slider's filled track is a gradient with the slider position in it, so it can't be
# recoloured directly. These filters turn PRIMARY into each group colour (fitted with the CSS
# filter formulas; recompute them if PRIMARY or a group colour changes)
TRACK_FILTERS = {
    "Overview": "hue-rotate(189deg) saturate(0) brightness(1.40)",
    "Reservoirs": "none",
    "Weather": "hue-rotate(294deg) saturate(0.74) brightness(1.13)",
    "Power flows": "hue-rotate(194deg) saturate(1.13) brightness(1.17)",
    "About": "hue-rotate(65deg) saturate(0.71) brightness(1.05)",
}


def _rgba(color: str, alpha: float) -> str:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def accent_css(group: str) -> str:
    """CSS giving the widgets the group colour instead of the one global primaryColor.

    The class names are Streamlit's styled components in the version pinned in uv.lock. After an
    upgrade they may change, and the widgets then simply fall back to PRIMARY.
    """
    c = GROUP_COLORS.get(group, PRIMARY)
    track = TRACK_FILTERS.get(group, "none")
    return f"""
[data-testid="stSidebarNav"] a[aria-current="page"] {{ border-left: 4px solid {c}; }}
h1 {{ border-bottom: 2px solid {c}; padding-bottom: 0.3rem; }}
/* Space between the line and the page description (the container key becomes this class) */
.st-key-page_description {{ margin-top: {DESCRIPTION_GAP}; }}
/* Slider: thumb, value and filled track */
.efbyxod3 {{ background-color: {c} !important; }}
.efbyxod4 {{ color: {c} !important; }}
.efbyxod5 {{ filter: {track}; }}
/* Radio, checkbox and toggle when selected */
label[data-selected] .e1mpz0hj4 {{ background-color: {c} !important; }}
label[data-selected] .e15oan335 {{ background-color: {c} !important; border-color: {c} !important; }}
label[data-selected] .e15oan337, label[data-selected] .enqxyix13 {{ background-color: {c} !important; }}
/* Tabs */
.e1ac7blb4[data-selected], .e1ac7blb4[data-hovered], .e1ac7blb4[data-focus-visible] {{ color: {c} !important; }}
.e1ac7blb4[data-selected] .react-aria-SelectionIndicator {{ background-color: {c} !important; }}
/* Multiselect tags */
.e1kig3hy3 {{ background-color: {c} !important; color: {BACKGROUND} !important; }}
/* Primary buttons, and hover on the other button kinds */
.eqzt73c1 {{ background-color: {c} !important; border-color: {c} !important; color: {BACKGROUND} !important; }}
.eqzt73c1:hover, .eqzt73c1:focus-visible {{ background-color: {_rgba(c, 0.85)} !important; border-color: {_rgba(c, 0.85)} !important; }}
.eqzt73c3:hover, .eqzt73c4:hover, .eqzt73c5:hover {{ color: {c} !important; }}
/* Selected pills and segmented control */
.eqzt73c11, .eqzt73c13, .eqzt73c27[data-selected], .eqzt73c28[data-selected] {{
    background-color: {_rgba(c, 0.1)} !important; border-color: {c} !important; color: {c} !important; }}
.eqzt73c11:hover, .eqzt73c13:hover, .eqzt73c27[data-selected][data-hovered], .eqzt73c28[data-selected][data-hovered] {{
    background-color: {_rgba(c, 0.2)} !important; }}
/* Number input +/- buttons */
.e1rv0tzo2:hover:enabled, .e1rv0tzo2:focus:enabled {{ background-color: {c} !important; }}
"""


def page_header(title: str, group: str, description: str = ""):
    """Title, the line under it and a short description of the page, nothing else above it.

    The line, the active sidebar link and the widgets get the group colour (accent_css).
    The description is markdown, so it can hold links. Returns the description container, so a
    page can add its grey caption (`header.caption(...)`) between the two lines, also later in
    the script when the caption depends on a selection.
    """
    # Only CSS, so nothing visible comes before the title
    st.markdown(f"<style>{accent_css(group)}</style>", unsafe_allow_html=True)
    st.title(title)
    header = st.container(key="page_description")
    if description:  # An empty description would still take up a line
        header.markdown(description)
    return header


@contextmanager
def data_guard(what: str):
    """Show a warning and stop the page if loading `what` fails, instead of a traceback.

    OSError covers requests' connection errors and missing files or secrets.
    """
    try:
        yield
    except (OSError, PyMongoError, ValueError, KeyError) as error:
        st.warning(f"Could not load {what}. Check the connection and try again later.\n\n"
                   f"Details: `{type(error).__name__}: {error}`")
        st.stop()
