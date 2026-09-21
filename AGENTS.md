# Repository guide

## Map

- `custom_components/netbird/`: integration package and Home Assistant metadata.
- `tests/`: runtime and repository-contract tests.
- `tests/fixtures/`: anonymized API-shaped data only.
- `pyproject.toml` and `uv.lock`: Python compatibility and locked tooling.
- `.github/workflows/ci.yml`: Linux quality gate equivalent to local checks.

## Conventions

Use async Home Assistant APIs, ConfigEntry `runtime_data`, typed boundaries,
entity descriptions, translations, and a DataUpdateCoordinator when polling is
implemented. Keep changes scoped to the active issue. Do not add empty platforms,
services, speculative API fields, TODOs, or placeholder implementations.

## Validation

Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, and
`uv run pytest -q --cov=custom_components.netbird --cov-report=term-missing`.
Runtime tests require Linux or WSL.

## Compatibility and safety

Support Home Assistant 2026.9.3 or newer and Python 3.14.2 or newer until the
documented support matrix changes. Never store or log tokens, passwords,
cookies, private URLs, raw diagnostics, or production responses. Use anonymized
fixtures and opt-in environment-based credentials for future live tests.
