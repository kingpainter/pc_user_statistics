# File Name: panel.py
# Version: 2.2.0
# Description: Panel registration for PC User Statistics.
# Last Updated: March 1, 2026

from __future__ import annotations

import os
import logging

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, __version__

_LOGGER = logging.getLogger(__name__)

PANEL_URL       = f"/api/{DOMAIN}-panel"
PANEL_ICON      = "mdi:controller-classic"
PANEL_NAME      = "pc-user-statistics-panel"
PANEL_TITLE     = "PC Statistik"
PANEL_FOLDER    = "frontend"
PANEL_FILENAME  = "pc-user-statistics-panel.js"
CUSTOM_COMPONENTS = "custom_components"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the PC User Statistics sidebar panel."""

    # Guard against double registration
    if hass.data[DOMAIN].get("_panel_registered", False):
        _LOGGER.debug("Panel already registered, skipping")
        return

    root_dir      = os.path.join(hass.config.path(CUSTOM_COMPONENTS), DOMAIN)
    frontend_dir  = os.path.join(root_dir, PANEL_FOLDER)
    panel_file    = os.path.join(frontend_dir, PANEL_FILENAME)

    # Cache busting based on file mtime
    try:
        cache_bust = int(os.path.getmtime(panel_file))
    except OSError:
        _LOGGER.warning("Panel JS file not found: %s", panel_file)
        cache_bust = 0

    # Register static path for the JS file
    await hass.http.async_register_static_paths([
        StaticPathConfig(PANEL_URL, panel_file, cache_headers=False),
    ])
    _LOGGER.info("Panel static path registered: %s → %s", PANEL_URL, panel_file)

    # Register custom sidebar panel
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_NAME,
        frontend_url_path=DOMAIN,
        js_url=f"{PANEL_URL}?v={__version__}&m={cache_bust}",
        embed_iframe=False,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=False,
        config={},
    )

    hass.data[DOMAIN]["_panel_registered"] = True
    _LOGGER.info("Panel '%s' registered in sidebar at /%s", PANEL_TITLE, DOMAIN)


def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the panel from the sidebar."""
    from homeassistant.components import frontend
    frontend.async_remove_panel(hass, DOMAIN)
    _LOGGER.debug("Panel removed from sidebar")
