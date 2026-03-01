# Dependencies & Requirements

This document describes everything needed to run the PC User Statistics integration.

---

## 🏠 Home Assistant

- **Version**: 2024.1 or newer
- **Type**: Any installation method (HAOS, Container, Core)

---

## 🗄️ InfluxDB

- **Version**: 1.x (not InfluxDB 2.x — different API)
- **Purpose**: Long-term storage of power, time, and cost data
- **Recommended**: Run as a Home Assistant add-on

### Installation (HAOS)
1. Go to **Settings → Add-ons → Add-on Store**
2. Search for **InfluxDB** and install
3. Start the add-on and open the Web UI
4. Create a database named `homeassistant` (or your preferred name)
5. Create a user with read/write access to that database

---

## 🔌 Smart Power Plug

Used to measure the PC's power consumption in real time.

### Requirements
- Must report **current power consumption in watts** (W) as a HA sensor
- Must report **device self-consumption** (the plug's own power draw) as a separate sensor
  — this is subtracted from the total to get the PC's net consumption

### Tested with
- **Shelly Plug S** / **Shelly Plug Plus** — exposes both sensors automatically
- Any Z-Wave or Zigbee smart plug with power monitoring should work

### Required sensor entities
| Sensor | Example entity ID | Unit |
|--------|-------------------|------|
| PC power consumption | `sensor.gamer_pc_power_monitor_current_consumption` | W |
| Plug self-consumption | `sensor.gamer_pc_power_monitor_device_power` | W |

> **Note**: The plug's self-consumption (typically 1–3W) is automatically subtracted
> from the total reading. When the PC is off, the net value is clamped to 0W.

---

## 🖥️ HASS.Agent (Windows)

Used to detect which Windows user is currently logged in and report it to Home Assistant.

- **Platform**: Windows only
- **Purpose**: Provides a sensor whose state is the currently logged-in username
- **Download**: [github.com/LAB02-Research/HASS.Agent](https://github.com/LAB02-Research/HASS.Agent)

### Setup in HASS.Agent
1. Install and configure HASS.Agent on the gaming PC
2. Add a new **Sensor** of type **Logged In Users** (or **Windows User**)
3. The sensor state should return the Windows username (e.g. `Konge`, `Lukas`, `Sebas`)
4. Note the entity ID that appears in Home Assistant (e.g. `sensor.flemming_gamer_satellite_loggeduser`)

### User mapping
The sensor state (Windows username) is mapped to a user ID in the integration:

| Windows username (sensor state) | User ID in integration |
|----------------------------------|------------------------|
| `konge` | `flemming` |
| `lukas` | `lukas` |
| `sebas` | `sebastian` |

> Mappings are case-insensitive and can be edited in the **🔧 Konfiguration** panel tab
> without restarting Home Assistant.

---

## 💰 Electricity Price Sensor

Used to calculate session and monthly electricity costs in DKK.

### Requirements
- Must return current price in **DKK per kWh** as a float
- Should update at least every hour for accurate cost tracking

### Recommended
- **Energi Data Service** integration (Danish electricity prices)
  - Install via HACS or the HA integration store
  - Automatically provides real-time spot prices including tariffs
  - Entity example: `sensor.energi_data_service`

### Alternative
Any sensor that returns a float value in DKK/kWh will work.

---

## 📱 Home Assistant Companion App (optional)

Required only if you want to receive **push notifications**.

- Install the **Home Assistant** app on your phone (iOS or Android)
- Log in with your HA account
- The app will automatically appear as a `notify.mobile_app_*` service in HA
- Select it in the **🔔 Notifikationer** tab under "Modtagerenheder"

---

## 📋 Summary

| Component | Required | Purpose |
|-----------|----------|---------|
| Home Assistant 2024.1+ | ✅ | Platform |
| InfluxDB 1.x | ✅ | Data storage |
| Smart plug with power monitoring | ✅ | Watt measurement |
| HASS.Agent (Windows) | ✅ | User detection |
| Energi Data Service | ✅ | Electricity price |
| HA Companion App | ⭕ Optional | Push notifications |

---

## 🗂️ Sensor Entity ID Overview

All sensor entity IDs can be configured in the **🔧 Konfiguration** panel tab after installation.
Default values (matching the original setup):

| Role | Default entity ID |
|------|-------------------|
| Logged-in user | `sensor.flemming_gamer_satellite_loggeduser` |
| PC power (W) | `sensor.gamer_pc_power_monitor_current_consumption` |
| Plug self-power (W) | `sensor.gamer_pc_power_monitor_device_power` |
| Electricity price (DKK/kWh) | `sensor.energi_data_service` |

---

**Last Updated**: March 1, 2026  
**Document Version**: 2.3.0
