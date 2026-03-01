# File Name: notification_manager.py
# Version: 2.3.0
# Description: Evaluates notification rules and sends to HA Companion app.
# Last Updated: March 1, 2026

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant

from .store import NotificationStore

if TYPE_CHECKING:
    from . import PCStatisticsCoordinator

_LOGGER = logging.getLogger(__name__)


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}t {m}m"
    return f"{m} minutter"


def _fmt_cost(dkk: float) -> str:
    return f"{dkk:.2f}".replace(".", ",")


class NotificationManager:
    """Evaluates rules against coordinator state and sends push notifications."""

    def __init__(self, hass: HomeAssistant, store: NotificationStore) -> None:
        self._hass = hass
        self._store = store

    async def async_evaluate(self, coordinator: "PCStatisticsCoordinator") -> None:
        """
        Called on every coordinator update.
        Checks each enabled rule against current state and fires if triggered.
        """
        rules = self._store.get_rules()
        devices = self._store.get_devices()

        if not devices:
            return  # No devices configured — nothing to send

        data = coordinator.data or {}
        current_user: str | None = data.get("current_user")
        acc_time: float = data.get("acc_time", 0.0)
        acc_cost: float = data.get("acc_cost", 0.0)
        now = time.time()

        for rule_id, rule in rules.items():
            if not rule.get("enabled"):
                continue

            trigger_type: str = rule.get("trigger_type", "")
            trigger_value: float = float(rule.get("trigger_value", 0))
            user_targets: list[str] = rule.get("user_targets", [])

            # ── idle_pc: no user logged in but power > threshold ──────────
            if trigger_type == "idle_minutes":
                if current_user is None and coordinator.last_power > 10:
                    await self._maybe_send(
                        rule_id=rule_id,
                        rule=rule,
                        user="system",
                        devices=devices,
                        trigger_value=trigger_value,
                        now=now,
                        replacements={
                            "{user}": "system",
                            "{time}": _fmt_time(now - coordinator.last_write_time),
                            "{cost}": _fmt_cost(acc_cost),
                        },
                    )
                continue

            # ── user-based rules ──────────────────────────────────────────
            if not current_user:
                continue

            # Filter by user_targets (empty list = all users)
            if user_targets and current_user not in user_targets:
                continue

            triggered = False

            if trigger_type == "session_minutes":
                triggered = acc_time >= trigger_value * 60

            elif trigger_type == "session_cost":
                triggered = acc_cost >= trigger_value

            if not triggered:
                continue

            await self._maybe_send(
                rule_id=rule_id,
                rule=rule,
                user=current_user,
                devices=devices,
                trigger_value=trigger_value,
                now=now,
                replacements={
                    "{user}": current_user.capitalize(),
                    "{time}": _fmt_time(acc_time),
                    "{cost}": _fmt_cost(acc_cost),
                },
            )

    async def _maybe_send(
        self,
        rule_id: str,
        rule: dict,
        user: str,
        devices: list[str],
        trigger_value: float,
        now: float,
        replacements: dict[str, str],
    ) -> None:
        """Send if enough time has passed since last send (anti-spam)."""
        last_sent = self._store.get_last_sent(rule_id, user)
        repeat: bool = rule.get("repeat", False)
        repeat_interval: float = float(rule.get("repeat_interval", 60)) * 60  # minutes → seconds

        # Non-repeating: only send once per session (reset when user changes)
        if not repeat and last_sent > 0:
            return

        # Repeating: respect interval
        if repeat and (now - last_sent) < repeat_interval:
            return

        await self._send(rule, devices, replacements)
        await self._store.async_mark_sent(rule_id, user, now)

    async def _send(
        self,
        rule: dict,
        devices: list[str],
        replacements: dict[str, str],
    ) -> None:
        """Send push notification to all configured devices."""
        title = rule.get("title", "PC Statistik")
        message = rule.get("message", "")

        for k, v in replacements.items():
            title = title.replace(k, v)
            message = message.replace(k, v)

        for service_path in devices:
            try:
                # service_path = "notify.mobile_app_flemming_phone"
                parts = service_path.split(".", 1)
                if len(parts) != 2:
                    continue
                domain, service = parts
                await self._hass.services.async_call(
                    domain,
                    service,
                    {"title": title, "message": message},
                    blocking=False,
                )
                _LOGGER.debug("Sent notification '%s' via %s", rule.get("name"), service_path)
            except Exception as err:
                _LOGGER.warning("Failed to send notification via %s: %s", service_path, err)

    async def async_send_test(self, rule_id: str, user: str) -> bool:
        """Send a test notification for a specific rule and user."""
        rule = self._store.get_rule(rule_id)
        devices = self._store.get_devices()

        if not rule or not devices:
            return False

        await self._send(
            rule=rule,
            devices=devices,
            replacements={
                "{user}": user.capitalize() if user != "system" else "System",
                "{time}": "1t 23m",
                "{cost}": "7,50",
            },
        )
        _LOGGER.info("Test notification sent for rule '%s'", rule_id)
        return True
