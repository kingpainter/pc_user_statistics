# Planned Features

This document outlines the roadmap for future development of the PC User Statistics integration.

---

## ✅ Completed (v2.3.0)

These features were planned and have been fully implemented:

| Feature | Version | Status |
|---------|---------|--------|
| UI-based user configuration | v2.3.0 | ✅ Done — Konfiguration-tab i panel |
| Notification system | v2.3.0 | ✅ Done — 4 premade + egne regler |
| Historical data graphs | v2.3.0 | ✅ Done — 30-dages SVG søjlediagram |
| Custom sidebar panel | v2.3.0 | ✅ Done — Vanilla JS, 6 tabs |
| Leaderboard | v2.3.0 | ✅ Done — Månedlig ranking med medaljer |
| Dark/light theme | v2.3.0 | ✅ Done — Følger HA automatisk |
| Live watt-gauge | v2.3.0 | ✅ Done — HalvCircel gauge i header |
| Tab reordering | v2.3.0 | ✅ Done — Drag-and-drop i Konfiguration |

---

## 🎯 Short-term Goals (v2.4.0)

### Data Export
**Status**: Planned  
**Priority**: Medium  
**Effort**: Medium

Export historisk data direkte fra panelet.

**Features**:
- Download CSV for valgt datointerval
- Per-bruger eller samlet eksport
- Knap i Historik-tab

---

### Lovelace Dashboard Auto-Generation
**Status**: Planned  
**Priority**: Low  
**Effort**: Medium

Generer et færdigt Lovelace dashboard automatisk.

**Features**:
- Generér YAML med alle sensorer
- Copy-to-clipboard knap i Admin-tab
- Understøtter ApexCharts-card og standard HA-cards

---

### Forbedret Historik
**Status**: Planned  
**Priority**: Medium  
**Effort**: Medium

**Features**:
- Valgfrit datointerval (ikke kun 30 dage)
- Uge/måned/år-visning
- Heatmap — tid fordelt på ugedag og time
- Trend-linje

---

## 🚀 Mid-term Goals (v2.5.0)

### Multi-PC Support
**Status**: Planned  
**Priority**: Low  
**Effort**: High

Spor flere PC'er i samme HA-installation.

**Features**:
- Separate config entries per PC
- Samlet husstand-statistik
- PC-sammenligning i panel

---

### Ugentlig/månedlig rapport-notifikation
**Status**: Planned  
**Priority**: Low  
**Effort**: Low

Automatisk opsummering sendt som push.

**Features**:
- Mandag morgen: ugeoversigt
- 1. i måneden: månedsoversigt
- Valgfrit pr. bruger

---

## 🌟 Long-term Goals (v3.0.0+)

### Gold Quality Scale Compliance
**Status**: Aktiv planlægning  
**Priority**: Medium  
**Effort**: High

**Mangler**:
- Integration tests (`tests/test_integration.py`)
- Test coverage ≥ 95%
- GitHub Actions CI/CD workflow
- Ruff + mypy i CI
- CONTRIBUTING.md
- Code review af HA team

---

### HACS-submission
**Status**: Planned  
**Priority**: Medium  
**Effort**: Low

**Kræver**:
- `hacs.json` fil
- Brand assets (logo)
- Offentligt GitHub repository
- Mindst Bronze quality scale

---

### Machine Learning Insights
**Status**: Concept  
**Priority**: Low  
**Effort**: Very High

Lokal ML til at opdage mønstre og anomalier i spillemønstre. Privacy-first, lokal behandling, opt-in.

---

## 🔧 Løbende tekniske forbedringer

- Øg test coverage til 95%+
- Tilføj GitHub Actions CI/CD
- Ruff + mypy linting
- CONTRIBUTING.md

---

## ❌ Ikke planlagt

| Feature | Årsag |
|---------|-------|
| Remote PC Control | Out of scope — brug Wake-on-LAN i stedet |
| Game Launcher Integration | For platform-specifik og skrøbelig |
| Automatic PC Shutdown | Sikkerhedsrisiko |
| Cloud Backup | Ikke relevant for dette use case |

---

## 📅 Release Timeline (tentativ)

| Version | Dato | Fokus |
|---------|------|-------|
| v2.0.0 | 2026-01-11 ✅ | Major restructure, Silver compliance |
| v2.3.0 | 2026-03-01 ✅ | Custom panel, notifikationer, historik, konfiguration |
| v2.4.0 | 2026-04-30 | Data export, forbedret historik |
| v2.5.0 | 2026-06-30 | Multi-PC, rapport-notifikationer |
| v3.0.0 | 2026-Q4 | Gold compliance, HACS, CI/CD |

---

**Last Updated**: March 1, 2026  
**Document Version**: 2.3.0
