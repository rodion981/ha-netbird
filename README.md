# NetBird for Home Assistant

NetBird is a Home Assistant custom integration for read-only monitoring of a
NetBird Cloud account through the official REST API.

## Project status

The MVP includes UI configuration, coordinated polling, peer devices, status
and metadata entities, reload/unload support, and redacted diagnostics. There is
no packaged release yet.

## Project parameters

- Home Assistant domain: `netbird`
- Owner: [rodion981](https://github.com/rodion981)
- Repository: `https://github.com/rodion981/ha-netbird`
- Current distribution: manual installation from the private repository
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
uv run python -m pytest -q --cov=custom_components.netbird --cov-report=term-missing
```

Home Assistant runtime tests must run on Linux or WSL. Native Windows can run
the static checks, but Home Assistant imports the POSIX-only `fcntl` module.

Tests use anonymized JSON fixtures. Live API tests must be opt-in, use a
dedicated disposable personal access token supplied through an environment
variable, and must never print or persist the token. No credentials, private
URLs, cookies, or diagnostics belong in the repository.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution and versioning rules.

## Installation

1. Copy `custom_components/netbird` into the Home Assistant configuration
   directory as `custom_components/netbird`.
2. Restart Home Assistant.
3. Open **Settings > Devices & services > Add integration**, select **NetBird**,
   and enter a NetBird personal access token.

To rotate a PAT, open the existing NetBird integration entry and choose
**Reconfigure**. Enter a new PAT for the same NetBird account. Home Assistant
validates it before replacing the stored token and reloading the entry. Verify
that the integration recovers before revoking the old PAT. If the old PAT was
already revoked, use the same manual action; NetBird may return an ambiguous
HTTP 404, so the integration does not automatically treat every 404 as an
authentication failure.

## Peer lifecycle

New peers appear after a successful poll without reloading the integration. A
peer missing from a successful snapshot remains unavailable while Home
Assistant retains its device and entities. Cleanup occurs only after 10
consecutive successful snapshots omit that peer. Failed or malformed refreshes
do not advance this threshold, and a returning peer resets it.

The absence counter is runtime-only. Reloading or restarting Home Assistant
resets it, which can only delay cleanup. Before deletion, the integration
checks that the peer device and every linked entity belong to the same NetBird
ConfigEntry. Unsafe registry associations block all deletion and create a
translated Home Assistant Repair with manual guidance.

HACS validation is intentionally skipped while this repository is private,
because HACS custom repositories must be public. Enable the HACS CI job only
after the repository is made public and the required brand assets are available.
