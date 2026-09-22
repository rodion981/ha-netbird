"""Home Assistant tests for topology summary and resource entities."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.api import NetBirdTransportError
from custom_components.netbird.const import CONF_ACCOUNT_ID, CONF_API_TOKEN, DOMAIN
from custom_components.netbird.models import (
    NetBirdAccount,
    NetBirdNetwork,
    NetBirdPeer,
    NetBirdResource,
    NetBirdRouter,
)

ACCOUNT = "topology-account"
NETWORK = NetBirdNetwork("network-1", "Home LAN")
RESOURCE = NetBirdResource(
    "resource-1", "network-1", "Home subnet", "192.0.2.0/24", "subnet", True
)
ROUTER = NetBirdRouter("router-1", "network-1", True, peer_id="peer-1")


@pytest.fixture
def topology_client() -> Iterator[MagicMock]:
    """Provide one complete topology and peer snapshot."""
    with patch("custom_components.netbird.NetBirdApiClient") as client_class:
        client = client_class.return_value
        client.async_get_account = AsyncMock(return_value=NetBirdAccount(ACCOUNT))
        client.async_get_peers = AsyncMock(
            return_value=(NetBirdPeer("peer-1", name="Router", connected=True),)
        )
        client.async_get_networks = AsyncMock(return_value=(NETWORK,))
        client.async_get_network_resources = AsyncMock(return_value=(RESOURCE,))
        client.async_get_network_routers = AsyncMock(return_value=(ROUTER,))
        yield client


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: ACCOUNT, CONF_API_TOKEN: "test-token"},
        unique_id=ACCOUNT,
        version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


async def test_account_network_and_resource_entities(
    hass: HomeAssistant, topology_client: MagicMock
) -> None:
    """A complete snapshot exposes useful totals and resource details."""
    entry = await _setup(hass)
    assert _state(hass, _entity_id(hass, "sensor", f"{ACCOUNT}:network_count")) == "1"
    assert _state(hass, _entity_id(hass, "sensor", f"{ACCOUNT}:resource_count")) == "1"
    assert (
        _state(
            hass,
            _entity_id(hass, "sensor", f"{ACCOUNT}:network:network-1:router_count"),
        )
        == "1"
    )
    assert (
        _state(
            hass,
            _entity_id(
                hass,
                "sensor",
                f"{ACCOUNT}:network:network-1:connected_routing_peers",
            ),
        )
        == "1"
    )
    assert (
        _state(
            hass,
            _entity_id(
                hass,
                "sensor",
                f"{ACCOUNT}:network:network-1:resource:resource-1:address",
            ),
        )
        == "192.0.2.0/24"
    )
    assert (
        _state(
            hass,
            _entity_id(
                hass,
                "binary_sensor",
                f"{ACCOUNT}:network:network-1:resource:resource-1:enabled",
            ),
        )
        == "on"
    )

    devices = dr.async_get(hass)
    network_device = devices.async_get_device_by_identifier(
        (DOMAIN, f"{ACCOUNT}:network:network-1"), entry.entry_id
    )
    resource_device = devices.async_get_device_by_identifier(
        (DOMAIN, f"{ACCOUNT}:network:network-1:resource:resource-1"), entry.entry_id
    )
    assert network_device is not None
    assert resource_device is not None
    assert resource_device.via_device_id == network_device.id


async def test_partial_resource_failure_is_not_reported_as_zero(
    hass: HomeAssistant, topology_client: MagicMock
) -> None:
    """Failed nested sections become unavailable while routers remain usable."""
    entry = await _setup(hass)
    topology_client.async_get_network_resources.side_effect = NetBirdTransportError(
        "safe"
    )

    await entry.runtime_data.topology_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert (
        _state(hass, _entity_id(hass, "sensor", f"{ACCOUNT}:resource_count"))
        == STATE_UNAVAILABLE
    )
    assert (
        _state(
            hass,
            _entity_id(hass, "sensor", f"{ACCOUNT}:network:network-1:resource_count"),
        )
        == STATE_UNAVAILABLE
    )
    assert (
        _state(
            hass,
            _entity_id(hass, "sensor", f"{ACCOUNT}:network:network-1:router_count"),
        )
        == "1"
    )


async def test_stale_resource_and_network_devices_are_removed(
    hass: HomeAssistant, topology_client: MagicMock
) -> None:
    """Ten complete absences remove only integration-owned topology devices."""
    entry = await _setup(hass)
    devices = dr.async_get(hass)
    resource_id = _entity_id(
        hass,
        "sensor",
        f"{ACCOUNT}:network:network-1:resource:resource-1:address",
    )
    topology_client.async_get_networks.return_value = ()

    for _ in range(10):
        await entry.runtime_data.topology_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert er.async_get(hass).async_get(resource_id) is None
    assert (
        devices.async_get_device_by_identifier(
            (DOMAIN, f"{ACCOUNT}:network:network-1:resource:resource-1"),
            entry.entry_id,
        )
        is None
    )
    assert (
        devices.async_get_device_by_identifier(
            (DOMAIN, f"{ACCOUNT}:network:network-1"), entry.entry_id
        )
        is None
    )
