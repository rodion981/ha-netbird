# NetBird Topology Monitoring v0.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add isolated read-only monitoring for NetBird Networks, Resources, and Routers with bounded request fan-out and truthful partial availability.

**Architecture:** Add typed topology models and documented API methods, then poll them with a separate five-minute coordinator. Represent account and network summaries as sensors, and each resource as a child device with enabled/address/type entities. Cross-reference routing peer IDs with the existing peer coordinator without coupling their failure states.

**Tech Stack:** Python 3.14.2, asyncio, aiohttp, Home Assistant DataUpdateCoordinator, pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-netbird-v0.2.0-monitoring-design.md`

## Global Constraints

- Use only documented `GET /api/networks` and nested resources/routers endpoints.
- Do not call deprecated `/api/routes`.
- Poll topology every 300 seconds with concurrency limit 6.
- A topology failure must not make peer entities unavailable.
- Partial network failures remain scoped to the failed resource or router section.
- Keep diagnostics aggregate-only and redact names, IDs, addresses, and raw payloads.
- Preserve Home Assistant 2026.9.3 and Python 3.14.2 minimums.

## Review Focus

- Zero networks yields valid zero counts without nested requests.
- One failed nested request does not discard successful networks or sections.
- Cancellation is not swallowed by broad exception handling.
- Router group references never inflate concrete connected-peer counts.
- Removing a network or resource cannot delete a device with foreign associations.

---

### Task 1: Define and parse the topology API contract

**Files:**
- Create: `tests/fixtures/networks.json`
- Create: `tests/fixtures/network_resources.json`
- Create: `tests/fixtures/network_routers.json`
- Modify: `custom_components/netbird/models.py`
- Modify: `custom_components/netbird/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces: `NetBirdNetwork`, `NetBirdResource`, `NetBirdRouter`, `async_get_networks`, `async_get_network_resources`, and `async_get_network_routers`.

- [ ] **Step 1: Add anonymized fixtures matching documented responses**

```json
[{"id":"network-test-id","name":"Home LAN","description":"Test network"}]
```

```json
[{"id":"resource-test-id","type":"subnet","name":"Home subnet","description":"Test resource","address":"192.0.2.0/24","enabled":true,"groups":[]}]
```

```json
[{"id":"router-test-id","peer":"peer-test-id","peer_groups":[],"metric":100,"masquerade":true,"enabled":true}]
```

- [ ] **Step 2: Write failing parser and endpoint tests**

Assert exact paths, `Authorization: Token`, typed output, empty lists, missing optional description, required ID/name/address/type/enabled validation, and secret-safe errors.

- [ ] **Step 3: Run focused API tests and confirm failure**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_api.py -k "network or resource or router"'`

Expected: import or attribute failures for topology types and methods.

- [ ] **Step 4: Add frozen topology dataclasses**

```python
@dataclass(frozen=True, slots=True)
class NetBirdResource:
    id: str
    network_id: str
    name: str
    address: str
    type: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class NetBirdRouter:
    id: str
    network_id: str
    enabled: bool
    peer_id: str | None = None
    peer_group_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NetBirdNetwork:
    id: str
    name: str
    description: str | None = None
```

- [ ] **Step 5: Implement the three read-only client methods**

```python
async def async_get_network_resources(
    self, network_id: str
) -> tuple[NetBirdResource, ...]:
    payload = await self._async_get_json(f"/api/networks/{network_id}/resources")
    return _parse_resources(payload, network_id)
```

Use the same safe status/error mapping as peers. Validate path IDs before interpolation.

- [ ] **Step 6: Run all API tests**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_api.py'`

Expected: PASS.

- [ ] **Step 7: Commit the API slice**

```bash
git add custom_components/netbird/api.py custom_components/netbird/models.py tests/test_api.py tests/fixtures/networks.json tests/fixtures/network_resources.json tests/fixtures/network_routers.json
git commit -m "feat(netbird): add read-only topology API models"
```

### Task 2: Build the isolated topology coordinator

**Files:**
- Create: `custom_components/netbird/topology.py`
- Create: `tests/test_topology.py`
- Modify: `custom_components/netbird/const.py`
- Modify: `custom_components/netbird/__init__.py`

