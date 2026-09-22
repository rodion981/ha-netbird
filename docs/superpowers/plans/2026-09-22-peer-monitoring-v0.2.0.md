# NetBird Peer Monitoring v0.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the useful peer fields already returned by `/api/peers`, migrate existing installations safely, and retain one peer request per refresh.

**Architecture:** Extend the existing sensor and binary-sensor platforms with typed descriptions and field selectors. Keep the peer coordinator and stable peer device identity unchanged. Add a version-2 config-entry migration that only enables entities previously disabled by the integration.

**Tech Stack:** Python 3.14.2, Home Assistant 2026.9.3, pytest-homeassistant-custom-component, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-22-netbird-v0.2.0-monitoring-design.md`

## Global Constraints

- Cloud endpoint remains fixed at `https://api.netbird.io`.
- All API access remains read-only and uses the injected Home Assistant session.
- Keep one `GET /api/peers` call per 60-second peer refresh.
- Keep unique IDs in the form `<account_id>:<peer_id>:<key>`.
- Do not expose user ID, serial number, public connection IP, location, or raw payloads.
- Missing optional fields become unknown or unavailable, never false values.
- Preserve Home Assistant 2026.9.3 and Python 3.14.2 minimums.

## Review Focus

- A peer with `connected=false` remains available and reports disconnected.
- A missing optional boolean reports unavailable instead of `off`.
- Naive or invalid timestamps never reach Home Assistant as valid states.
- Migration never enables an entity disabled by the user.
- Adding nine peer entities does not add per-peer API requests.

---

### Task 1: Pin the useful peer entity contract

**Files:**
- Modify: `tests/test_entities.py`
- Modify: `tests/test_mvp_integration.py`

**Interfaces:**
- Consumes: `NetBirdPeer` fields already normalized by `api._parse_peer`.
- Produces: expected registry keys and states for the sensor and binary-sensor implementations.

- [ ] **Step 1: Expand the rich peer fixture used by entity tests**

```python
PEER = NetBirdPeer(
    id="peer-1",
    name="Test peer",
    version="0.0-test",
    ip="100.64.0.10",
    ipv6="fd00::10",
    hostname="test-peer",
    dns_label="test-peer.netbird.cloud",
    os="Linux",
    connected=False,
    last_seen=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
    last_login=datetime(2026, 1, 1, 2, 3, tzinfo=UTC),
    accessible_peers_count=4,
    ssh_enabled=True,
    ephemeral=False,
    login_expired=True,
    approval_required=False,
)
```

- [ ] **Step 2: Add failing assertions for enabled states and semantic keys**

```python
expected = {
    "last_seen": "2026-01-02T03:04:00+00:00",
    "ip_address": "100.64.0.10",
    "accessible_peers": "4",
    "last_login": "2026-01-01T02:03:00+00:00",
    "ssh_enabled": "on",
    "ephemeral": "off",
}
for key, value in expected.items():
    entity = _entity(hass, PEER.id, key)
    assert entity is not None
    assert _state(hass, entity.entity_id).state == value
    assert _state(hass, entity.entity_id).attributes["netbird_key"] == key
```

- [ ] **Step 3: Add missing-field coverage**

Assert sensors are `unknown`, optional booleans are `unavailable`, and `approval_required` is not registered when absent.

- [ ] **Step 4: Run focused tests and confirm failure**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_entities.py tests/test_mvp_integration.py'`

Expected: failures for missing `ip_address`, `accessible_peers`, `last_login`, `ssh_enabled`, `ephemeral`, and `netbird_key`.

### Task 2: Implement peer sensors and binary sensors

**Files:**
- Modify: `custom_components/netbird/entity.py`
- Modify: `custom_components/netbird/sensor.py`
- Modify: `custom_components/netbird/binary_sensor.py`

**Interfaces:**
- Consumes: `NetBirdPeer`, `NetBirdConfigEntry`, and the existing peer coordinator.
- Produces: `NetBirdPeerSensor` and expanded `NetBirdPeerBinarySensor` entities.

- [ ] **Step 1: Add the stable dashboard key to the base entity**

```python
self._attr_extra_state_attributes = {"netbird_key": key}
```

- [ ] **Step 2: Replace the one-off last-seen implementation with descriptions and selectors**

Define sensor descriptions for `last_seen`, `ip_address`, `accessible_peers`, `last_login`, `ipv6_address`, `hostname`, `dns_label`, and `operating_system`. Use `SensorDeviceClass.TIMESTAMP` for timestamps and `EntityCategory.DIAGNOSTIC` for every entity except `last_seen`. Disable only IPv6, hostname, DNS label, and operating system by default.

