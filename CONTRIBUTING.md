# Contributing to PC User Statistics

Thank you for your interest in contributing! This document explains how to set up a development environment, run tests, and submit changes.

---

## 🛠️ Development Setup

### Prerequisites

- Python 3.11+
- Home Assistant development environment
- InfluxDB v1.x (for integration tests)
- Git

### Install dependencies

```bash
pip install -r requirements_dev.txt
```

`requirements_dev.txt` should include:

```
homeassistant
pytest
pytest-asyncio
pytest-homeassistant-custom-component
pytest-cov
ruff
mypy
aiohttp
```

---

## 🧪 Running Tests

```bash
# All tests with coverage
pytest tests/ --cov=custom_components/pc_user_statistics --cov-report=term-missing

# Single file
pytest tests/test_helpers.py -v

# Only unit tests (no InfluxDB required)
pytest tests/ -m "not integration" -v
```

Target coverage: **≥95%** (Gold quality scale requirement).

---

## 🔍 Linting & Type Checking

```bash
# Ruff linting
ruff check custom_components/pc_user_statistics/

# Mypy strict type checking
mypy custom_components/pc_user_statistics/ --strict
```

All PRs must pass both checks with zero errors.

---

## 📁 File Structure

```
custom_components/pc_user_statistics/
├── __init__.py           # Coordinator, setup, unload
├── config_flow.py        # UI configuration flow
├── const.py              # Constants
├── diagnostics.py        # HA diagnostics support
├── helpers.py            # Shared helpers
├── manifest.json         # Integration metadata
├── notification_manager.py
├── panel.py              # Sidebar panel registration
├── quality_scale.yaml    # Gold compliance tracking
├── sensor.py             # HA sensor entities
├── store.py              # Persistent storage
├── strings.json          # English translations
├── websocket.py          # WebSocket API (11 commands)
├── translations/
│   └── da.json           # Danish translations
└── frontend/
    ├── pc-user-statistics-panel.js
    └── pc-user-statistics-cards.js
```

---

## 🔄 Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your changes and add tests
4. Run linting and tests — all must pass
5. Commit with a descriptive message following the format below
6. Open a Pull Request against `main`

### Commit message format

```
type: short description

- Detail 1
- Detail 2

Files changed:
M  path/to/file.py
A  path/to/new_file.py
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

---

## 📋 Version Bumping

When making changes, always update **all three** version locations:

| File | Field |
|------|-------|
| `manifest.json` | `"version"` |
| `const.py` | `__version__` |
| `CHANGELOG.md` | New section at top |

---

## 🏠 Home Assistant Guidelines

This integration targets the **Gold quality scale**. All contributions must:

- Use `async`/`await` for all I/O
- Include full type hints
- Handle `unavailable` and `unknown` entity states explicitly
- Follow [HA entity guidelines](https://developers.home-assistant.io/docs/core/entity/)
- Not introduce new blocking calls in the event loop

---

## 📞 Questions?

Open an issue on [GitHub](https://github.com/kingpainter/pc_user_statistics/issues) or start a discussion.
