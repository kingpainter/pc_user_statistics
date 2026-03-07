# Changelog

All notable changes to the PC User Statistics Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.5.0] - 2026-03-07

### Added

- **`diagnostics.py`** — Downloadable debug info from HA UI (Gold quality scale requirement):
  - Exposes integration version, config entry state, coordinator status, tracked users
  - Password intentionally omitted; HA auto-redacts sensitive fields
  - Accessible via Settings → Devices & Services → PC User Statistics → ⋮ → Download diagnostics

- **`quality_scale.yaml`** — Explicit Gold quality scale compliance tracking:
  - All Bronze/Silver/Gold rules mapped with `done`, `todo`, or `exempt` status
  - Replaces manual tracking in `HA_COMPLIANCE.md`

- **`websocket.py` — `monthly_loaded` flag in `get_stats` response**:
  - Panel can now show a loading indicator until InfluxDB monthly data is ready
  - Prevents displaying zeroes during initial startup

- **`strings.json` + `da.json` — `reconfigure` step translations**:
  - Added `reconfigure` step with all field labels (EN + DA)
  - Added `reconfigure_successful` abort message (EN + DA)

### Changed

- **`manifest.json`** — Version bumped to `2.5.0`
- **`const.py`** — `__version__` already at `2.5.0` (set in previous session)
- **`sensor.py`** — `EntityCategory.DIAGNOSTIC` on hub sensors (set in previous session)
- **`sensor.py`** — `available` property on all sensors (set in previous session)
- **`config_flow.py`** — `reconfigure` step added (set in previous session)
- **`__init__.py`** — `ConfigEntryAuthFailed` (HTTP 401), `ConfigEntryNotReady` (startup failure), exponential backoff retry for `_async_load_monthly_data` (set in previous session)

---

## [2.4.1] - 2026-03-03

### Fixed

- **`__init__.py` — Tidsmåling forkert ved brugerskift** (`_handle_user_change`):
  - `self.last_time` blev ikke nulstillet inden ny bruger startede akkumulering
  - Første delta for ny bruger inkluderede tid fra forrige brugers session (phantom-tid)
  - Fix: `self.last_time = now` sættes nu inde i `_handle_user_change` ved hvert brugerskift

- **`__init__.py` — Akkumulerende deltas ved 60s polling** (`_async_update_data`):
  - `self.last_time` blev aldrig opdateret efter `_calculate_deltas()` i polling-løkken
  - Resulterede i voksende delta-vinduer: poll #1 = 60s, poll #2 = 120s, poll #3 = 180s osv.
  - Fix: `self.last_time = now` tilføjet efter `_calculate_deltas()` i `_async_update_data`

- **`websocket.py` — WS-forbindelse crashede ved gem af konfiguration** (`ws_save_config`):
  - `async_update_entry()` triggede `add_update_listener` → `async_reload()` synkront
  - Integration unloadede mens WebSocket-svaret endnu ikke var sendt → panel frøs
  - Fix: `connection.send_result()` sendes først, reload scheduleres via `async_create_task()`

- **`websocket.py` — HA mobil-bruger forsvandt efter reload** (`ws_get_config`):
  - Returnerede `coordinator.user_map` (normaliseret — `ha_user` smidt væk)
  - Fix: Returnerer nu raw `entry.options` så `ha_user` dict-værdier bevares

- **`config_flow.py` — `AttributeError` ved åbning af optionsflow** (`OptionsFlow`):
  - `OptionsFlow.__init__` satte `self.config_entry` som HA 2024+ har gjort til read-only property
  - Fix: `__init__` fjernet — HA injekterer `config_entry` automatisk via base-klassen

- **`panel.py` — "Removing unknown panel" i loggen ved reload**:
  - `_panel_registered` flag overlevede integration-reload → `async_register_panel()` sprang over
  - Efterfølgende unload kaldte `async_remove_panel()` på et panel der ikke eksisterede
  - Fix: `async_unregister_panel()` nulstiller nu altid `_panel_registered = False`

- **`manifest.json` — Forældet `influxdb==5.3.2` requirement fjernet**:
  - Integration bruger udelukkende `aiohttp` til InfluxDB-kommunikation (siden v2.0.0)
  - `influxdb` Python-pakken var aldrig i brug og kunne forårsage installationsfejl

### Changed

