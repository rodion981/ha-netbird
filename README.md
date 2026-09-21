# NetBird for Home Assistant

NetBird is a planned Home Assistant custom integration for monitoring a NetBird
cloud VPN account through the official REST API.

## Project status

The repository contains the Home Assistant integration foundation and a typed,
async NetBird Cloud API client. Config flow, coordinated polling, entities, and
diagnostics are not implemented yet. There is no installable release yet.

## Project parameters

- Home Assistant domain: `netbird`
- Owner: [rodion981](https://github.com/rodion981)
- Planned repository: `https://github.com/rodion981/ha-netbird`
- Planned distribution: public HACS repository and manual installation
- License: MIT
- Minimum Home Assistant version: 2026.9.3
- Development target: Home Assistant 2026.9.3
- Minimum Python version: 3.14.2

The integration name follows NetBird's product spelling. The `netbird` domain
does not conflict with an integration bundled in the supported Home Assistant
baseline.

## Development

Install the locked environment with [uv](https://docs.astral.sh/uv/):

```shell
uv sync --frozen
```

Run the local quality gate:

```shell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q --cov=custom_components.netbird --cov-report=term-missing
```

Home Assistant runtime tests must run on Linux or WSL. Native Windows can run
the static checks, but Home Assistant imports the POSIX-only `fcntl` module.

Tests use anonymized JSON fixtures. Future live API tests must be opt-in, use a
dedicated NetBird service-user personal access token supplied through an
environment variable, and must never print or persist the token. No credentials,
private URLs, cookies, or diagnostics belong in the repository.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution and versioning rules.

## Installation

Installation is intentionally unavailable during Phase 0. HACS and manual
installation instructions will be added only after the MVP is functional and
validated.
