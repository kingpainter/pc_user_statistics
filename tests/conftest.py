# File Name: conftest.py
# Description: Shared pytest fixtures for PC User Statistics tests.

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry


# ── Shared config data ─────────────────────────────────────────────────────

MOCK_CONFIG_DATA = {
    "host": "localhost",
    "port": 8086,
    "database": "homeassistant",
    "username": "admin",
    "password": "secret",
}

MOCK_OPTIONS = {
    "tracked_users": ["flemming", "lukas", "sebastian"],
    "user_mappings": "konge=flemming,lukas=lukas,sebas=sebastian",
}

MOCK_USER_MAP = {
    "konge": "flemming",
    "lukas": "lukas",
    "sebas": "sebastian",
}


# ── Config entry fixture ───────────────────────────────────────────────────

@pytest.fixture
def mock_config_entry():
    """Return a mock ConfigEntry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id_123"
    entry.data = MOCK_CONFIG_DATA.copy()
    entry.options = MOCK_OPTIONS.copy()
    entry.title = "PC User Statistics"
    return entry


# ── HA state fixtures ──────────────────────────────────────────────────────

def make_state(entity_id: str, state: str) -> MagicMock:
    """Create a mock HA State object."""
    s = MagicMock()
    s.entity_id = entity_id
    s.state = state
    return s


@pytest.fixture
def mock_hass():
    """Return a minimal mock HomeAssistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.data = {}
    hass.async_create_task = MagicMock()
    return hass


# ── InfluxDB response helpers ──────────────────────────────────────────────

def influxdb_response(user: str, time: float, energy: float, cost: float) -> dict:
    """Build a minimal valid InfluxDB JSON response for one user."""
    return {
        "results": [
            {
                "series": [
                    {
                        "tags": {"user": user},
                        "values": [[None, time, energy, cost]],
                    }
                ]
            }
        ]
    }


def empty_influxdb_response() -> dict:
    """Return an empty but valid InfluxDB response."""
    return {"results": [{}]}