```python
SENSOR_VALUE_GETTERS: dict[str, Callable[[NetBirdPeer], StateType | datetime]] = {
    "last_seen": lambda peer: peer.last_seen,
    "ip_address": lambda peer: peer.ip,
    "accessible_peers": lambda peer: peer.accessible_peers_count,
    "last_login": lambda peer: peer.last_login,
    "ipv6_address": lambda peer: peer.ipv6,
    "hostname": lambda peer: peer.hostname,
    "dns_label": lambda peer: peer.dns_label,
    "operating_system": lambda peer: peer.os,
}
```

- [ ] **Step 3: Create applicable sensor entities dynamically**

Track `(peer_id, description.key)` instead of only peer IDs. Skip fields that have never been supplied when their entity is optional. Preserve existing `last_seen` unique IDs.

- [ ] **Step 4: Add SSH and ephemeral binary descriptions**

```python
(
    BinarySensorEntityDescription(
        key="ssh_enabled",
        translation_key="ssh_enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)
(
    BinarySensorEntityDescription(
        key="ephemeral",
        translation_key="ephemeral",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)
```

Set `login_expired` and `approval_required` to diagnostic category. Keep `connected` primary.

- [ ] **Step 5: Use an explicit boolean selector map**

```python
BINARY_VALUE_GETTERS: dict[str, Callable[[NetBirdPeer], bool | None]] = {
    "connected": lambda peer: peer.connected,
    "login_expired": lambda peer: peer.login_expired,
    "approval_required": lambda peer: peer.approval_required,
    "ssh_enabled": lambda peer: peer.ssh_enabled,
    "ephemeral": lambda peer: peer.ephemeral,
}
```

- [ ] **Step 6: Run focused tests**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_entities.py tests/test_mvp_integration.py'`

Expected: PASS and the mocked client still receives one peer request per refresh.

- [ ] **Step 7: Commit the peer entity slice**

```bash
git add custom_components/netbird/entity.py custom_components/netbird/sensor.py custom_components/netbird/binary_sensor.py tests/test_entities.py tests/test_mvp_integration.py
git commit -m "feat(netbird): expose useful peer monitoring entities"
```

### Task 3: Add translations and registry migration

**Files:**
- Modify: `custom_components/netbird/config_flow.py`
- Modify: `custom_components/netbird/__init__.py`
- Modify: `custom_components/netbird/strings.json`
- Modify: `custom_components/netbird/translations/en.json`
- Modify: `custom_components/netbird/translations/uk.json`
- Modify: `tests/test_config_flow.py`
- Modify: `tests/test_entities.py`

**Interfaces:**
- Consumes: config-entry version 1 and stable entity unique IDs.
- Produces: config-entry version 2 and complete English/Ukrainian entity names.

- [ ] **Step 1: Add failing migration tests**

Create a version-1 entry and registry rows for `last_seen`: one with `disabled_by=RegistryEntryDisabler.INTEGRATION`, one with `disabled_by=RegistryEntryDisabler.USER`. Assert migration enables only the integration-disabled row and updates entry version to 2.

- [ ] **Step 2: Verify the migration test fails**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_config_flow.py -k migrate'`

Expected: FAIL because `VERSION` is 1 and `async_migrate_entry` is absent.

- [ ] **Step 3: Implement version-2 migration**

```python
async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version > 2:
        return False
    if entry.version == 1:
        registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if (
                entity.platform == DOMAIN
                and entity.unique_id.endswith(":last_seen")
                and entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
            ):
                registry.async_update_entity(entity.entity_id, disabled_by=None)
        hass.config_entries.async_update_entry(entry, version=2)
    return True
```

Set `NetBirdConfigFlow.VERSION = 2`.

- [ ] **Step 4: Add matching English and Ukrainian translations**

Add names for IP address, accessible peers, last login, IPv6 address, hostname, DNS label, operating system, SSH enabled, and ephemeral in all three JSON resources.

- [ ] **Step 5: Run migration and translation tests**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_config_flow.py tests/test_entities.py tests/test_repository_quality.py'`

Expected: PASS.

- [ ] **Step 6: Commit migration and translations**

```bash
git add custom_components/netbird/__init__.py custom_components/netbird/config_flow.py custom_components/netbird/strings.json custom_components/netbird/translations tests/test_config_flow.py tests/test_entities.py
git commit -m "feat(netbird): migrate peer diagnostics for v0.2.0"
```

### Task 4: Verify peer monitoring as an independent deliverable

**Files:**
- No product changes expected.

**Interfaces:**
- Consumes: Tasks 1 through 3.
- Produces: a green peer-monitoring gate before topology work starts.

- [ ] **Step 1: Run lint, formatting, types, and peer tests**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q tests/test_api.py tests/test_entities.py tests/test_config_flow.py tests/test_mvp_integration.py
```

- [ ] **Step 2: Inspect the diff for request fan-out and exposed private fields**

Run: `git diff HEAD~2 -- custom_components/netbird tests`

Expected: no new API calls and no state sourced from `user_id`, `serial_number`, `connection_ip`, `country_code`, or `city_name`.
