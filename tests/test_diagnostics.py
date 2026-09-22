"""Runtime privacy tests for allowlisted NetBird diagnostics."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.api import NetBirdTransportError
from custom_components.netbird.const import CONF_ACCOUNT_ID, CONF_API_TOKEN, DOMAIN
from custom_components.netbird.diagnostics import async_get_config_entry_diagnostics
from custom_components.netbird.models import NetBirdAccount, NetBirdNetwork, NetBirdPeer

ACCOUNT = "account-private-id-sentinel"
SECRET_VALUES = (
    "pat-secret-sentinel",
    ACCOUNT,
    "peer-private-id-sentinel",
    "user-private-id-sentinel",
    "name-private-sentinel",
    "hostname-private-sentinel",
    "serial-private-sentinel",
    "203.0.113.44",
    "10.0.0.0/24",
    "person@example.invalid",
    "https://private.example.invalid/path",
    "connection-private-sentinel",
    "nested-secret-key-sentinel",
    "header-secret-sentinel",
    "raw-response-sentinel",
)


async def test_diagnostics_allowlist_and_failure_privacy(hass: HomeAssistant) -> None:
    """Nested secrets never enter diagnostics; failure preserves cached counts."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCOUNT_ID: ACCOUNT,
            CONF_API_TOKEN: SECRET_VALUES[0],
            "headers": {SECRET_VALUES[12]: [SECRET_VALUES[13]]},
            "private_url": SECRET_VALUES[10],
            "nested": {SECRET_VALUES[12]: [{"body": SECRET_VALUES[14]}]},
        },
        unique_id=ACCOUNT,
    )
    entry.add_to_hass(hass)
    peers = (
        NetBirdPeer(
            id=SECRET_VALUES[2],
            name=SECRET_VALUES[4],
            user_id=SECRET_VALUES[3],
            hostname=SECRET_VALUES[5],
            serial_number=SECRET_VALUES[6],
            ip=SECRET_VALUES[7],
            connection_ip=SECRET_VALUES[11],
            connected=True,
        ),
        NetBirdPeer(id="another-peer", connected=False),
    )
    with patch("custom_components.netbird.NetBirdApiClient") as client_class:
        client = client_class.return_value
        client.async_get_account = AsyncMock(return_value=NetBirdAccount(id=ACCOUNT))
        client.async_get_peers = AsyncMock(return_value=peers)
        client.async_get_networks = AsyncMock(
            return_value=(NetBirdNetwork("network-private", "private-name"),)
        )
        client.async_get_network_resources = AsyncMock(return_value=())
        client.async_get_network_routers = AsyncMock(return_value=())
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data.coordinator

        requests_before = client.async_get_peers.await_count
        success = await async_get_config_entry_diagnostics(hass, entry)
        assert success == {
            "integration_version": "0.2.0",
            "deployment_class": "cloud",
            "coordinator": {
                "last_update_success": True,
                "last_successful_refresh": (
                    coordinator.last_successful_refresh.isoformat()
                ),
                "error_class": None,
            },
            "peers": {"total": 2, "connected": 1},
            "topology": {
                "last_update_success": True,
                "error_class": None,
                "networks": 1,
                "complete_resource_sections": 1,
                "complete_router_sections": 1,
            },
        }
        assert (
            datetime.fromisoformat(
                success["coordinator"]["last_successful_refresh"]
            ).tzinfo
            is not None
        )
        assert client.async_get_peers.await_count == requests_before
        assert client.async_get_account.await_count == 1

        client.async_get_peers.side_effect = NetBirdTransportError(SECRET_VALUES[14])
        await coordinator.async_refresh()
        failed = await async_get_config_entry_diagnostics(hass, entry)
        assert failed["coordinator"] == {
            "last_update_success": False,
            "last_successful_refresh": success["coordinator"][
                "last_successful_refresh"
            ],
            "error_class": "NetBirdRefreshError",
        }
        assert failed["peers"] == {"total": 2, "connected": 1}
        assert client.async_get_peers.await_count == requests_before + 1
        serialized = json.dumps((success, failed), sort_keys=True)
        for secret in SECRET_VALUES:
            assert secret not in serialized
        for forbidden_key in ("api_token", "account_id", "peer_id", "headers", "raw"):
            assert forbidden_key not in serialized
        await hass.config_entries.async_unload(entry.entry_id)


async def test_unloaded_entry_diagnostics_do_not_invent_zero_counts(
    hass: HomeAssistant,
) -> None:
    """Missing cached runtime is explicit, not misreported as zero peers."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: ACCOUNT, CONF_API_TOKEN: SECRET_VALUES[0]},
        unique_id=ACCOUNT,
    )
    entry.add_to_hass(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["coordinator"] == {
        "last_update_success": False,
        "last_successful_refresh": None,
        "error_class": None,
    }
    assert diagnostics["peers"] == {"total": None, "connected": None}
    assert diagnostics["topology"] == {
        "last_update_success": False,
        "error_class": None,
        "networks": None,
        "complete_resource_sections": None,
        "complete_router_sections": None,
    }
