"""Cross-component Home Assistant proof for the assembled NetBird MVP."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.api import (
    NetBirdAuthenticationError,
    NetBirdSchemaError,
)
from custom_components.netbird.const import CONF_ACCOUNT_ID, CONF_API_TOKEN, DOMAIN
from custom_components.netbird.diagnostics import async_get_config_entry_diagnostics
from custom_components.netbird.models import NetBirdAccount, NetBirdPeer

ACCOUNT = "mvp-test-account"
PEERS = (
    NetBirdPeer(id="mvp-peer-1", name="First peer", connected=True),
    NetBirdPeer(id="mvp-peer-2", name="Second peer", connected=False),
)


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    """Require a stable registry identity for an assembled MVP entity."""
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


def _state(hass: HomeAssistant, entity_id: str) -> State:
    """Require an enabled Home Assistant state."""
    state = hass.states.get(entity_id)
    assert state is not None
    return state


async def test_complete_mvp_lifecycle_without_extra_peer_requests(
    hass: HomeAssistant,
) -> None:
    """Assembled platforms share one coordinator through failures and reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: ACCOUNT, CONF_API_TOKEN: "fake-mvp-pat"},
        unique_id=ACCOUNT,
    )
    entry.add_to_hass(hass)
    with patch("custom_components.netbird.NetBirdApiClient") as client_class:
        client = client_class.return_value
        client.async_get_account = AsyncMock(return_value=NetBirdAccount(id=ACCOUNT))
        client.async_get_peers = AsyncMock(return_value=PEERS)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        devices = dr.async_get(hass)
        account_device = devices.async_get_device_by_identifier(
            (DOMAIN, ACCOUNT), entry.entry_id
        )
        first_device = devices.async_get_device_by_identifier(
            (DOMAIN, f"{ACCOUNT}:mvp-peer-1"), entry.entry_id
        )
        second_device = devices.async_get_device_by_identifier(
            (DOMAIN, f"{ACCOUNT}:mvp-peer-2"), entry.entry_id
        )
        assert account_device is not None
        assert first_device is not None
        assert second_device is not None

        total_id = _entity_id(hass, "sensor", f"{ACCOUNT}:peer_count")
        connected_count_id = _entity_id(
            hass, "sensor", f"{ACCOUNT}:connected_peer_count"
        )
        peer_id = _entity_id(hass, "binary_sensor", f"{ACCOUNT}:mvp-peer-1:connected")
        assert _state(hass, total_id).state == "2"
        assert _state(hass, connected_count_id).state == "1"
        assert _state(hass, peer_id).state == "on"
        client.async_get_peers.assert_awaited_once_with()

        coordinator = entry.runtime_data.coordinator
        client.async_get_peers.side_effect = NetBirdSchemaError("invalid peer id")
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.data == PEERS
        assert _state(hass, total_id).state == STATE_UNAVAILABLE
        assert _state(hass, peer_id).state == STATE_UNAVAILABLE
        retained_device = devices.async_get_device_by_identifier(
            (DOMAIN, f"{ACCOUNT}:mvp-peer-1"), entry.entry_id
        )
        assert retained_device is not None
        assert retained_device.id == first_device.id
        requests_before_diagnostics = client.async_get_peers.await_count
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        assert diagnostics["coordinator"]["last_update_success"] is False
        assert diagnostics["peers"] == {"total": 2, "connected": 1}
        assert client.async_get_peers.await_count == requests_before_diagnostics

        with patch.object(entry, "async_start_reauth_if_available") as reauth:
            client.async_get_peers.side_effect = NetBirdAuthenticationError("safe")
            await coordinator.async_refresh()
            reauth.assert_called_once_with(hass)

        client.async_get_peers.side_effect = None
        client.async_get_peers.return_value = (
            NetBirdPeer(id="mvp-peer-1", connected=False),
            PEERS[1],
        )
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert _state(hass, total_id).state == "2"
        assert _state(hass, connected_count_id).state == "0"
        assert _state(hass, peer_id).state == "off"

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert coordinator._shutdown_requested
        assert not coordinator._listeners
        assert _entity_id(hass, "sensor", f"{ACCOUNT}:peer_count") == total_id
        assert (
            _entity_id(hass, "binary_sensor", f"{ACCOUNT}:mvp-peer-1:connected")
            == peer_id
        )
        reloaded_account = devices.async_get_device_by_identifier(
            (DOMAIN, ACCOUNT), entry.entry_id
        )
        reloaded_peer = devices.async_get_device_by_identifier(
            (DOMAIN, f"{ACCOUNT}:mvp-peer-2"), entry.entry_id
        )
        assert reloaded_account is not None
        assert reloaded_peer is not None
        assert reloaded_account.id == account_device.id
        assert reloaded_peer.id == second_device.id
        current = entry.runtime_data.coordinator
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert current._shutdown_requested
        assert not current._listeners
        assert client.async_get_peers.await_count == 5
