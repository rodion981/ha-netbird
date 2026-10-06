# Repository guide

## Architecture

Read-only Home Assistant custom integration for NetBird Cloud and explicit
self-hosted HTTPS servers. Package: `custom_components/netbird/`.

- `__init__.py`: setup/unload, typed `ConfigEntry.runtime_data`, v1/v2/v3 migration.
- `config_flow.py`: deployment selection, PAT validation, reauth and reconfigure;
  no options flow or YAML configuration.
- `deployment.py`: HTTPS origins, address checks and optional PEM CA trust.
- `transport.py`: connection-time DNS filtering; owned self-hosted sessions close
  after flow validation and on entry unload/failure. Cloud uses HA's shared session.
- `api.py` / `models.py`: shared async GET client and immutable typed snapshots.
- `coordinator.py`: bulk peers every 60 seconds; `topology.py`: Networks every
  300 seconds, then Resources/Routers (`1 + 2N` requests, concurrency limit 6).
- `routing.py`: concrete/group router resolution from bulk peer membership.
- `sensor.py`, `binary_sensor.py`, `entity.py`, `topology_entity.py`: dynamic
  entities, stable identity, device hierarchy and availability.
- `lifecycle.py`, `topology_lifecycle.py`: registry cleanup after 10 successful
  missing-object snapshots; preserve ambiguous/foreign ownership.
- `diagnostics.py`: cached aggregate allowlist; `dashboard_urls.py`: UI links.
- `manifest.json`, `hacs.json`, `strings.json`, `translations/{en,uk}.json`:
  metadata and UI text. `examples/`: native bilingual dashboards.
- `tests/`: mocked HA runtime and repository contracts; `tests/fixtures/`:
  anonymized shapes. `scripts/live_api_contract.py`: separate opt-in live probe.

## Existing conventions

Use annotated async APIs, injected aiohttp sessions, `@callback` for
non-awaiting HA callbacks, frozen/slotted dataclasses and tuples for snapshots,
entity descriptions, translation keys and `typing.override`. Ruff uses Python
3.14, 88 columns and sorted imports; mypy requires typed definitions.

Keep peers and topology independently available. Missing data must not become
false or zero; partial topology failures must not imply deletion. Lifecycle
listeners count successful unchanged snapshots even with `always_update=False`.
Own subscriptions through `entry.async_on_unload` / `entity.async_on_remove`.
Run blocking DNS/TLS work in HA's executor. Keep peer cleanup distinct from
network/resource cleanup. `connected` and `routing_available` do not prove VPN
reachability.

## Validation

Python >=3.14.2; HA >=2026.9.3 (development pin: 2026.9.3). Linux/WSL is required
for runtime tests (`fcntl`). Keep Windows and WSL virtual environments separate;
in WSL set `UV_PROJECT_ENVIRONMENT=.venv-wsl` and `UV_LINK_MODE=copy`.

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python -m pytest -q --cov=custom_components.netbird --cov-report=term-missing --cov-fail-under=95
```

Use `uv run ruff format <changed-python-files>` when formatting edits. Run
focused behavior tests after changes, then the relevant full gate. CI additionally
runs hassfest, HACS and Gitleaks; distinguish local, hosted and live evidence.
No pre-commit configuration or package build pipeline is defined.

## Change and compatibility rules

Inspect implementation, tests, Git status and relevant documentation before
editing. Read `CONTRIBUTING.md`, `docs/QUALITY_SCALE.md`, `SECURITY.md` and the
applicable design notes under `docs/superpowers/`; historical plans are context,
not authorization. Preserve pre-existing local work and report baseline failures.
Avoid unrelated refactoring, speculative fields, empty platforms and placeholders.

Preserve account-based entry IDs, entity/device identifiers, `netbird_key`, user
disabled states and Recorder continuity. Config-entry changes need migrations
and reload/reauth tests. Since 1.0.0, breaking changes require a major release.
Keep manifest/project/lock versions and bilingual documentation aligned.

Keep the API GET-only, HTTPS verification enabled, redirects disabled and the
10-second request timeout. Do not introduce legacy Routes, MSP, write actions
or new endpoint fan-out outside the authorized scope. Never commit/log tokens,
private URLs, certificates, raw diagnostics or production responses. ConfigEntry
credential storage is intentional; diagnostics expose only allowlisted aggregates.
Live checks require explicit approval and environment-provided disposable
credentials; never weaken coverage gates or mutate NetBird to make them pass.
Do not commit, push, publish or change external planning without authorization.
