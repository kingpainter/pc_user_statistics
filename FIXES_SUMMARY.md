# Fixes Summary

This document summarizes all major fixes and improvements across versions.

---

## v2.3.0 — March 1, 2026

### JS Syntax Fixes
- **Problem**: `SyntaxError: Unexpected token 'class'` — panel loadede ikke i HA
- **Årsag**: `module_url` i panel-registrering + Lit import fra unpkg
- **Fix**: Omskrevet til vanilla `HTMLElement` (ingen imports), registreret med `js_url`

- **Problem**: `SyntaxError: Invalid or unexpected token` — escaped backticks
- **Årsag**: Python string-erstatninger escapede `` ` `` til `` \` `` i template literals
- **Fix**: `_headerHTML` omskrevet til ren string-konkatenation

### Sensor-konfiguration
- **Problem**: HA advarsel — `MonthlyCostSensor` brugte `TOTAL_INCREASING` med `MONETARY` device class
- **Fix**: `monthly_cost` state class ændret til `TOTAL` (eneste gyldige for `MONETARY`)

### Manglende konstanter
- **Problem**: `ImportError: cannot import name 'CONF_USER_MAPPINGS'`
- **Fix**: Tilføjet `CONF_USER_MAPPINGS`, `CONF_TRACKED_USERS`, `DEFAULT_USER_MAP`, `DEFAULT_USERS` til `const.py`

---

## v2.0.0 — January 11, 2026

### Original Known Limitations → Fixed

| Limitation | Fix |
|-----------|-----|
| Hardcoded users | `CONF_USER_MAPPINGS` + `CONF_TRACKED_USERS` i config entry |
| Ingen unit tests | 25+ tests, >80% coverage |
| Ingen data buffering | 100-point FIFO write buffer |
| Ingen retry logic | Op til 3 retry-forsøg per buffered write |

### Kritiske bugs
- Session reset: `acc_time` nulstilles ikke fejlagtigt ved bruger → None
- InfluxDB parsing: robust håndtering af malformed responses
- Negative power values: clamp til 0
- Sensor states: korrekt håndtering af `unavailable` og `unknown`

---

## Metrics oversigt

| | v1.0.x | v2.0.0 | v2.3.0 |
|-|--------|--------|--------|
| **Lines of Code** | ~500 | ~1200 | ~3500+ |
| **Test Coverage** | 0% | ~82% | ~82% |
| **Type Hints** | ~40% | 100% | 100% |
| **Panel** | ❌ | ❌ | ✅ Komplet |
| **Notifikationer** | ❌ | ❌ | ✅ |
| **Historik** | ❌ | ❌ | ✅ |
| **Known Bugs** | 5+ | 0 | 0 |

---

**Last Updated**: March 1, 2026
