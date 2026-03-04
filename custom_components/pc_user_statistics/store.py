# File Name: store.py
# Version: 2.5.1
# Description: Persistent storage for notification rules using HA store (.storage).
# Last Updated: March 4, 2026
#
# Changes in 2.5.1:
#   - Added mark_sent_in_memory() — updates last_sent in RAM without disk write
#   - Added async_flush() — single disk flush after all rules are evaluated
#     Previously async_mark_sent() wrote to disk on every triggered rule (every 60s)

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.notifications"
STORAGE_VERSION = 1

# ── Premade rule templates ──────────────────────────────────────────────────
PREMADE_RULES: list[dict[str, Any]] = [
    {
        "id": "pause_reminder",
        "name": "Pausepåmindelse",
        "icon": "⏱️",
        "description": "Send påmindelse efter en bestemt spilletid",
        "trigger_type": "session_minutes",
        "trigger_value": 60,
        "title": "⏱️ Tid til en pause, {user}!",
        "message": "Du har spillet i {time} — husk at tage en pause! 🎮",
        "repeat": True,
        "repeat_interval": 60,
    },
    {
        "id": "long_session",
        "name": "Lang session advarsel",
        "icon": "🌙",
        "description": "Advar når en session bliver meget lang",
        "trigger_type": "session_minutes",
        "trigger_value": 180,
        "title": "🌙 Lang session, {user}!",
        "message": "Du har spillet i {time} i dag. Måske tid til at stoppe? 😴",
        "repeat": False,
        "repeat_interval": 0,
    },
    {
        "id": "cost_limit",
        "name": "Prisgrænse",
        "icon": "💰",
        "description": "Advar når sessionen koster over en bestemt pris",
        "trigger_type": "session_cost",
        "trigger_value": 10.0,
        "title": "💰 Prisgrænse nået, {user}!",
        "message": "Denne session har kostet {cost} kr i strøm. 💡",
        "repeat": False,
        "repeat_interval": 0,
    },
    {
        "id": "idle_pc",
        "name": "PC glemt tændt",
        "icon": "🌅",
        "description": "Advar når PC bruger strøm men ingen er logget ind",
        "trigger_type": "idle_minutes",
        "trigger_value": 30,
        "title": "🌅 PC er tændt uden bruger!",
        "message": "PC har brugt strøm i {time} uden nogen logget ind. Husk at slukke! 🔌",
        "repeat": True,
        "repeat_interval": 30,
    },
]


class NotificationStore:
    """Handles persistent storage of notification rules."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Load data from storage, seeding premade rules if first run."""
        stored = await self._store.async_load()

        if stored is None:
            _LOGGER.info("No notification store found — seeding premade rules")
            self._data = self._seed_defaults()
            await self._store.async_save(self._data)
        else:
            self._data = stored
            # Add any new premade rules introduced in newer versions
            updated = False
            for rule in PREMADE_RULES:
                if rule["id"] not in self._data.get("rules", {}):
                    self._data.setdefault("rules", {})[rule["id"]] = {
                        **rule,
                        "enabled": False,
                        "user_targets": [],
                    }
                    updated = True
            if updated:
                await self._store.async_save(self._data)

        _LOGGER.debug("Notification store loaded: %d rules", len(self._data.get("rules", {})))

    def _seed_defaults(self) -> dict[str, Any]:
        """Create default store structure with all premade rules disabled."""
        rules = {}
        for rule in PREMADE_RULES:
            rules[rule["id"]] = {
                **rule,
                "enabled": False,
                "user_targets": [],
            }
        return {
            "rules": rules,
            "devices": [],
            "last_sent": {},
        }

    # ── Rules ───────────────────────────────────────────────────────────────

    def get_rules(self) -> dict[str, Any]:
        """Return all rules."""
        return self._data.get("rules", {})

    def get_rule(self, rule_id: str) -> dict[str, Any] | None:
        """Return a single rule by ID."""
        return self._data.get("rules", {}).get(rule_id)

    async def async_save_rule(self, rule_id: str, config: dict[str, Any]) -> None:
        """Save (create or update) a rule."""
        self._data.setdefault("rules", {})[rule_id] = config
        await self._store.async_save(self._data)
        _LOGGER.debug("Saved rule: %s", rule_id)

    async def async_delete_rule(self, rule_id: str) -> bool:
        """Delete a custom rule. Returns False if it's a premade rule."""
        rule = self._data.get("rules", {}).get(rule_id)
        if not rule:
            return False
        if rule_id in {r["id"] for r in PREMADE_RULES}:
            return False  # Premade rules cannot be deleted — only disabled
        del self._data["rules"][rule_id]
        await self._store.async_save(self._data)
        _LOGGER.debug("Deleted custom rule: %s", rule_id)
        return True

    # ── Devices ─────────────────────────────────────────────────────────────

    def get_devices(self) -> list[str]:
        """Return configured notify service names."""
        return self._data.get("devices", [])

    def get_available_mobile_apps(self, hass: HomeAssistant) -> list[dict[str, str]]:
        """Discover available mobile app notify services from HA."""
        apps = []
        try:
            services = hass.services.async_services().get("notify", {})
            for service_name in services:
                if service_name.startswith("mobile_app_"):
                    friendly = service_name.replace("mobile_app_", "").replace("_", " ").title()
                    apps.append({
                        "service": f"notify.{service_name}",
                        "name": friendly,
                    })
        except Exception as err:
            _LOGGER.warning("Could not discover mobile apps: %s", err)
        return apps

    async def async_save_devices(self, devices: list[str]) -> None:
        """Save configured devices."""
        self._data["devices"] = devices
        await self._store.async_save(self._data)
        _LOGGER.info("Saved %d notification devices", len(devices))

    # ── Sent tracking (anti-spam) ────────────────────────────────────────────

    def get_last_sent(self, rule_id: str, user: str) -> float:
        """Return timestamp of last sent notification for rule+user."""
        key = f"{rule_id}_{user}"
        return self._data.get("last_sent", {}).get(key, 0.0)

    def mark_sent_in_memory(self, rule_id: str, user: str, timestamp: float) -> None:
        """Update last_sent in RAM immediately — no disk write.

        Call async_flush() after all rules are evaluated to batch the write.
        """
        self._data.setdefault("last_sent", {})[f"{rule_id}_{user}"] = timestamp

    async def async_flush(self) -> None:
        """Persist current in-memory state to disk.

        Called once after all notification rules are evaluated, rather than
        writing on every individual rule trigger.
        """
        await self._store.async_save(self._data)
        _LOGGER.debug("Notification store flushed to disk")

    async def async_mark_sent(self, rule_id: str, user: str, timestamp: float) -> None:
        """Mark a notification as sent and persist immediately.

        Use mark_sent_in_memory() + async_flush() for batch evaluation.
        This method is kept for backwards compatibility and single-shot sends.
        """
        self.mark_sent_in_memory(rule_id, user, timestamp)
        await self._store.async_save(self._data)
