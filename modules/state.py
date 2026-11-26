"""Selections shared across pages.

Streamlit deletes a widget's session-state key on any page where the widget isn't drawn.
The values are therefore stored under a separate key and passed back as the widget's
default, so e.g. an area clicked on the map is still selected on the forecast page.
"""

from typing import Any

import streamlit as st

PREFIX = "_kept_"
WIDGET_PREFIX = "w_"

# Defaults for the shared selections
DEFAULTS: dict[str, Any] = {
    "area_type": "EL",
    "weather_variable": "temperature_2m",
    "forecast_horizon": 26,
}


def get(name: str, default: Any = None) -> Any:
    return st.session_state.get(PREFIX + name, DEFAULTS.get(name, default))


def set(name: str, value: Any) -> None:  # noqa: A001 - mirrors get()
    st.session_state[PREFIX + name] = value


def _save(name: str) -> None:
    set(name, st.session_state[WIDGET_PREFIX + name])


def widget(name: str, options: list, default: Any = None) -> dict[str, Any]:
    """Keyword arguments for a selectbox/radio (index) or a range select_slider (value, when
    `default` is a tuple) whose value should survive page switches.

    A stored value that is no longer among the options falls back to `default`, or the first option.
    """
    value = get(name)
    is_range = isinstance(default, tuple)
    candidates = value if isinstance(value, (tuple, list)) else [value]
    if value is None or not all(v in options for v in candidates) or is_range != isinstance(value, (tuple, list)):
        value = default if default is not None else options[0]
    set(name, tuple(value) if is_range else value)

    kwargs: dict[str, Any] = {"key": WIDGET_PREFIX + name, "on_change": _save, "args": (name,)}
    if is_range:
        kwargs["value"] = tuple(value)
    else:
        kwargs["index"] = options.index(value)
    return kwargs
