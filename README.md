# PC User Statistics

[![Version](https://img.shields.io/badge/version-2.10.0-blue.svg)](https://github.com/kingpainter/pc_user_statistics)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)](https://www.home-assistant.io/)
[![Quality Scale](https://img.shields.io/badge/quality-silver%20→%20gold-gold.svg)](https://developers.home-assistant.io/docs/integration_quality_scale_index/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A Home Assistant custom integration for tracking gaming PC usage statistics per user. Monitor power consumption, session time, and electricity costs — with a full custom sidebar panel, historical graphs, push notifications, and more.

---

## 📋 Features

### ✅ What It Does

- **Multi-User Tracking**: Individual statistics per user, configurable via UI
- **Live Session Monitoring**: Real-time power (watt gauge), time, and cost tracking
- **Monthly Summaries**: Automated monthly statistics per user
- **Historical Graphs**: Daily bar charts for the last 30 days per metric
- **Leaderboard**: Monthly ranking with 🥇🥈🥉 medals
- **Push Notifications**: Configurable rules with test and repeat support
- **InfluxDB Integration**: Long-term data storage for historical analysis
- **Custom Sidebar Panel**: Full-featured UI built directly into Home Assistant
- **Dark/Light Theme**: Automatically follows your HA theme
- **Multi-Language Support**: English and Danish translations included

### 📊 Tracked Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| **Session Time** | seconds | Active PC usage time for current session |
| **Session Energy** | kWh | Power consumption for current session |
| **Session Cost** | DKK | Electricity cost for current session |
| **Monthly Time** | seconds | Total usage time for current month |
| **Monthly Energy** | kWh | Total power consumption for current month |
| **Monthly Cost** | DKK | Total electricity cost for current month |

---

## 🚀 Installation

### Prerequisites

- **Home Assistant**: 2024.1 or newer
- **InfluxDB**: Running and accessible (v1.x)
- **Required Sensors**:
  - User login sensor (returns current username as state)
  - Power consumption sensor (PC wattage in W)
  - Energy price sensor (DKK per kWh)
  - *(Optional)* Device self-consumption sensor (only needed for plugs that expose it separately)

### Manual Installation

1. Copy the `custom_components/pc_user_statistics/` folder to your HA `/config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings** → **Devices & Services** → **+ Add Integration**
4. Search for **PC User Statistics**
5. Enter your InfluxDB connection details

### HACS (Coming Soon)

*HACS submission pending*

---

## ⚙️ Configuration

### Initial Setup (Config Flow)

| Field | Example | Description |
|-------|---------|-------------|
| **Host** | `a0d7b954-influxdb` | InfluxDB hostname or IP |
| **Port** | `8086` | InfluxDB port |
| **Database** | `homeassistant` | Database name |
| **Username** | `homeassistant` | InfluxDB username |
| **Password** | `••••••••` | InfluxDB password |

The integration will verify the InfluxDB connection, confirm the database exists, load existing monthly data, and start tracking immediately.

### Sensor & User Configuration (Panel UI)

After setup, open the **🔧 Konfiguration** tab in the sidebar panel to:

- Edit all 4 sensor entity IDs without touching any files
- Add, edit, or remove user mappings (sensor state → user ID)
- Reorder sidebar tabs via drag-and-drop

Changes are saved instantly and trigger an automatic integration reload.

---

## 🖥️ Sidebar Panel

The integration adds a **🎮 PC Statistik** entry to your HA sidebar with 6 tabs:

### 📊 Statistik
- Live session cards (tid, energi, pris)
- Donut-diagram med månedlig fordeling per bruger
- Månedlige totalkort per bruger
- 🏆 Leaderboard med guld/sølv/bronze ranking

### 👤 Brugere
- Aktiv bruger med LIVE-badge
- Oversigt over alle konfigurerede brugere og sensor-mappings

### 🔔 Notifikationer
- Konfigurer modtagerenheder (HA Companion app)
- 4 premade regler klar til brug:
  - ⏱️ **Pausepåmindelse** — gentages hvert 60 min
  - 🌙 **Lang session** — advarsel efter 3 timer
  - 💰 **Prisgrænse** — notifikation ved 10 kr
  - 🌅 **PC glemt tændt** — gentages hvert 30 min ved inaktivitet
- Opret egne regler med valgfri trigger, besked og repeat-interval
- Test-knap sender øjeblikkelig push

### 📈 Historik
- SVG søjlediagram — daglige totaler de seneste 30 dage
- Skift mellem Tid / Energi / Pris
- 7-dages tabel med mini-søjler per bruger

### 🔧 Konfiguration
- Rediger sensor entity IDs
- Administrer bruger-mappings
- Omarranger tabs via drag-and-drop

### ⚙️ Admin
- System-info og version
- InfluxDB write buffer status
- Bruger-mappings oversigt

---

## 🔌 Supported Devices

### Smart Power Plug

The integration requires a smart plug with power monitoring. The plug's watt sensor is read every 60 seconds to track energy consumption and cost.

#### ✅ TP-Link Kasa HS110 (tested)

| | |
|---|---|
| **Hardware version** | 1.0 |
| **Firmware version** | 1.2.6 |
| **HA integration** | TP-Link Smart Home (built-in) |
| **Local control** | Yes — no cloud account required |
| **HA polling** | Every 5 seconds |

The HS110 exposes a `current_consumption` sensor (W) that is used directly for watt tracking. It does **not** expose a separate device self-consumption sensor — the "Plug self-power" field in the configuration should be left empty when using HS110.

> ⚠️ **Do not update HS110 firmware.** Firmware version 1.1.0 on certain hardware revisions
> broke local Home Assistant access. Version 1.2.6 on HW 1.0 is stable.

**Entity IDs created by HS110** (example device name `gamer_pc_power_monitor`):

| Sensor | Entity ID | Unit |
|--------|-----------|------|
| Current power | `sensor.gamer_pc_power_monitor_current_consumption` | W |
| Total energy | `sensor.gamer_pc_power_monitor_total_consumption` | kWh |

#### Other compatible plugs

Any smart plug that exposes a watt (W) sensor in Home Assistant will work. The "Plug self-power" field is optional and only relevant for plugs that report their own power draw separately (e.g. Shelly Plug S/Plus).

---

### User Login Sensor (HASS.Agent)

[HASS.Agent](https://github.com/LAB02-Research/HASS.Agent) runs on the Windows gaming PC and reports the currently logged-in Windows username as a HA sensor state.

| | |
|---|---|
| **Platform** | Windows only |
| **Sensor type** | Logged In Users / Windows User |
| **State example** | `Konge`, `Lukas`, `Sebas` |
| **Entity example** | `sensor.flemming_gamer_satellite_loggeduser` |

The sensor state is matched to a user ID via the mappings configured in the **🔧 Konfiguration** tab.

---

### Electricity Price Sensor

Any sensor returning a float value in **DKK per kWh** is supported. For Danish users, [Energi Data Service](https://www.home-assistant.io/integrations/energi_data_service/) (available via HACS) provides real-time spot prices including tariffs.

---

## 🔌 Device Structure

### Statistics Hub
- `sensor.statistics_hub_current_user`
- `sensor.statistics_hub_current_session_time`
- `sensor.statistics_hub_current_session_energy`
- `sensor.statistics_hub_current_session_cost`

### Per-User Devices (e.g. Statistics Flemming)
- `sensor.statistics_flemming_monthly_time`
- `sensor.statistics_flemming_monthly_energy`
- `sensor.statistics_flemming_monthly_cost`

*(Same pattern for each configured user)*

---

## 📈 InfluxDB Data Structure

**Measurement**: `pc_usage`  
**Write frequency**: Every 60 seconds (when user is active)

| Field | Type | Description |
|-------|------|-------------|
| `power` | float | Current power in watts |
| `time_delta` | float | Seconds since last write |
| `energy_delta` | float | kWh since last write |
| `cost_delta` | float | DKK since last write |

**Tags**: `user` (string)

```sql
-- Total energy per user this month
SELECT SUM("energy_delta") AS "total_energy"
FROM "pc_usage"
WHERE time >= now() - 30d
GROUP BY "user"
```

---

## 🔄 Data Update Strategy

The integration uses a **DataUpdateCoordinator** with a 60-second polling interval.

| Event | What happens |
|-------|-------------|
| **State change** (user/power sensor) | `async_track_state_change_event` triggers immediately |
| **Every 60 seconds** | Coordinator polls, calculates deltas, writes to InfluxDB |
| **HA startup** | Monthly totals loaded from InfluxDB with exponential backoff (30s / 60s / 120s) |
| **InfluxDB write failure** | Point buffered (FIFO, max 100) and retried next poll |
| **5+ consecutive failures** | RepairIssue raised in HA UI — visible under Settings → Repairs |

Deltas (time, energy, cost) are only written to InfluxDB when a user is actively logged in and the power sensor reports a positive value.

---

## ⚠️ Known Limitations

- **InfluxDB v1.x only** — InfluxDB v2.x / v3.x is not supported
- **Single PC** — one integration instance tracks one PC; multi-PC requires multiple config entries (planned for v3.0.0)
- **DKK currency** — electricity cost is calculated in Danish Krone (DKK); other currencies require a matching energy price sensor
- **No historical import** — data tracking starts from the moment the integration is installed; existing InfluxDB data from other sources is not imported
- **HA Companion app required** for push notifications — standard HA notify services are not supported in the notification UI

---

## 🛠️ Troubleshooting

### Sensors show "Unavailable"
Check that all required sensors exist and are working. Verify entity IDs in the **🔧 Konfiguration** panel tab, or check HA logs filtered by `pc_user_statistics`.

### Monthly data not loading
Verify InfluxDB is running and accessible. Check that the `pc_usage` measurement exists. Reload the integration: **Settings → Devices & Services → PC User Statistics → ⋮ → Reload**

### No push notifications received
1. Install the Home Assistant Companion app on your phone
2. Open the **🔔 Notifikationer** tab and select your device
3. Enable at least one rule and use the **📨 Test** button to verify

### Negative or incorrect power values
Expected when PC is idle — the integration clamps negative values to 0.

### Panel not appearing in sidebar
Restart Home Assistant fully (not just reload). If the panel JS file was updated, clear your browser cache.

---

## 🔄 Migration from 1.x

1. Backup any automations/dashboards using old entity IDs
2. Delete old integration (**Settings → Devices & Services → Spille PC Statistik → Delete**)
3. Install new integration and configure with your InfluxDB details
4. Update entity ID references (see [CHANGELOG.md](CHANGELOG.md))

Your historical data in InfluxDB is **not** affected.

---

## 📝 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- Home Assistant community for integration guidelines
- InfluxDB for time-series data storage

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/kingpainter/pc_user_statistics/issues)
- **Discussions**: [GitHub Discussions](https://github.com/kingpainter/pc_user_statistics/discussions)

---

**Made with ❤️ for the Home Assistant community**