**Interfaces:**
- Consumes: topology API methods from Task 1.
- Produces: `NetBirdTopologyCoordinator` with `NetBirdTopologySnapshot` data.

- [ ] **Step 1: Write coordinator tests for request budget and partial failure**

For `N=3`, assert one network call, three resource calls, three router calls, and maximum observed nested concurrency no greater than 6. Add cases for empty networks, failed top-level list, one failed resource list, one failed router list, recovery, 401 reauth, and cancellation.

- [ ] **Step 2: Run tests and confirm failure**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_topology.py'`

Expected: module import failure.

- [ ] **Step 3: Define partial snapshot types**

```python
@dataclass(frozen=True, slots=True)
class NetBirdNetworkTopology:
    network: NetBirdNetwork
    resources: tuple[NetBirdResource, ...] | None
    routers: tuple[NetBirdRouter, ...] | None


@dataclass(frozen=True, slots=True)
class NetBirdTopologySnapshot:
    networks: tuple[NetBirdNetworkTopology, ...]
```

`None` means the nested request failed; an empty tuple means a successful empty list.

- [ ] **Step 4: Implement bounded nested fetches**

```python
semaphore = asyncio.Semaphore(TOPOLOGY_REQUEST_CONCURRENCY)


async def fetch_resources(
    network: NetBirdNetwork,
) -> tuple[NetBirdResource, ...] | None:
    async with semaphore:
        try:
            return await self._client.async_get_network_resources(network.id)
        except NetBirdAuthenticationError:
            raise
        except NetBirdUpdateError:
            return None
```

Use `asyncio.gather` for resource and router tasks and let `CancelledError` propagate.

- [ ] **Step 5: Wire runtime data and setup ordering**

Add `topology_coordinator` to `NetBirdRuntimeData`. First-refresh peer monitoring remains required. Topology first refresh may fail without blocking the config entry; schedule later retries and expose topology unavailable.

- [ ] **Step 6: Run topology and setup tests**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_topology.py tests/test_foundation.py tests/test_mvp_integration.py'`

Expected: PASS and peer request counts unchanged.

- [ ] **Step 7: Commit the coordinator slice**

```bash
git add custom_components/netbird/topology.py custom_components/netbird/const.py custom_components/netbird/__init__.py tests/test_topology.py tests/test_foundation.py tests/test_mvp_integration.py
git commit -m "feat(netbird): coordinate topology polling independently"
```

### Task 3: Expose account and network topology summaries

**Files:**
- Modify: `custom_components/netbird/sensor.py`
- Create: `custom_components/netbird/topology_entity.py`
- Create: `tests/test_topology_entities.py`

**Interfaces:**
- Consumes: `NetBirdTopologySnapshot` and the peer coordinator.
- Produces: account totals and one network device with five summary sensors.

- [ ] **Step 1: Write failing account/network entity tests**

Assert account totals, network resource/router counts, partial-section unavailability, zero lists, stable device IDs, reload deduplication, and connected-router counts based only on concrete peer IDs.

- [ ] **Step 2: Confirm failures**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_topology_entities.py -k "account or network"'`

- [ ] **Step 3: Implement topology entity bases**

```python
class NetBirdNetworkEntity(CoordinatorEntity[NetBirdTopologyCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, entry: NetBirdConfigEntry, network_id: str, key: str) -> None:
        super().__init__(entry.runtime_data.topology_coordinator)
        self._network_id = network_id
        self._attr_unique_id = (
            f"{entry.runtime_data.account_id}:network:{network_id}:{key}"
        )
        self._attr_extra_state_attributes = {"netbird_key": key}
```

- [ ] **Step 4: Add account topology descriptions**

Add `network_count`, `resource_count`, `enabled_resource_count`, `router_count`, and `enabled_router_count`. Return unavailable for aggregate resource/router totals if any contributing network section is `None`.

- [ ] **Step 5: Add network summary descriptions**

Add total/enabled resources, total/enabled routers, and connected routing peers. The connected sensor subscribes to both coordinators and is unavailable when router or peer data is unavailable.

- [ ] **Step 6: Run focused tests**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_topology_entities.py'`

- [ ] **Step 7: Commit summary entities**

