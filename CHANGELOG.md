# Changelog

All notable changes to the PC User Statistics Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.3.0] - 2026-03-01

### 🎉 Major Feature Release — Custom Panel & Notification System

### Added

- **Custom Sidebar Panel** (`panel.py` + `frontend/pc-user-statistics-panel.js`)
  - Full-featured vanilla JS panel registered in HA sidebar
  - Shadow DOM, no external imports — zero dependency on Lit or other frameworks
  - Automatic dark/light theme detection via `hass.themes.darkMode`
  - 6 tabs: Statistik, Brugere, Notifikationer, Historik, Konfiguration, Admin
  - Drag-and-drop tab reordering saved in `sessionStorage`

- **Live Header**
  - Pulserende ring-animation når en bruger spiller (sonar-effekt)
  - HalvCircel watt-gauge med live strømforbrug opdateret fra HA state
  - Gradient header-baggrund under aktiv session
  - Farveskala grøn → gul → rød baseret på watt-belastning

- **Leaderboard** (Statistik-tab)
  - Månedlig rangering med 🥇🥈🥉 medaljer
  - Animerede søjler med cubic-bezier
  - Guld-gradient-ramme til #1-pladsen

- **Notification System** (`store.py`, `notification_manager.py`)
  - Persistent storage i `.storage/pc_user_statistics.notifications`
  - 4 premade regler (alle deaktiveret som standard):
    - ⏱️ Pausepåmindelse (gentages hvert 60 min)
    - 🌙 Lang session advarsel (én gang ved 3 timer)
    - 💰 Prisgrænse (én gang ved 10 kr)
    - 🌅 PC glemt tændt (gentages hvert 30 min ved inaktivitet)
  - Opret/rediger/slet egne regler
  - Inline rediger premade regler (trigger-værdi, besked, repeat)
  - Test-knap sender øjeblikkeligt push til konfigurerede enheder
  - Anti-spam: ikke-gentagne regler fyrer én gang per session
  - Template-variabler: `{user}`, `{time}`, `{cost}` i titel og besked

- **Historik-tab**
  - SVG søjlediagram — daglige totaler per bruger, seneste 30 dage
  - Metric-vælger: Tid / Energi / Pris
  - 7-dages tabel med mini-søjler og daglige værdier
  - Lazy-load — data hentes kun første gang tab klikkes

- **Konfiguration-tab**
  - Rediger sensor entity IDs direkte i UI (bruger, watt, måler, pris)
  - Dynamisk bruger-mappings tabel — tilføj/fjern brugere
  - Gem → trigger automatisk integration-reload via `_async_options_updated`
  - Drag-and-drop tab-rækkefølge med visuelt feedback

- **WebSocket API** (`websocket.py`) — 11 kommandoer:
  - `get_stats`, `get_system`
  - `get_notifications`, `save_notification`, `delete_notification`, `test_notification`
  - `get_devices`, `save_devices`
  - `get_history` — InfluxDB `GROUP BY time(1d), "user"` for op til 90 dage
  - `get_config`, `save_config`

### Changed

- Entity IDs er nu dynamiske — læses fra `config_entry.data` med fallback til konstanter
- `_async_options_updated` listener registreret ved setup for automatisk reload ved konfigurationsændringer
- Panel registreret med `js_url` (ikke `module_url`) for korrekt browser-loading

### Fixed

- JS `SyntaxError: Unexpected token 'class'` — panel omskrevet til vanilla `HTMLElement`, ingen ES module imports
- `monthly_cost` sensor: `TOTAL_INCREASING` → `TOTAL` (korrekt for `MONETARY` device class)
- Manglende `CONF_USER_MAPPINGS`, `CONF_TRACKED_USERS`, `DEFAULT_USER_MAP`, `DEFAULT_USERS` konstanter i `const.py`

---

## [2.0.2] - 2026-03-01

### Fixed

- `MonthlyCostSensor`: `SensorStateClass.TOTAL_INCREASING` → `SensorStateClass.TOTAL`
  — HA 2024+ tillader kun `TOTAL` eller `None` for `MONETARY` device class
- Tilføjet manglende konstanter til `const.py`:
  - `CONF_USER_MAPPINGS`, `CONF_TRACKED_USERS`
  - `DEFAULT_USER_MAP`, `DEFAULT_USERS`
  - `USER_MAP` og `USERS` bevaret som aliases til bagudkompatibilitet

### Changed

- Version bumped: `2.0.1` → `2.0.2` i `const.py` og `manifest.json`

---

## [2.0.1] - 2026-03-01

### Fixed

- JS `SyntaxError: Invalid or unexpected token` — escaped backticks fra Python string-erstatninger renset ud
- `_headerHTML` omskrevet til ren string-konkatenation (ingen template literals)

---

## [2.0.0] - 2026-01-11

### 🎉 Major Release - Complete Restructure

This release represents a complete restructure of the integration to meet Home Assistant's Silver quality scale requirements and modern best practices.

### ⚠️ Breaking Changes

- **Integration domain renamed**: `spille_pc_statistik` → `pc_user_statistics`
  - **Action required**: You must remove the old integration and reconfigure
  - Entity IDs will change (e.g., `sensor.flemming_monthly_time` → `sensor.statistics_flemming_monthly_time`)
  - Update any automations, scripts, or dashboards that reference the old entity IDs

### Added

