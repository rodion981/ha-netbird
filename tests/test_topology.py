"""Tests for isolated NetBird topology polling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.api import (
    NetBirdAuthenticationError,
    NetBirdTransportError,
)
from custom_components.netbird.const import DOMAIN, TOPOLOGY_REQUEST_CONCURRENCY
from custom_components.netbird.models import (
    NetBirdNetwork,
    NetBirdRouter,
)
from custom_components.netbird.topology import NetBirdTopologyCoordinator


async def test_topology_request_budget_and_concurrency(hass: HomeAssistant) -> None:
    """A refresh uses 1 + 2N requests under one shared ceiling."""
    networks = tuple(
        NetBirdNetwork(f"n-{index}", f"Network {index}") for index in range(3)
    )
    active = 0
    maximum = 0

    async def nested(network_id: str) -> tuple[()]:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        return ()

    client = AsyncMock()
    client.async_get_networks.return_value = networks
    client.async_get_network_resources.side_effect = nested
    client.async_get_network_routers.side_effect = nested
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = NetBirdTopologyCoordinator(hass, entry, client)

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert len(coordinator.data.networks) == 3
    assert client.async_get_networks.await_count == 1
    assert client.async_get_network_resources.await_count == 3
    assert client.async_get_network_routers.await_count == 3
    assert maximum <= TOPOLOGY_REQUEST_CONCURRENCY


async def test_topology_preserves_partial_sections(hass: HomeAssistant) -> None:
    """One nested failure marks only that section unavailable."""
    network = NetBirdNetwork("n-1", "Network")
    client = AsyncMock()
    client.async_get_networks.return_value = (network,)
    client.async_get_network_resources.side_effect = NetBirdTransportError("safe")
    client.async_get_network_routers.return_value = (
        NetBirdRouter("router", "n-1", True, peer_id="peer"),
    )
    coordinator = NetBirdTopologyCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), client
    )

    await coordinator.async_refresh()

    item = coordinator.data.networks[0]
    assert item.resources is None
    assert item.routers == (NetBirdRouter("router", "n-1", True, peer_id="peer"),)


async def test_topology_empty_networks_have_no_nested_requests(
    hass: HomeAssistant,
) -> None:
    """An empty inventory is a complete zero snapshot."""
    client = AsyncMock()
    client.async_get_networks.return_value = ()
    coordinator = NetBirdTopologyCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), client
    )

    await coordinator.async_refresh()

    assert coordinator.data.networks == ()
    client.async_get_network_resources.assert_not_awaited()
    client.async_get_network_routers.assert_not_awaited()


async def test_nested_topology_auth_failure_requests_reauthentication(
    hass: HomeAssistant,
) -> None:
    """A 401 from a nested endpoint keeps authentication semantics."""
    client = AsyncMock()
    client.async_get_networks.return_value = (NetBirdNetwork("n-1", "Network"),)
    client.async_get_network_resources.side_effect = NetBirdAuthenticationError("safe")
    client.async_get_network_routers.return_value = ()
    coordinator = NetBirdTopologyCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), client
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