- **`pc-user-statistics-panel.js` — Tab-ikoner gjort større og centreret**:
  - Ikon-størrelse: `18px` → `30px`
  - Gap mellem ikon og label: `2px` → `5px`
  - Tab-padding: `10px/14px` → `14px/20px`
  - Tabs centreret i stedet for venstre-aligned (`justify-content: center`)

---

## [2.4.0] - 2026-03-02

### Added

- **Persistent `aiohttp.ClientSession`** (`__init__.py`):
  - Én HTTP-session oprettes ved setup og genbruges til alle InfluxDB-kald
  - Lukkes rent i `async_shutdown()` ved integration-unload
  - Eliminerer overhead fra gentagne session-oprettelser

- **Smart tab-aware polling** (`pc-user-statistics-panel.js`):
  - `_loadForTab()` bruges i 30s polling — henter kun data relevant for aktiv tab
  - Historik- og konfigurationstabs auto-refreshes aldrig
  - `_load()` bruges kun ved første connect og manuel Opdater-knap

- **`async_track_state_change_event`** (`__init__.py`):
  - Erstatter global `EVENT_STATE_CHANGED` bus
  - HA filtrerer events på kilden — langt mere effektivt

- **`async_shutdown()`** (`__init__.py`):
  - Lukker persistent HTTP-session rent ved integration-unload

### Fixed

- Monthly data race condition: snapshot tages før InfluxDB-load, merges efter
- `_query_history` i `websocket.py` genbruger nu koordinatorens persistente session

---

## [2.3.2] - 2026-03-02

### Fixed

- Mobil-responsivt CSS: tab-labels skjules på skærme under 600px
- Notifikations-layout optimeret til mobilvisning
- Diverse CSS-justeringer for bedre mobiloplevelse

---

## [2.3.1] - 2026-03-01

### Fixed

- Lovelace resource registrering fejlede med HA 2024.x API-ændringer
  - `hass.data["lovelace"].resources` erstattet med `hass.data["lovelace_resources"]`
  - Fallback til ældre API for bagudkompatibilitet
- Panel registreret med `module_url` (ES module) i stedet for `js_url`

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
  - Halvcirkel watt-gauge med live strømforbrug opdateret fra HA state
  - Gradient header-baggrund under aktiv session
  - Farveskala grøn → gul → rød baseret på watt-belastning

- **Leaderboard** (Statistik-tab)
  - Månedlig rangering med 🥇🥈🥉 medaljer
  - Animerede søjler med cubic-bezier
  - Guld-gradient-ramme til #1-pladsen

- **Notification System** (`store.py`, `notification_manager.py`)
  - Persistent storage i `.storage/pc_user_statistics.notifications`
  - 4 premade regler (alle deaktiveret som standard)
  - Opret/rediger/slet egne regler
  - Anti-spam, test-knap, template-variabler: `{user}`, `{time}`, `{cost}`

- **Historik-tab**: SVG søjlediagram, daglige totaler, 30 dage, lazy-load
- **Konfiguration-tab**: Rediger entity IDs og bruger-mappings direkte i UI
- **WebSocket API** (`websocket.py`): 11 kommandoer

### Changed

- Entity IDs er nu dynamiske — læses fra `config_entry.data`
- Admin-only panel (`require_admin=True`), Lovelace cards tilgængelige for alle

---

## [2.0.2] - 2026-03-01

### Fixed

- `MonthlyCostSensor`: `TOTAL_INCREASING` → `TOTAL` (HA 2024+ krav for `MONETARY`)
- Tilføjet manglende konstanter til `const.py`: `CONF_USER_MAPPINGS`, `CONF_TRACKED_USERS`, `DEFAULT_USER_MAP`, `DEFAULT_USERS`

---

## [2.0.1] - 2026-03-01

### Fixed

- JS `SyntaxError: Invalid or unexpected token` — escaped backticks renset ud

---

## [2.0.0] - 2026-01-11

### 🎉 Major Release — Complete Restructure

- Integration omdøbt: `spille_pc_statistik` → `pc_user_statistics`
- Fuld device-struktur: Hub device + per-bruger devices med `via_device`
- Silver quality scale: type hints, device classes, `has_entity_name = True`
- 100-point FIFO write buffer med 3 retry-forsøg
- Config flow med InfluxDB-validering

---

## [1.0.8] - 2025-12-24

### Changed

- Default InfluxDB database: `"stroemforbrug"` → `"homeassistant"`

---

## [1.0.0] - 2025-09-15

### Added

- Initial release — strømforbrug, tid og pris per bruger via InfluxDB
