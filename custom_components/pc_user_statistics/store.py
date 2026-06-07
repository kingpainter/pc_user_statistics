# File Name: store.py
# Version: 2.8.0
# Description: Persistent storage for notification rules using HA store (.storage).
# Last Updated: June 5, 2026
#
# Changes in 2.8.0:
#   NEW: Split storage into two independent keys:
#        - pc_user_statistics.config  — notification rules + devices
#        - pc_user_statistics.session — session snapshot only
#        Isolates corruption: a corrupt session file no longer wipes rules/devices
#        and vice versa. Session key is flushed aggressively (every 60s) while
#        config key is only written on actual rule/device changes.

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.config"
SESSION_STORAGE_KEY = f"{DOMAIN}.session"
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
    """Handles persistent storage of notification rules and session state.

    Two separate storage keys are used:
      - pc_user_statistics.config   — notification rules and device list
      - pc_user_statistics.session  — session snapshot (flushed every 60s)

    Splitting them means a corrupt/stale session file cannot wipe notification
    rules and vice versa.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._session_store: Store = Store(hass, STORAGE_VERSION, SESSION_STORAGE_KEY)
        self._data: dict[str, Any] = {}
        self._session_data: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Load data from both storage keys, seeding premade rules if first run."""
        # ── Config store (rules + devices) ──────────────────────────────────
        try:
            stored = await self._store.async_load()
        except Exception as err:
            _LOGGER.error(
                "Failed to load config store (corrupt storage?) — seeding defaults: %s", err
            )
            stored = None

        if stored is None:
            _LOGGER.info("No config store found — seeding premade rules")
            self._data = self._seed_defaults()
            await self._store.async_save(self._data)
        else:
            self._data = stored
            self._data.setdefault("last_sent", {})
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

        # ── Session store (snapshot only) ───────────────────────────────────
        try:
            session_stored = await self._session_store.async_load()
            self._session_data = session_stored if isinstance(session_stored, dict) else {}
        except Exception as err:
            _LOGGER.warning(
                "Failed to load session store — starting fresh session: %s", err
            )
            self._session_data = {}

        _LOGGER.debug(
            "Stores loaded: %d rules, session=%s",
            len(self._data.get("rules", {})),
            "present" if self._session_data else "empty",
        )

    def _seed_defaults(self) -> dict[str, Any]:
        """Create default config store structure with all premade rules disabled."""
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
        """Return a shallow copy of all rules.

        Returns a copy rather than the live dict to prevent RuntimeError if a
        WebSocket handler modifies rules while notification_manager is iterating.
        """
        return dict(self._data.get("rules", {}))

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

    def reset_session_sent(self, user: str) -> None:
        """Clear last_sent for all rules for a user on new session start.

        Called when a user's session starts so all per-session rules fire again.
        Removes every key matching <rule_id>_<user> from last_sent regardless
        of repeat setting — repeating rules will re-arm from the new session
        start, and non-repeating rules get a clean slate for the next session.
        """
        last_sent = self._data.get("last_sent", {})
        suffix = f"_{user}"
        keys_to_delete = [k for k in last_sent if k.endswith(suffix)]
        for key in keys_to_delete:
            del last_sent[key]
        if keys_to_delete:
            _LOGGER.debug("Cleared last_sent for user '%s' on new session (%d entries)", user, len(keys_to_delete))

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
        This method is kept for single-shot sends (e.g. test notifications).
        """
        self.mark_sent_in_memory(rule_id, user, timestamp)
        await self._store.async_save(self._data)

    # ── Session persistence ──────────────────────────────────────────────────

    def get_session(self) -> dict[str, Any] | None:
        """Return the last saved session snapshot from the dedicated session store.

        Returns None if no session has been saved yet (first run / after clear).
        """
        if not self._session_data:
            return None
        return self._session_data

    def save_session_in_memory(
        self,
        current_user: str | None,
        acc_time: float,
        acc_energy: float,
        acc_cost: float,
        last_time: float,
        ms_screen_time: int | None = None,
        ms_screen_time_date: str | None = None,
    ) -> None:
        """Update session snapshot in RAM — no disk write.

        Call async_flush_session() afterwards to persist to the dedicated session store.

        ms_screen_time: Microsoft Family Safety screen_time in minutes at snapshot time.
        ms_screen_time_date: ISO date string (YYYY-MM-DD) the screen_time belongs to.
        Both are optional — only set when a Family Safety mapping exists for the user.
        """
        self._session_data = {
            "current_user": current_user,
            "acc_time": acc_time,
            "acc_energy": acc_energy,
            "acc_cost": acc_cost,
            "last_time": last_time,
            "saved_at": time.time(),
            "ms_screen_time": ms_screen_time,
            "ms_screen_time_date": ms_screen_time_date,
        }

    async def async_flush_session(self) -> None:
        """Persist session snapshot to the dedicated session store.

        Uses a separate storage key from config/rules so frequent session
        writes (every 60s) do not touch the config store.
        """
        await self._session_store.async_save(self._session_data)
        _LOGGER.debug("Session snapshot flushed to disk")

    async def async_clear_session(self) -> None:
        """Clear the session snapshot from the dedicated session store.

        Called on clean logout so a stale session is never restored on the
        next HA startup. Does NOT affect notification rules or devices.
        """
        self._session_data = {}
        await self._session_store.async_save({})
        _LOGGER.debug("Session snapshot cleared from disk")
