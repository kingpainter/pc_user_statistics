# Changelog

All notable changes to the PC User Statistics Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---
## [2.7.0] - 2026-03-14

### Added

- **Session persistence — overlever HA-genstart midt i en session** (`store.py`, `__init__.py`):
  - Session-state (`current_user`, `acc_time`, `acc_energy`, `acc_cost`, `last_time`) gemmes nu til disk ved hvert succesfuldt InfluxDB-write (~hvert 60s)
  - Ved HA-startup gendannes sessionen automatisk — ingen tid, energi eller pris går tabt
  - Maksimalt tab ved HA-genstart: ~60s (svarer til ét poll-interval)
  - Ingen ekstra disk-writes: session piggybacks på den eksisterende notification-flush
  - Sikkerheds-tjek ved genoprettelse:
    - Snapshot afvises hvis det er ældre end 4 timer (PC var slukket)
    - Snapshot afvises hvis den gemte bruger ikke længere er i `tracked_users`
    - Snapshot afvises hvis en anden bruger allerede er aktiv på sensoren
  - Session ryddes fra disk ved ren logout — ingen ghost-sessions ved næste opstart
  - Nye metoder i `store.py`: `get_session()`, `save_session_in_memory()`, `async_flush_session()`, `async_clear_session()`
  - Ny metode i `__init__.py`: `_async_restore_session()`


## [2.6.2] - 2026-03-08

### Fixed

- **`__init__.py` — Månedlig data loader aldrig fra InfluxDB** (`_async_load_monthly_data`):
  - `datetime.isoformat()` returnerede `2026-03-01T00:00:00+00:00` i WHERE-klausulen
  - InfluxDB 1.x accepterer ikke `+00:00` — kræver `Z`-suffix (RFC3339)
  - Query returnerede tom serie, `_monthly_loaded` forblev `False` permanent
  - System Health viste "Afventer InfluxDB..." og panelet viste spinner for altid
  - **Fix**: Ændret til `.strftime("%Y-%m-%dT%H:%M:%SZ")` — samme mønster som `_query_history()` i `websocket.py` allerede brugte korrekt

- **`__init__.py` — `last_write_time` initialiseret forkert** (`__init__`):
  - `self.last_write_time = time.time()` ved startup gav en falsk "aldrig"-visning
  - System Health viste orange "aldrig" selv under normal drift uden aktiv bruger
  - **Fix**: Initialiseret til `0.0` — nul betyder eksplicit "ingen write endnu"

- **`system_health.py` — System Health viste vildledende statusser**:
  - `monthly_data_loaded` returnerede rå boolean → HA viste ✅/❌ for en forbigående loading-tilstand
  - `last_influxdb_write` viste orange "aldrig" selvom PC blot var idle (ingen aktiv session)
  - **Fix**: `monthly_data_loaded` returnerer nu tekst ("Indlæst ✓" / "Afventer InfluxDB...")
  - **Fix**: `last_influxdb_write` skelner nu mellem "ingen aktiv session" (neutral) og "aldrig" (kun når bruger er aktiv men ingen write er sket)

### Changed

- **`pc-user-statistics-panel.js` — Tab-struktur omstruktureret**:
  - `statistik`-tab (tidligere `statistics`) omdøbt til **`live`** 🎮 — viser udelukkende live session: gauges, tid/energi/pris og donut-fordeling
  - `brugere`-tab (`users`) erstattet af ny **`statistik`**-tab 📊 — viser månedlige totaler per bruger, leaderboard og donut side om side i to-kolonne layout
  - Tab-rækkefølge i `localStorage` opgraderes automatisk — ukendte IDs filtreres og nye tilføjes

---

## [2.6.1] - 2026-03-08

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
