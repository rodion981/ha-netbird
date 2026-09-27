# NetBird integration quality evidence

<!-- netbird-doc-contract: {"release":"0.3.0","endpoints":["/api/accounts","/api/peers","/api/networks","/api/networks/{id}/resources","/api/networks/{id}/routers"],"group_router_resolution":"supported","evidence":["mocked-tests","hosted-ci","manual-live"],"distribution":["hacs-custom","manual"],"branding":"included"} -->

This is the project's evidence checklist for the released Cloud `0.3.0` baseline and the ROD-48 self-hosted implementation candidate. It is **not** a Home Assistant Core quality-tier award. The protected self-hosted lifecycle check passed, with the non-empty self-hosted peer case explicitly retained as a release-evidence limitation below. Recheck the [current Home Assistant rules](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/) before claiming a tier. Evidence below points to repository code, tests, and named hosted runs, not to a production installation.

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
- Hosted evidence: release publication requires the v0.3.0 tag workflow to pass quality, hassfest, HACS validation, and Gitleaks on the release commit.
- Release evidence: [v0.3.0](https://github.com/rodion981/ha-netbird/releases/tag/v0.3.0), its tag workflow, the official NetBird brand asset, and the direct HACS custom-repository button form the release evidence.
- Live API evidence: the protected [manual live API contract run](https://github.com/rodion981/ha-netbird/actions/runs/36159603786/job/108170984157) passed on 25 September 2026 for the account, peer, network, resource, router, and peer-group input shapes used by v0.3.0. This is point-in-time shape evidence only; it does not verify derived entities or reachability.
- Self-hosted live evidence: on 27 September 2026, a disposable NetBird `0.79.0` combined server behind an Nginx HTTPS reverse proxy passed private-CA setup, config-entry load, peer and topology polling, reload, same-account PAT reauth, same-account endpoint/dashboard reconfigure, untrusted-CA failure, and fail-closed HTTPS redirect handling. The account contained one Network, one Resource, and one group-based Router. The peer endpoint succeeded with an empty list; a non-empty peer on this self-hosted deployment was not separately exercised. Public DNS, Let's Encrypt, frontend rendering, installation through HACS, and end-to-end VPN reachability were not tested. The disposable PAT, CA, URL, identifiers, response bodies, containers, volume, and test harness were removed after the run.
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
| Network and resource devices, group-aware routing summaries, routing availability, dynamic discovery, and conservative topology cleanup | [routing.py](../custom_components/netbird/routing.py), [topology_entity.py](../custom_components/netbird/topology_entity.py), [topology_lifecycle.py](../custom_components/netbird/topology_lifecycle.py), [test_routing.py](../tests/test_routing.py), [test_topology_entities.py](../tests/test_topology_entities.py) |
| Translated config, entities, errors, and Repair guidance | [strings.json](../custom_components/netbird/strings.json), [uk.json](../custom_components/netbird/translations/uk.json), [test_repository_quality.py](../tests/test_repository_quality.py) |
| Allowlisted diagnostics | [diagnostics.py](../custom_components/netbird/diagnostics.py), [test_diagnostics.py](../tests/test_diagnostics.py) |
| Documentation for setup, removal, updates, entities, uses, and limitations | [English README](../README.md), [Ukrainian README](../README.uk.md) |
| Runtime end-to-end behavior within Home Assistant tests | [test_mvp_integration.py](../tests/test_mvp_integration.py) |
| Async API with injected Home Assistant web session | [api.py](../custom_components/netbird/api.py), [__init__.py](../custom_components/netbird/__init__.py), [test_api.py](../tests/test_api.py) |
| Explicit Cloud/self-hosted profiles, HTTPS-origin normalization, private CA verification, fail-closed redirects, and identity-preserving v2-to-v3 migration | [deployment.py](../custom_components/netbird/deployment.py), [config_flow.py](../custom_components/netbird/config_flow.py), [test_deployment.py](../tests/test_deployment.py), [test_config_flow.py](../tests/test_config_flow.py) |
| Native dynamic dashboard without third-party cards or generated entity IDs | [dashboard example](../examples/netbird-dashboard.yaml), [test_dashboard_example.py](../tests/test_dashboard_example.py) |

Rules about actions, triggers, conditions, local discovery, or push subscriptions are not applicable: the integration exposes none of those features. The manifest uses `local_polling` because one explicit deployment type directly polls a user-managed server; Cloud remains supported. Branding and HACS custom-repository metadata are included; hassfest, HACS validation, Gitleaks, and the quality gate must pass on the release commit before publication is complete. The integration is not claimed to be listed in the HACS default store. No `quality_scale.yaml` or official tier is claimed for this custom integration. Coverage percentage must come from the command above, not from this checklist.

## API assumptions and limits

- Cloud uses the fixed `https://api.netbird.io` origin. Self-hosted setup accepts only a normalized HTTPS origin with no credentials, path, query, or fragment. It rejects loopback, unspecified, link-local, multicast, and hostnames resolving to those classes while allowing private LAN addresses. The integration uses `GET /api/accounts`, `GET /api/peers`, `GET /api/networks`, `GET /api/networks/{id}/resources`, and `GET /api/networks/{id}/routers`. [NetBird API reference](https://docs.netbird.io/api), [deployment policy](../custom_components/netbird/deployment.py), [client](../custom_components/netbird/api.py).
- API and dashboard origins are separate. The dashboard origin is optional and never receives the PAT. Every API request verifies TLS, refuses redirects, and uses either the normal trust store or an explicit PEM CA bundle. There is no disabled-verification path, HTTP fallback, mTLS, endpoint discovery, or subpath hosting.
- Self-hosted compatibility is capability-based. Initial setup and endpoint reconfigure require the complete consumed account, peer, network, resource, and router schemas. No undocumented minimum server version is claimed.
- The account list has exactly one item for a usable PAT. Peer IDs are required and unique. Optional peer fields may be absent or null. These are **integration parsing requirements**, not guarantees for every NetBird deployment.
- Invalid optional timestamps become unknown. Malformed required data fails the complete refresh. [Parser](../custom_components/netbird/api.py), [API tests](../tests/test_api.py).
- The peer coordinator polls every 60 seconds. The separate topology coordinator polls every 300 seconds. After the network list, Resources and Routers use a shared concurrency limit of six; one complete refresh costs `1 + 2N` requests for `N` networks. A failed nested section affects only that network section, and a failed topology refresh does not affect peer states.
- Connected routing peers resolves concrete and group-based routers from the bulk peer response and deduplicates peers. Missing router, group, peer, or connection data makes the result unavailable instead of presenting a partial count.
- Routing available is true when an enabled resource has at least one resolved connected routing peer. It is false for a disabled resource, no enabled routers, or a complete set of explicitly disconnected peers. Incomplete data is unavailable unless another complete path already proves true. This is not a reachability claim.
- NetBird's documented peer `connected` value represents Management Service state. End-to-end VPN access must be checked separately. The integration does not claim pagination, push delivery, rate-limit policy, or undocumented fields.
- NetBird [describes its API error handling as beta](https://docs.netbird.io/api/guides/errors). An HTTP 404 alone does not establish PAT expiry. Cloud API surfaces may evolve. Anonymized fixtures and mocked responses verify code behavior; the protected [manual live run](https://github.com/rodion981/ha-netbird/actions/runs/36159603786/job/108170984157) separately established point-in-time input-shape evidence for the v0.3.0 endpoint set. Record future live findings separately with date, API documentation version or URL, anonymized shape, tested scope, and outcome. Never record raw production responses or identifiers.
- Deprecated legacy Routes, MSP/multi-tenant setup, OAuth, write operations, traffic telemetry, and end-to-end VPN path tests remain outside scope.
