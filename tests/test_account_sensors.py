"""Runtime tests for NetBird account peer summary sensors."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.const import CONF_ACCOUNT_ID, CONF_API_TOKEN, DOMAIN
from custom_components.netbird.models import NetBirdAccount, NetBirdPeer

ACCOUNT = "account-test-id"
PEERS = (
    NetBirdPeer(id="peer-1", connected=True),
    NetBirdPeer(id="peer-2", connected=False),
    NetBirdPeer(id="peer-3", connected=None),
)


def _entry() -> MockConfigEntry:
    """Create a valid, anonymous account entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: ACCOUNT, CONF_API_TOKEN: "test-token"},
        unique_id=ACCOUNT,
    )


def _entity_id(hass: HomeAssistant, key: str) -> str:
    """Return the registry entity ID for an account count."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{ACCOUNT}:{key}"
    )
    assert entity_id is not None
    return entity_id


def _state(hass: HomeAssistant, entity_id: str) -> State:
    """Require an enabled sensor state."""
    state = hass.states.get(entity_id)
    assert state is not None
    return state


async def test_account_counts_availability_and_reload(hass: HomeAssistant) -> None:
    """Counts use one peer poll, recover, and retain stable registry identity."""
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.netbird.NetBirdApiClient") as client_class:
        client = client_class.return_value
        client.async_get_account = AsyncMock(return_value=NetBirdAccount(id=ACCOUNT))
        client.async_get_peers = AsyncMock(return_value=PEERS)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        total_id = _entity_id(hass, "peer_count")
        connected_id = _entity_id(hass, "connected_peer_count")
        assert _state(hass, total_id).state == "3"
        assert _state(hass, connected_id).state == "1"
        assert _state(hass, total_id).attributes["friendly_name"] == (
            "NetBird account Total peers"
        )
        client.async_get_peers.assert_awaited_once_with()

        devices = dr.async_get(hass)
        device = devices.async_get_device_by_identifier(
            (DOMAIN, ACCOUNT), entry.entry_id
        )
        assert device is not None
        assert device.manufacturer == "NetBird"
        registry = er.async_get(hass)
        total_entry = registry.async_get(total_id)
        connected_entry = registry.async_get(connected_id)
        assert total_entry is not None
        assert connected_entry is not None
        assert total_entry.device_id == device.id
        assert connected_entry.device_id == device.id
        assert total_entry.original_device_class is None

        coordinator = entry.runtime_data.coordinator
        client.async_get_peers.side_effect = TimeoutError()
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert _state(hass, total_id).state == STATE_UNAVAILABLE
        assert _state(hass, connected_id).state == STATE_UNAVAILABLE
        assert coordinator.data == PEERS

        client.async_get_peers.side_effect = None
        client.async_get_peers.return_value = ()
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert _state(hass, total_id).state == "0"
        assert _state(hass, connected_id).state == "0"

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert _entity_id(hass, "peer_count") == total_id
        assert _entity_id(hass, "connected_peer_count") == connected_id
        reloaded_device = devices.async_get_device_by_identifier(
            (DOMAIN, ACCOUNT), entry.entry_id
        )
        assert reloaded_device is not None
        assert reloaded_device.id == device.id
        account_ids = {f"{ACCOUNT}:peer_count", f"{ACCOUNT}:connected_peer_count"}
        entries = er.async_entries_for_config_entry(registry, entry.entry_id)
        account_entities = [
            entity for entity in entries if entity.unique_id in account_ids
        ]
        assert len(account_entities) == 2
        assert client.async_get_peers.await_count == 4
        current_coordinator = entry.runtime_data.coordinator
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert not current_coordinator._listeners


async def test_initial_empty_snapshot_registers_zero_counts(
    hass: HomeAssistant,
) -> None:
    """An empty peer list remains a valid account state."""
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.netbird.NetBirdApiClient") as client_class:
        client = client_class.return_value
        client.async_get_account = AsyncMock(return_value=NetBirdAccount(id=ACCOUNT))
        client.async_get_peers = AsyncMock(return_value=())
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert _state(hass, _entity_id(hass, "peer_count")).state == "0"
        assert _state(hass, _entity_id(hass, "connected_peer_count")).state == "0"
        client.async_get_peers.assert_awaited_once_with()
        await hass.config_entries.async_unload(entry.entry_id)