- **Device Organization**: Full device structure implementation
  - Hub device: "Statistics Hub" with global sensors
  - User devices: Individual devices per user (Flemming, Lukas, Sebastian)
  - Proper device linking via `via_device`
- **New Files**:
  - `helpers.py`: Shared parsing, validation, and formatting utilities
  - `strings.json`: English translations (default language)
  - `README.md`: Comprehensive user documentation
  - `PLANNED_FEATURES.md`: Roadmap for future development
  - `HA_COMPLIANCE.md`: Quality scale compliance documentation
- **Version Consistency**: `__version__` constant in `const.py` synchronized with `manifest.json`
- **Enhanced Validation**: Config validation, safe state parsing, InfluxDB response handling
- **Type Hints**: Complete type annotations throughout codebase
- **Error Handling**: Comprehensive try/except blocks with proper logging levels
- **Data Buffering**: 100-point FIFO write buffer for failed InfluxDB writes
- **Retry Logic**: Up to 3 retry attempts per buffered write
- **Unit Tests**: >80% coverage (`tests/test_helpers.py`, `tests/test_init.py`)

### Changed

- `has_entity_name = True` for all sensors (HA 2024+ naming)
- Base classes `PCStatisticsHubSensor` and `PCStatisticsUserSensor`
- Native value return (no more string formatting in sensors)
- Proper device classes: DURATION, ENERGY, MONETARY
- Users and mappings loaded from config entry options (not hardcoded)

### Fixed

- Session reset logic: `acc_time` no longer resets on user → None
- InfluxDB response parsing: robust handling of malformed data
- Negative power values clamped to 0
- Proper handling of "unavailable" and "unknown" sensor states

---

## [1.0.8] - 2025-12-24

### Changed

- Updated default InfluxDB database name from "stroemforbrug" to "homeassistant"
- Added `DEFAULT_DATABASE` constant in `const.py`

---

## [1.0.7] - 2025-09-16

### Fixed

- Resolved circular import issue in `__init__.py`

---

## [1.0.6] - 2025-09-15

### Fixed

- Replaced `async_forward_entry_setup` with `async_forward_entry_setups`
- Improved InfluxDB response handling for empty responses
- Replaced synchronous InfluxDB write with async aiohttp POST

---

## [1.0.5] - 2025-09-15

### Fixed

- Replaced synchronous `client.query` with async aiohttp request

---

## [1.0.4] - 2025-09-15

### Fixed

- Resolved setup failure with proper file structure and debug logging

---

## [1.0.3] - 2025-09-15

### Fixed

- Corrected `TypeError` when parsing InfluxDB `SHOW DATABASES` response

### Added

- `CHANGELOG.md` file for version history

---

## [1.0.2] - 2025-09-15

### Fixed

- Fixed `TypeError` in InfluxDB response parsing
- Improved validation and logging

### Added

- Version control headers in all files
- Danish translations in `translations/da.json`

---

## [1.0.1] - 2025-09-15

### Fixed

- Replaced synchronous database query with async aiohttp request

### Added

- Danish translations support

---

## [1.0.0] - 2025-09-15

### Added

- Initial release of Spille PC Statistik integration
- Power consumption, time, and cost tracking for three users
- InfluxDB data storage
- Live and monthly statistics sensors
- Lovelace dashboard configuration
- Config flow for setup

---

## Migration Guide: 1.x → 2.0.0

### Step 1: Backup Your Data

Your historical data in InfluxDB will **not** be affected, but entity IDs will change.

### Step 2: Remove Old Integration

1. Go to **Settings** → **Devices & Services**
2. Find **Spille PC Statistik** → Click **Delete**

### Step 3: Install New Integration

1. Copy `custom_components/pc_user_statistics/` to your HA config
2. Restart Home Assistant
3. Go to **Settings** → **Devices & Services** → **Add Integration**
4. Search for **PC User Statistics** and configure with your InfluxDB details

### Step 4: Update Entity ID References

| Old Entity ID | New Entity ID |
|---------------|---------------|
| `sensor.current_user` | `sensor.statistics_hub_current_user` |
| `sensor.current_session_time` | `sensor.statistics_hub_current_session_time` |
| `sensor.current_session_energy` | `sensor.statistics_hub_current_session_energy` |
| `sensor.current_session_cost` | `sensor.statistics_hub_current_session_cost` |
| `sensor.flemming_monthly_time` | `sensor.statistics_flemming_monthly_time` |
| `sensor.flemming_monthly_energy` | `sensor.statistics_flemming_monthly_energy` |
| `sensor.flemming_monthly_cost` | `sensor.statistics_flemming_monthly_cost` |
| *(same pattern for Lukas and Sebastian)* | *(same pattern)* |

---

[2.3.0]: https://github.com/kingpainter/pc_user_statistics/releases/tag/v2.3.0
[2.0.2]: https://github.com/kingpainter/pc_user_statistics/releases/tag/v2.0.2
[2.0.1]: https://github.com/kingpainter/pc_user_statistics/releases/tag/v2.0.1
[2.0.0]: https://github.com/kingpainter/pc_user_statistics/releases/tag/v2.0.0
[1.0.8]: https://github.com/kingpainter/pc_user_statistics/releases/tag/v1.0.8
[1.0.7]: https://github.com/kingpainter/pc_user_statistics/releases/tag/v1.0.7
