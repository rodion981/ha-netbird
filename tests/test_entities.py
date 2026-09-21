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
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

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
    connected=False,
    login_expired=True,
    approval_required=False,
    last_seen=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
)
MINIMAL_PEER = NetBirdPeer(id="peer-2")


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
    platform = "sensor" if key == "last_seen" else "binary_sensor"
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
    assert devices.async_get_device_by_identifier(
        (DOMAIN, f"{ACCOUNT}:peer-2"), entry.entry_id
    )

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
    assert approval.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert seen.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert seen.entity_category == "diagnostic"
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
