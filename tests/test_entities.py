"""Home Assistant runtime tests for MVP peer devices and entities."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.api import NetBirdSchemaError
from custom_components.netbird.binary_sensor import PARALLEL_UPDATES as BINARY_PARALLEL
from custom_components.netbird.const import CONF_ACCOUNT_ID, CONF_API_TOKEN, DOMAIN
from custom_components.netbird.models import NetBirdAccount, NetBirdPeer
from custom_components.netbird.sensor import PARALLEL_UPDATES as SENSOR_PARALLEL

ACCOUNT = "account-test-id"
TOKEN = "test-secret-token"
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
MINIMAL_PEER = NetBirdPeer(id="peer-2")
NEW_PEER = NetBirdPeer(
    id="peer-3",
    name="New peer",
    connected=True,
    login_expired=False,
    approval_required=True,
    last_seen=datetime(2026, 2, 3, 4, 5, tzinfo=UTC),
)


@pytest.fixture
def cloud_client() -> Iterator[MagicMock]:
    """Keep the Cloud boundary mocked across reloads and teardown."""
    with patch("custom_components.netbird.NetBirdApiClient") as client_class:
        client = client_class.return_value
        client.async_get_account = AsyncMock(return_value=NetBirdAccount(id=ACCOUNT))
        client.async_get_peers = AsyncMock(return_value=(PEER, MINIMAL_PEER))
        yield client


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    """Set up real platforms against an anonymized, mocked Cloud boundary."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: ACCOUNT, CONF_API_TOKEN: TOKEN},
        unique_id=ACCOUNT,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity(hass: HomeAssistant, peer_id: str, key: str) -> er.RegistryEntry | None:
    """Find an entity by its stable integration unique ID."""
    registry = er.async_get(hass)
    platform = (
        "sensor"
        if key
        in {
            "last_seen",
            "ip_address",
            "accessible_peers",
            "last_login",
            "ipv6_address",
            "hostname",
            "dns_label",
            "operating_system",
        }
        else "binary_sensor"
    )
    entity_id = registry.async_get_entity_id(
        platform, DOMAIN, f"{ACCOUNT}:{peer_id}:{key}"
    )
    return registry.async_get(entity_id) if entity_id else None


def _state(hass: HomeAssistant, entity_id: str) -> State:
    """Require an enabled entity to have a Home Assistant state."""
    state = hass.states.get(entity_id)
    assert state is not None
    return state