```bash
git add custom_components/netbird/sensor.py custom_components/netbird/topology_entity.py tests/test_topology_entities.py
git commit -m "feat(netbird): expose topology summary sensors"
```

### Task 4: Expose dynamic resource devices and lifecycle

**Files:**
- Modify: `custom_components/netbird/sensor.py`
- Modify: `custom_components/netbird/binary_sensor.py`
- Create: `custom_components/netbird/topology_lifecycle.py`
- Modify: `custom_components/netbird/__init__.py`
- Modify: `tests/test_topology_entities.py`

**Interfaces:**
- Consumes: resource lists from the topology coordinator.
- Produces: stable resource devices, three resource entities, and conservative cleanup.

- [ ] **Step 1: Write failing dynamic resource tests**

Cover initial network/resource creation, later discovery, disappearance only after 10 successful relevant snapshots, no counter advance on a failed resource or router section, return resetting the counter, foreign entity association blocking network or resource deletion, and listener cleanup.

- [ ] **Step 2: Implement resource device identity and entities**

```python
resource_identifier = (
    DOMAIN,
    f"{account_id}:network:{network_id}:resource:{resource.id}",
)
```

Create `enabled`, `address`, and `resource_type` entities. Link the resource device to `(DOMAIN, f"{account_id}:network:{network_id}")` through `via_device`.

- [ ] **Step 3: Implement topology lifecycle ownership checks**

Reuse the peer lifecycle safety properties but keep network/resource known IDs and absence counters separate. Remove a network device only after its resource devices are gone and it has no foreign associations. Delete only integration-owned entities and devices with no foreign associations.

- [ ] **Step 4: Run resource lifecycle tests**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_topology_entities.py'`

- [ ] **Step 5: Commit dynamic resources**

```bash
git add custom_components/netbird/sensor.py custom_components/netbird/binary_sensor.py custom_components/netbird/topology_lifecycle.py custom_components/netbird/__init__.py tests/test_topology_entities.py
git commit -m "feat(netbird): manage network resource devices"
```

### Task 5: Translate and redact topology diagnostics

**Files:**
- Modify: `custom_components/netbird/strings.json`
- Modify: `custom_components/netbird/translations/en.json`
- Modify: `custom_components/netbird/translations/uk.json`
- Modify: `custom_components/netbird/diagnostics.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_repository_quality.py`

**Interfaces:**
- Consumes: topology coordinators and entities from Tasks 2 through 4.
- Produces: complete UI names and aggregate-only diagnostics.

- [ ] **Step 1: Add failing translation and diagnostic assertions**

Require all topology entity keys in English and Ukrainian. Assert diagnostics contain coordinator success/error class and aggregate counts but none of fixture IDs, names, or addresses.

- [ ] **Step 2: Implement aggregate diagnostics**

```python
"topology": {
    "last_update_success": topology.last_update_success,
    "error_class": type(topology.last_exception).__name__ if topology.last_exception else None,
    "networks": len(snapshot.networks) if snapshot else None,
    "complete_resource_sections": sum(item.resources is not None for item in snapshot.networks) if snapshot else None,
    "complete_router_sections": sum(item.routers is not None for item in snapshot.networks) if snapshot else None,
}
```

- [ ] **Step 3: Add translations and run tests**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_diagnostics.py tests/test_repository_quality.py tests/test_topology_entities.py'`

- [ ] **Step 4: Commit diagnostics and translations**

```bash
git add custom_components/netbird/strings.json custom_components/netbird/translations custom_components/netbird/diagnostics.py tests/test_diagnostics.py tests/test_repository_quality.py tests/test_topology_entities.py
git commit -m "feat(netbird): translate and diagnose topology monitoring"
```

### Task 6: Verify topology as an independent deliverable

**Files:**
- No product changes expected.

- [ ] **Step 1: Run focused and full static gates**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q tests/test_api.py tests/test_topology.py tests/test_topology_entities.py tests/test_diagnostics.py
```

- [ ] **Step 2: Check forbidden legacy endpoint and secrets**

Run: `rg -n '/api/routes|connection_ip|serial_number|user_id|country_code|city_name' custom_components/netbird`

Expected: no `/api/routes` call and no new state/diagnostic exposure of forbidden peer fields.
