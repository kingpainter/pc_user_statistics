# File Name: panel.py
# Version: 2.6.2
# Description: Panel and Lovelace card registration for PC User Statistics.
#              Registers the sidebar panel (admin only) and the custom Lovelace
#              cards as static HTTP paths. Cards auto-register in the Lovelace
#              picker via window.customCards in the JS file itself.


from __future__ import annotations

import os
import logging

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, __version__

_LOGGER = logging.getLogger(__name__)

PANEL_URL         = f"/api/{DOMAIN}-panel"
CARDS_URL         = f"/api/{DOMAIN}-cards"
PANEL_ICON        = "mdi:controller-classic"
PANEL_NAME        = "pc-user-statistics-panel"
PANEL_TITLE       = "PC Statistik"
PANEL_FOLDER      = "frontend"
PANEL_FILENAME    = "pc-user-statistics-panel.js"
CARDS_FILENAME    = "pc-user-statistics-cards.js"
CUSTOM_COMPONENTS = "custom_components"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the sidebar panel and Lovelace card resource."""

    # Guard against double registration within the same HA session
    if hass.data[DOMAIN].get("_panel_registered", False):
        _LOGGER.debug("Panel already registered, skipping")
        return

    root_dir     = os.path.join(hass.config.path(CUSTOM_COMPONENTS), DOMAIN)
    frontend_dir = os.path.join(root_dir, PANEL_FOLDER)
    panel_file   = os.path.join(frontend_dir, PANEL_FILENAME)
    cards_file   = os.path.join(frontend_dir, CARDS_FILENAME)

    # Cache busting based on file mtime
    try:
        panel_cache_bust = int(os.path.getmtime(panel_file))
    except OSError:
        _LOGGER.warning("Panel JS file not found: %s", panel_file)
        panel_cache_bust = 0

    try:
        cards_cache_bust = int(os.path.getmtime(cards_file))
    except OSError:
        _LOGGER.warning("Cards JS file not found: %s", cards_file)
        cards_cache_bust = 0

    # ── Register static HTTP paths ─────────────────────────────────────────
    static_paths = [StaticPathConfig(PANEL_URL, panel_file, cache_headers=False)]
    if os.path.exists(cards_file):
        static_paths.append(StaticPathConfig(CARDS_URL, cards_file, cache_headers=False))
        _LOGGER.info("Cards static path registered: %s → %s", CARDS_URL, cards_file)
    else:
        _LOGGER.warning("Cards JS file not found: %s", cards_file)

    await hass.http.async_register_static_paths(static_paths)
    _LOGGER.info("Panel static path registered: %s → %s", PANEL_URL, panel_file)

    # ── Register custom sidebar panel ──────────────────────────────────────
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_NAME,
        frontend_url_path=DOMAIN,
        module_url=f"{PANEL_URL}?v={__version__}&m={panel_cache_bust}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=True,
        config={},
    )

    # FIX: flag is set here — must be cleared in async_unregister_panel()
    hass.data[DOMAIN]["_panel_registered"] = True
    _LOGGER.info("Panel '%s' registered in sidebar at /%s", PANEL_TITLE, DOMAIN)

    # ── Register cards as Lovelace resource ───────────────────────────────
    if os.path.exists(cards_file):
        await _async_register_lovelace_resource(
            hass,
            url=f"{CARDS_URL}?v={__version__}&m={cards_cache_bust}",
            url_base=CARDS_URL,
        )


async def _async_register_lovelace_resource(
    hass: HomeAssistant,
    url: str,
    url_base: str,
) -> None:
    """Add or update the cards JS as a Lovelace resource.

    Uses the lovelace integration's resource store directly.
    Compatible with HA 2024.x+ where LovelaceData no longer has .mode/.resources.
    """
    import asyncio
    try:
        # In HA 2024.x the lovelace integration exposes resources via
        # hass.data["lovelace_resources"] (a ResourceStorageCollection).
        # Fall back to older hass.data["lovelace"].resources for compatibility.
        resources = hass.data.get("lovelace_resources")

        if resources is None:
            lovelace = hass.data.get("lovelace")
            if lovelace is None:
                _LOGGER.warning(
                    "Lovelace not available — add '%s' manually as a JS module resource", url
                )
                return
            resources = getattr(lovelace, "resources", None)

        if resources is None:
            _LOGGER.warning(
                "Cannot find Lovelace resources store — add '%s' manually as a JS module resource",
                url,
            )
            return

        # Wait until resources collection is loaded (up to 10 seconds)
        for _ in range(10):
            if getattr(resources, "loaded", True):
                break
            await asyncio.sleep(1)

        existing = [
            r for r in resources.async_items()
            if r["url"].startswith(url_base)
        ]

        if existing:
            resource = existing[0]
            if resource["url"] != url:
                await resources.async_update_item(
                    resource["id"],
                    {"res_type": "module", "url": url},
                )
                _LOGGER.info("Updated cards Lovelace resource to: %s", url)
            else:
                _LOGGER.debug("Cards Lovelace resource already up to date")
        else:
            await resources.async_create_item({"res_type": "module", "url": url})
            _LOGGER.info(
                "Registered cards Lovelace resource: %s — "
                "custom:pc-user-statistics-user-card and "
                "custom:pc-user-statistics-tablet-card are now available in the card picker",
                url,
            )

    except Exception as err:
        _LOGGER.error("Failed to register Lovelace resource: %s", err)


def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the panel from the sidebar and clear the registration flag.

    FIX: The _panel_registered flag must be cleared here. If it survives
    into the next async_setup_entry() call, async_register_panel() skips
    registration entirely — and the following unload then tries to remove
    a panel that was never registered, producing "Removing unknown panel".
    """
    from homeassistant.components import frontend

    # Only call async_remove_panel if we actually registered it
    if hass.data.get(DOMAIN, {}).get("_panel_registered", False):
        frontend.async_remove_panel(hass, DOMAIN)
        _LOGGER.debug("Panel removed from sidebar")
    else:
        _LOGGER.debug("Panel was not registered, skipping removal")

    # Always clear the flag so the next setup registers fresh
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["_panel_registered"] = False


async def async_unregister_cards_resource(hass: HomeAssistant) -> None:
    """Remove the cards Lovelace resource (called on integration unload)."""
    try:
        resources = hass.data.get("lovelace_resources")

        if resources is None:
            lovelace = hass.data.get("lovelace")
            if not lovelace:
                return
            resources = getattr(lovelace, "resources", None)

        if resources is None:
            return

        if not getattr(resources, "loaded", True):
            return

        existing = [
            r for r in resources.async_items()
            if r["url"].startswith(CARDS_URL)
        ]
        for resource in existing:
            await resources.async_delete_item(resource["id"])
            _LOGGER.info("Removed cards resource: %s", resource["url"])

    except Exception as err:
        _LOGGER.debug("Could not remove cards resource: %s", err)