async def test_initial_devices_entities_and_single_request(
    hass: HomeAssistant, cloud_client: MagicMock
) -> None:
    """Both platforms share one snapshot and expose only approved peer data."""
    entry = await _setup(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert BINARY_PARALLEL == SENSOR_PARALLEL == 0
    cloud_client.async_get_peers.assert_awaited_once_with()
    devices = dr.async_get(hass)
    device = devices.async_get_device_by_identifier(
        (DOMAIN, f"{ACCOUNT}:peer-1"), entry.entry_id
    )
    assert device is not None
    assert device.manufacturer == "NetBird"
    assert device.name == "Test peer"
    assert device.sw_version == "0.0-test"
    assert device.configuration_url == "https://app.netbird.io/peer?id=peer-1"
    assert devices.async_get_device_by_identifier(
        (DOMAIN, f"{ACCOUNT}:peer-2"), entry.entry_id
    )
    account_device = devices.async_get_device_by_identifier(
        (DOMAIN, ACCOUNT), entry.entry_id
    )
    assert account_device is not None
    assert account_device.configuration_url == "https://app.netbird.io/peers"

    connected = _entity(hass, "peer-1", "connected")
    expired = _entity(hass, "peer-1", "login_expired")
    approval = _entity(hass, "peer-1", "approval_required")
    seen = _entity(hass, "peer-1", "last_seen")
    assert connected is not None
    assert expired is not None
    assert approval is not None
    assert seen is not None
    assert connected.device_id == device.id
    assert connected.original_device_class == "connectivity"
    assert expired.original_device_class == approval.original_device_class == "problem"
    assert _state(hass, connected.entity_id).state == "off"
    assert _state(hass, expired.entity_id).state == "on"
    assert approval.disabled_by is None
    assert seen.disabled_by is None
    assert seen.entity_category is None
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
        state = _state(hass, entity.entity_id)
        assert state.state == value
        assert state.attributes["netbird_key"] == key
    for key in ("ipv6_address", "hostname", "dns_label", "operating_system"):
        optional = _entity(hass, PEER.id, key)
        assert optional is not None
        assert optional.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    for key in ("ip_address", "accessible_peers", "last_login"):
        missing = _entity(hass, MINIMAL_PEER.id, key)
        assert missing is not None
        assert _state(hass, missing.entity_id).state == STATE_UNKNOWN
    for key in ("connected", "login_expired", "ssh_enabled", "ephemeral"):
        missing = _entity(hass, MINIMAL_PEER.id, key)
        assert missing is not None
        assert _state(hass, missing.entity_id).state == STATE_UNAVAILABLE
    assert _entity(hass, "peer-2", "approval_required") is None
    assert _entity(hass, "peer-2", "last_seen") is not None
    minimal_connection = _entity(hass, "peer-2", "connected")
    assert minimal_connection is not None
    assert _state(hass, minimal_connection.entity_id).state == STATE_UNAVAILABLE
    assert (
        _state(hass, connected.entity_id).attributes["friendly_name"]
        == "Test peer Connection"
    )

    await hass.config_entries.async_unload(entry.entry_id)


async def test_availability_recovery_and_absent_peer(
    hass: HomeAssistant, cloud_client: MagicMock
) -> None:
    """A failure hides retained data; offline and absence remain distinct."""
    entry = await _setup(hass)
    connected = _entity(hass, "peer-1", "connected")
    assert connected is not None
    coordinator = entry.runtime_data.coordinator

    cloud_client.async_get_peers.side_effect = TimeoutError()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert coordinator.data == (PEER, MINIMAL_PEER)
    assert _state(hass, connected.entity_id).state == STATE_UNAVAILABLE

    cloud_client.async_get_peers.side_effect = None
    cloud_client.async_get_peers.return_value = (PEER,)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, connected.entity_id).state == "off"
    missing = _entity(hass, "peer-2", "connected")
    assert missing is not None
    assert _state(hass, missing.entity_id).state == STATE_UNAVAILABLE
    assert cloud_client.async_get_peers.await_count == 3
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not coordinator._successful_refresh_listeners


