# PC User Statistics

[![Version](https://img.shields.io/badge/version-2.5.0-blue.svg)](https://github.com/kingpainter/pc_user_statistics)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)](https://www.home-assistant.io/)
[![Quality Scale](https://img.shields.io/badge/quality-silver%20→%20gold-gold.svg)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A Home Assistant custom integration for tracking gaming PC usage statistics per user. Monitor power consumption, session time, and electricity costs — with a full custom sidebar panel, historical graphs, push notifications, and more.

---

## 📋 Features

- **Multi-User Tracking** — Individual statistics per user, configured via UI
- **Live Session Monitoring** — Real-time power (watt gauge), time, and cost
- **Monthly Summaries** — Automatic monthly totals per user, loaded from InfluxDB at startup
- **Historical Graphs** — Daily bar charts for the last 30 days per metric
- **Leaderboard** — Monthly ranking with 🥇🥈🥉 medals
- **Push Notifications** — Configurable rules with anti-spam, repeat, and test support
- **InfluxDB Integration** — Long-term time-series data storage
- **Custom Sidebar Panel** — Full-featured UI built directly into Home Assistant (6 tabs)
- **Dark/Light Theme** — Automatically follows your active HA theme
- **Diagnostics** — Download debug info from the HA UI
- **Reconfigure** — Update InfluxDB credentials without re-installing
- **Multi-Language** — English and Danish translations included

### 📊 Tracked Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| **Session Time** | s | Active usage time for current session |
| **Session Energy** | kWh | Power consumption for current session |
| **Session Cost** | DKK | Electricity cost for current session |
| **Monthly Time** | s | Total usage time this month |
| **Monthly Energy** | kWh | Total power consumption this month |
| **Monthly Cost** | DKK | Total electricity cost this month |

---

## 🚀 Installation

### Prerequisites

| Component | Required | Purpose |
|-----------|----------|---------|
| Home Assistant 2024.1+ | ✅ | Platform |
| InfluxDB 1.x | ✅ | Long-term data storage |
| Smart plug with power monitoring | ✅ | Watt measurement (e.g. Shelly Plug S) |
| HASS.Agent (Windows) | ✅ | Logged-in user detection |
| Energi Data Service | ✅ | Real-time electricity price (DKK/kWh) |
| HA Companion App | ⭕ Optional | Push notifications |

### Manual Installation

1. Copy the `custom_components/pc_user_statistics/` folder to your HA `/config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → + Add Integration**
4. Search for **PC User Statistics**
5. Enter your InfluxDB connection details

### HACS

*HACS submission planned for v3.0.0*

---

## ⚙️ Configuration

### Initial Setup

| Field | Example | Description |
|-------|---------|-------------|
| **Host** | `a0d7b954-influxdb` | InfluxDB hostname or IP |
| **Port** | `8086` | InfluxDB port |
| **Database** | `homeassistant` | Database name |
| **Username** | `homeassistant` | InfluxDB username |
| **Password** | `••••••••` | InfluxDB password |

The integration verifies the InfluxDB connection, loads existing monthly data, and starts tracking immediately. If InfluxDB is not yet ready, HA retries automatically.

### Reconfigure

To update InfluxDB credentials without re-installing:
**Settings → Devices & Services → PC User Statistics → ⋮ → Reconfigure**

### Sensor & User Configuration (Panel UI)

After setup, open the **🔧 Konfiguration** tab in the sidebar panel to:

- Edit all 4 sensor entity IDs without touching any files
- Add, edit, or remove user mappings (Windows username → user ID)
- Map HA mobile users for push notifications
- Reorder sidebar tabs via drag-and-drop

Changes save instantly and trigger an automatic integration reload.

---

## 🖥️ Sidebar Panel

The integration adds **🎮 PC Statistik** to your HA sidebar with 6 tabs:

### 📊 Statistik
- Live session cards (time, energy, cost)
- Donut chart — monthly usage per user
- Monthly total cards per user
- 🏆 Leaderboard with gold/silver/bronze ranking

### 👤 Brugere
- Active user with pulsing LIVE badge
- Overview of all configured users and sensor mappings

### 🔔 Notifikationer
- Configure receiver devices (HA Companion app)
- 4 ready-to-use premade rules:
  - ⏱️ **Pausepåmindelse** — repeats every 60 min
  - 🌙 **Lang session** — fires once after 3 hours
  - 💰 **Prisgrænse** — fires once at 10 DKK
  - 🌅 **PC glemt tændt** — repeats every 30 min when idle
- Create your own rules with custom trigger, message, and repeat interval
- Template variables: `{user}`, `{time}`, `{cost}`
- Test button sends an instant push notification

### 📈 Historik
- SVG bar chart — daily totals for the last 30 days
- Switch between Time / Energy / Cost
- 7-day table with per-user mini bars

### 🔧 Konfiguration
- Edit sensor entity IDs
- Manage user mappings and HA mobile user links
- Reorder tabs via drag-and-drop

### ⚙️ Admin
- System info and version
- InfluxDB write buffer status
- User mapping overview

---

## 🔌 Device Structure

### Statistics Hub *(diagnostic sensors)*
- `sensor.statistics_hub_current_user`
- `sensor.statistics_hub_current_session_time`
- `sensor.statistics_hub_current_session_energy`
- `sensor.statistics_hub_current_session_cost`

### Per-User Devices (e.g. Statistics Flemming)
- `sensor.statistics_flemming_monthly_time`
- `sensor.statistics_flemming_monthly_energy`
- `sensor.statistics_flemming_monthly_cost`

*Same pattern for each configured user.*

---

## 📈 InfluxDB Data Structure

**Measurement**: `pc_usage` | **Write frequency**: Every 60 seconds (active session)

| Field | Type | Description |
|-------|------|-------------|
| `power` | float | Current power in watts |
| `time_delta` | float | Seconds since last write |
| `energy_delta` | float | kWh since last write |
| `cost_delta` | float | DKK since last write |

**Tags**: `user` (string)

```sql
-- Total time per user this month
SELECT SUM("time_delta") AS "total_time"
FROM "pc_usage"
WHERE time >= now() - 30d
GROUP BY "user"
```

---

## 🛠️ Troubleshooting

### Sensors show "Unavailable"
Monthly user sensors show unavailable until the initial InfluxDB load completes (usually a few seconds after startup). If they remain unavailable, check that InfluxDB is running and verify entity IDs in the **🔧 Konfiguration** tab.

### "Cannot connect" during setup
Verify InfluxDB is running and the host/port are correct. If using the InfluxDB add-on, the default host is `a0d7b954-influxdb`. If InfluxDB starts after HA, the integration will retry automatically — no action needed.

### Authentication error (re-auth prompt appears)
InfluxDB returned a 401. Use **Settings → Devices & Services → PC User Statistics → ⋮ → Reconfigure** to update your credentials.

### Monthly data shows 0 after restart
The integration loads monthly totals from InfluxDB in the background at startup. If InfluxDB is slow to start, it retries up to 3 times (30s → 60s → 120s). Check HA logs filtered by `pc_user_statistics` for details.

### No push notifications received
1. Install the Home Assistant Companion app on your phone
2. Open **🔔 Notifikationer** → select your device under "Modtagerenheder"
3. Enable at least one rule and press **📨 Test** to verify

### Panel not appearing in sidebar
Do a full HA restart (not just reload). After updating the JS file, the browser requires a hard refresh (`Ctrl+Shift+R`) — or a full HA restart to force a new cache-bust URL.

### Time tracking seems wrong
Verify that your HASS.Agent sensor is reporting the correct Windows username, and that the mapping in **🔧 Konfiguration** matches exactly (case-insensitive). Check HA logs for "User changed" messages.

### Download diagnostics
**Settings → Devices & Services → PC User Statistics → ⋮ → Download diagnostics**
Provides a JSON file with coordinator state, session data, buffer status, and notification rules — useful for bug reports.

---

## 🔄 Migration from 1.x

1. Backup any automations or dashboards using old entity IDs
2. Delete old integration: **Settings → Devices & Services → Spille PC Statistik → Delete**
3. Install new integration and configure with your InfluxDB details
4. Update entity ID references (see [CHANGELOG.md](CHANGELOG.md))

Your historical data in InfluxDB is **not** affected.

---

## 📝 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/kingpainter/pc_user_statistics/issues)
- **Discussions**: [GitHub Discussions](https://github.com/kingpainter/pc_user_statistics/discussions)

---

**Made with ❤️ for the Home Assistant community**
