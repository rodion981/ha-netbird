# Cloud integration quality evidence

This is the project's evidence checklist for the Cloud-only `0.2.0` implementation. It is **not** a Home Assistant Core quality-tier award. Recheck the [current Home Assistant rules](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/) before claiming a tier. Evidence below points to repository code, tests, and named hosted runs, not to a production installation.

## Reproducible gate

On Linux or WSL with Python 3.14.2 or newer:

```shell
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python -m pytest -q --cov=custom_components.netbird --cov-report=term-missing --cov-fail-under=95
```

On native Windows, run the first three `uv run` checks. Home Assistant runtime tests need Linux/WSL because its import path requires POSIX `fcntl`. CI also runs hassfest, HACS validation, and Gitleaks. A local pass does not establish those hosted results or a live API pass. Use opt-in, environment-provided disposable credentials for any later live check; never commit the response, diagnostics, token, identifiers, names, addresses, or private URLs.

Evidence classes remain separate:

- Local static evidence: Ruff and mypy run in the developer environment.
- Local runtime evidence: pytest runs in Linux/WSL against anonymized fixtures and mocked responses.
- Hosted evidence: the public [v0.2.0 tag workflow](https://github.com/rodion981/ha-netbird/actions/runs/35766903549) passed quality, hassfest, and HACS jobs on the release commit; the workflow also runs Gitleaks.
- Release evidence: [v0.2.0](https://github.com/rodion981/ha-netbird/releases/tag/v0.2.0) is published, and the repository includes the official NetBird brand asset plus a direct HACS custom-repository button.
- Live API evidence: no manual live API contract validation of the complete v0.2.0 account, peer, network, resource, router, and peer-group shape is claimed by this checklist.
- Frontend and installation evidence must be recorded separately from automated test results when performed.

## Implemented rule evidence

| Rule or behavior | Evidence |
| --- | --- |
| UI config flow, test before configure, unique config entry, and reconfiguration | [config_flow.py](../custom_components/netbird/config_flow.py), [test_config_flow.py](../tests/test_config_flow.py) |
| Test before setup and typed runtime data | [__init__.py](../custom_components/netbird/__init__.py), [test_coordinator.py](../tests/test_coordinator.py) |
| Appropriate shared polling and refresh failures | [const.py](../custom_components/netbird/const.py), [coordinator.py](../custom_components/netbird/coordinator.py), [test_coordinator.py](../tests/test_coordinator.py) |
| Separate five-minute topology polling, `1 + 2N` request budgeting, concurrency 6, and partial-section isolation | [topology.py](../custom_components/netbird/topology.py), [test_topology.py](../tests/test_topology.py) |
| Stable entity IDs, names, classes, categories, and disabled diagnostic entities | [entity.py](../custom_components/netbird/entity.py), [sensor.py](../custom_components/netbird/sensor.py), [binary_sensor.py](../custom_components/netbird/binary_sensor.py), [test_entities.py](../tests/test_entities.py) |
| Dynamic devices, unload listener cleanup, stale removal, and blocked-cleanup Repair | [lifecycle.py](../custom_components/netbird/lifecycle.py), [test_entities.py](../tests/test_entities.py) |
| Network and resource devices, summaries, dynamic discovery, and conservative topology cleanup | [topology_entity.py](../custom_components/netbird/topology_entity.py), [topology_lifecycle.py](../custom_components/netbird/topology_lifecycle.py), [test_topology_entities.py](../tests/test_topology_entities.py) |
| Translated config, entities, errors, and Repair guidance | [strings.json](../custom_components/netbird/strings.json), [uk.json](../custom_components/netbird/translations/uk.json), [test_repository_quality.py](../tests/test_repository_quality.py) |
| Allowlisted diagnostics | [diagnostics.py](../custom_components/netbird/diagnostics.py), [test_diagnostics.py](../tests/test_diagnostics.py) |
| Documentation for setup, removal, updates, entities, uses, and limitations | [English README](../README.md), [Ukrainian README](../README.uk.md) |
| Runtime end-to-end behavior within Home Assistant tests | [test_mvp_integration.py](../tests/test_mvp_integration.py) |
| Async API with injected Home Assistant web session | [api.py](../custom_components/netbird/api.py), [__init__.py](../custom_components/netbird/__init__.py), [test_api.py](../tests/test_api.py) |
| Native dynamic dashboard without third-party cards or generated entity IDs | [dashboard example](../examples/netbird-dashboard.yaml), [test_dashboard_example.py](../tests/test_dashboard_example.py) |

Rules about actions, triggers, conditions, local discovery, or push subscriptions are not applicable to this Cloud polling implementation: it exposes none of those features. Branding, HACS custom-repository metadata, hassfest, HACS validation, Gitleaks, and the public v0.2.0 release are complete. The integration is not claimed to be listed in the HACS default store. No `quality_scale.yaml` or official tier is claimed for this custom integration. Coverage percentage must come from the command above, not from this checklist.

## Cloud API assumptions and limits

- Fixed origin: `https://api.netbird.io`. The integration uses `GET /api/accounts`, `GET /api/peers`, `GET /api/networks`, `GET /api/networks/{id}/resources`, and `GET /api/networks/{id}/routers`. [NetBird API reference](https://docs.netbird.io/api), [client](../custom_components/netbird/api.py).
- The account list has exactly one item for a usable PAT. Peer IDs are required and unique. Optional peer fields may be absent or null. These are **integration parsing requirements**, not guarantees for every NetBird deployment.
- Invalid optional timestamps become unknown. Malformed required data fails the complete refresh. [Parser](../custom_components/netbird/api.py), [API tests](../tests/test_api.py).
- The peer coordinator polls every 60 seconds. The separate topology coordinator polls every 300 seconds. After the network list, Resources and Routers use a shared concurrency limit of six; one complete refresh costs `1 + 2N` requests for `N` networks. A failed nested section affects only that network section, and a failed topology refresh does not affect peer states.
- The Connected routing peers sensor currently resolves only routers with a concrete peer ID. Group-based routers are stored but not resolved to concrete peers, so the value can be zero while a group-based route exists. This is an explicit v0.2.0 limitation, not a reachability claim.
- NetBird's documented peer `connected` value represents Management Service state. End-to-end VPN access must be checked separately. The integration does not claim pagination, push delivery, rate-limit policy, or undocumented fields.
- NetBird [describes its API error handling as beta](https://docs.netbird.io/api/guides/errors). An HTTP 404 alone does not establish PAT expiry. Cloud API surfaces may evolve. Anonymized fixtures and mocked responses verify code behavior; a manual live API contract run for the complete v0.2.0 endpoint set has not been established by this checklist. Record future live findings separately with date, API documentation version or URL, anonymized shape, tested scope, and outcome. Never record raw production responses or identifiers.
- Deprecated legacy Routes, self-hosted endpoints, MSP/multi-tenant setup, write operations, traffic telemetry, group-based router resolution, and end-to-end VPN path tests are outside v0.2.0.