async def test_dynamic_peer_lifecycle_without_duplicates(
    hass: HomeAssistant, cloud_client: MagicMock
) -> None:
    """New peers appear once and survive absence, failure, return, and reload."""
    entry = await _setup(hass)
    coordinator = entry.runtime_data.coordinator
    registry = er.async_get(hass)
    devices = dr.async_get(hass)

    cloud_client.async_get_peers.return_value = (PEER, MINIMAL_PEER, NEW_PEER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    new_device = devices.async_get_device_by_identifier(
        (DOMAIN, f"{ACCOUNT}:{NEW_PEER.id}"), entry.entry_id
    )
    assert new_device is not None
    new_entities = {
        key: _entity(hass, NEW_PEER.id, key)
        for key in ("connected", "login_expired", "approval_required", "last_seen")
    }
    assert all(new_entities.values())
    assert {entity.device_id for entity in new_entities.values() if entity} == {
        new_device.id
    }
    connected = new_entities["connected"]
    assert connected is not None
    assert _state(hass, connected.entity_id).state == "on"
    entity_ids = {entity.entity_id for entity in new_entities.values() if entity}

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert {
        entity.entity_id
        for key in new_entities
        if (entity := _entity(hass, NEW_PEER.id, key)) is not None
    } == entity_ids

    cloud_client.async_get_peers.return_value = (PEER, MINIMAL_PEER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, connected.entity_id).state == STATE_UNAVAILABLE
    assert devices.async_get(new_device.id) is not None

    cloud_client.async_get_peers.return_value = (PEER, MINIMAL_PEER, NEW_PEER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, connected.entity_id).state == "on"

    cloud_client.async_get_peers.side_effect = NetBirdSchemaError("invalid peer id")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert coordinator.data == (PEER, MINIMAL_PEER, NEW_PEER)
    assert _state(hass, connected.entity_id).state == STATE_UNAVAILABLE
    assert devices.async_get(new_device.id) is not None

    cloud_client.async_get_peers.side_effect = None
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert coordinator._shutdown_requested
    assert not coordinator._listeners
    assert {
        entity.entity_id
        for key in new_entities
        if (entity := _entity(hass, NEW_PEER.id, key)) is not None
    } == entity_ids
    reloaded_device = devices.async_get_device_by_identifier(
        (DOMAIN, f"{ACCOUNT}:{NEW_PEER.id}"), entry.entry_id
    )
    assert reloaded_device is not None
    assert reloaded_device.id == new_device.id
    assert (
        len(
            [
                entity
                for entity in registry.entities.values()
                if entity.unique_id.startswith(f"{ACCOUNT}:{NEW_PEER.id}:")
            ]
        )
        == 9
    )

    current = entry.runtime_data.coordinator
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert current._shutdown_requested
    assert not current._listeners


async def test_stale_peer_cleanup_threshold_failure_and_reappearance(
    hass: HomeAssistant, cloud_client: MagicMock
) -> None:
    """Cleanup needs ten successful absences and resets when the peer returns."""
    entry = await _setup(hass)
    coordinator = entry.runtime_data.coordinator
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    connected = _entity(hass, MINIMAL_PEER.id, "connected")
    device = devices.async_get_device_by_identifier(
        (DOMAIN, f"{ACCOUNT}:{MINIMAL_PEER.id}"), entry.entry_id
    )
    assert connected is not None
    assert device is not None
    original_entity_ids = {
        entity.entity_id
        for entity in registry.entities.values()
        if entity.unique_id.startswith(f"{ACCOUNT}:{MINIMAL_PEER.id}:")
    }

    cloud_client.async_get_peers.return_value = (PEER,)
    for _ in range(9):
        await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get(connected.entity_id) is not None
    assert devices.async_get(device.id) is not None

    cloud_client.async_get_peers.return_value = (PEER, MINIMAL_PEER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get(connected.entity_id) is not None
    assert devices.async_get(device.id) is not None

    cloud_client.async_get_peers.return_value = (PEER,)
    for _ in range(9):
        await coordinator.async_refresh()
    cloud_client.async_get_peers.side_effect = NetBirdSchemaError("invalid peer id")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get(connected.entity_id) is not None
    assert devices.async_get(device.id) is not None

    cloud_client.async_get_peers.side_effect = None
    old_coordinator = coordinator
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert not old_coordinator._successful_refresh_listeners
    coordinator = entry.runtime_data.coordinator
    for _ in range(9):
        await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get(connected.entity_id) is not None
    assert devices.async_get(device.id) is not None

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get(connected.entity_id) is None
    assert devices.async_get(device.id) is None
    assert hass.states.get(connected.entity_id) is None

    cloud_client.async_get_peers.return_value = (PEER, MINIMAL_PEER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    replacement = _entity(hass, MINIMAL_PEER.id, "connected")
    replacement_device = devices.async_get_device_by_identifier(
        (DOMAIN, f"{ACCOUNT}:{MINIMAL_PEER.id}"), entry.entry_id
    )
    assert replacement is not None
    assert replacement.entity_id == connected.entity_id
    assert replacement_device is not None
    assert {
        entity.entity_id
        for entity in registry.entities.values()
        if entity.unique_id.startswith(f"{ACCOUNT}:{MINIMAL_PEER.id}:")
    } == original_entity_ids

    await hass.config_entries.async_unload(entry.entry_id)


async def test_stale_peer_cleanup_blocks_foreign_registry_association(
    hass: HomeAssistant, cloud_client: MagicMock
) -> None:
    """A foreign entity association preserves the peer and raises a repair."""
    entry = await _setup(hass)
    coordinator = entry.runtime_data.coordinator
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_device_by_identifier(
        (DOMAIN, f"{ACCOUNT}:{MINIMAL_PEER.id}"), entry.entry_id
    )
    assert device is not None
    foreign_entry = MockConfigEntry(domain="foreign_test", data={})
    foreign_entry.add_to_hass(hass)
    foreign = registry.async_get_or_create(
        "sensor",
        "foreign_test",
        "foreign-peer-link",
        config_entry=foreign_entry,
        device_id=device.id,
    )

    cloud_client.async_get_peers.return_value = (PEER,)
    for _ in range(10):
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert devices.async_get(device.id) is not None
    assert _entity(hass, MINIMAL_PEER.id, "connected") is not None
    issues = ir.async_get(hass).issues
    assert (
        len([issue for (domain, _), issue in issues.items() if domain == DOMAIN]) == 1
    )
    assert (
        next(
            issue for (domain, _), issue in issues.items() if domain == DOMAIN
        ).translation_key
        == "stale_peer_cleanup_blocked"
    )

    registry.async_remove(foreign.entity_id)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert devices.async_get(device.id) is None
    assert _entity(hass, MINIMAL_PEER.id, "connected") is None
    assert not [issue for (domain, _), issue in issues.items() if domain == DOMAIN]

    await hass.config_entries.async_unload(entry.entry_id)


async def test_timestamp_and_reload_unload(
    hass: HomeAssistant, cloud_client: MagicMock
) -> None:
    """A diagnostic timestamp normalizes to UTC and listeners do not multiply."""
    entry = await _setup(hass)
    seen = _entity(hass, "peer-1", "last_seen")
    assert seen is not None
    registry = er.async_get(hass)
    registry.async_update_entity(seen.entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    old = entry.runtime_data.coordinator
    seen = _entity(hass, "peer-1", "last_seen")
    assert seen is not None
    assert _state(hass, seen.entity_id).state == "2026-01-02T03:04:00+00:00"

    cloud_client.async_get_peers.return_value = (
        NetBirdPeer(id="peer-1", connected=True, login_expired=None, last_seen=None),
        MINIMAL_PEER,
    )
    await old.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, seen.entity_id).state == STATE_UNKNOWN
    expired = _entity(hass, "peer-1", "login_expired")
    assert expired is not None
    assert _state(hass, expired.entity_id).state == STATE_UNAVAILABLE

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert old._shutdown_requested
    assert old._unsub_refresh is None
    assert not old._listeners
    current = entry.runtime_data.coordinator
    assert current is not old
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert current._shutdown_requested
    assert current._unsub_refresh is None
    assert not current._listeners
    assert cloud_client.async_get_peers.await_count == 4


def test_entity_translation_keys_match_descriptions() -> None:
    """Both languages translate every entity exposed by the platforms."""
    resource_dir = Path(__file__).parents[1] / "custom_components" / DOMAIN
    strings = json.loads((resource_dir / "strings.json").read_text(encoding="utf-8"))
    english = json.loads(
        (resource_dir / "translations" / "en.json").read_text(encoding="utf-8")
    )
    ukrainian = json.loads(
        (resource_dir / "translations" / "uk.json").read_text(encoding="utf-8")
    )
    assert english == strings
    assert (
        ukrainian["entity"]["binary_sensor"].keys()
        == strings["entity"]["binary_sensor"].keys()
    )
    assert ukrainian["entity"]["sensor"].keys() == strings["entity"]["sensor"].keys()
    for platform, descriptions in ukrainian["entity"].items():
        for key, description in descriptions.items():
            assert description["name"]
            assert description["name"] != english["entity"][platform][key]["name"]
