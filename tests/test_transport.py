"""Connection-time DNS filtering and self-hosted session ownership."""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp.abc import ResolveResult
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.api import NetBirdAddressError, NetBirdApiClient
from custom_components.netbird.const import (
    CONF_ACCOUNT_ID,
    CONF_API_TOKEN,
    CONF_DEPLOYMENT_TYPE,
    DEPLOYMENT_CLOUD,
    DEPLOYMENT_SELF_HOSTED,
    DOMAIN,
)
from custom_components.netbird.deployment import (
    NetBirdBlockedAddressError,
    NetBirdDeployment,
    NetBirdResolutionError,
)
from custom_components.netbird.models import NetBirdAccount, NetBirdPeer
from custom_components.netbird.transport import NetBirdResolver, async_netbird_session


def _deployment(kind: str = DEPLOYMENT_SELF_HOSTED) -> NetBirdDeployment:
    return NetBirdDeployment(kind, "https://netbird.example", None, None, False)


def _result(address: str) -> ResolveResult:
    return ResolveResult(
        hostname="netbird.example",
        host=address,
        port=443,
        family=socket.AF_INET6 if ":" in address else socket.AF_INET,
        proto=socket.IPPROTO_TCP,
        flags=socket.AI_NUMERICHOST,
    )


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "::1", "::ffff:127.0.0.1", "0.0.0.0", "169.254.169.254", "224.0.0.1"],
)
async def test_resolver_rejects_any_blocked_answer(address: str) -> None:
    with (
        patch(
            "aiohttp.resolver.ThreadedResolver.resolve",
            new=AsyncMock(return_value=[_result("10.0.0.2"), _result(address)]),
        ),
        pytest.raises(NetBirdBlockedAddressError),
    ):
        await NetBirdResolver().resolve("netbird.example", 443)


async def test_resolver_preserves_private_dual_stack_addresses() -> None:
    results = [_result("10.0.0.2"), _result("fd00::2")]
    with patch(
        "aiohttp.resolver.ThreadedResolver.resolve", new=AsyncMock(return_value=results)
    ):
        assert await NetBirdResolver().resolve("netbird.example", 443) == results


async def test_cloud_session_is_shared_and_remains_open(hass: HomeAssistant) -> None:
    shared = async_get_clientsession(hass)
    async with async_netbird_session(hass, _deployment(DEPLOYMENT_CLOUD)) as session:
        assert session is shared
    assert not shared.closed


@pytest.mark.parametrize("fail", [False, True])
async def test_flow_closes_owned_self_hosted_session(
    hass: HomeAssistant, fail: bool
) -> None:
    try:
        async with async_netbird_session(hass, _deployment()) as session:
            assert not session.closed
            if fail:
                raise ValueError("synthetic validation failure")
    except ValueError:
        assert fail
    assert session.closed


async def test_dns_change_blocks_actual_client_before_connection(
    hass: HomeAssistant,
) -> None:
    """Guard the resolver used by aiohttp, not a separate preflight lookup."""
    with (
        patch(
            "aiohttp.resolver.ThreadedResolver.resolve",
            new=AsyncMock(return_value=[_result("127.0.0.1")]),
        ),
        patch(
            "aiohttp.connector.aiohappyeyeballs.start_connection", new=AsyncMock()
        ) as connect,
    ):
        async with async_netbird_session(hass, _deployment()) as session:
            client = NetBirdApiClient(
                session, "synthetic-token", base_url="https://netbird.example"
            )
            with pytest.raises(NetBirdAddressError, match="address is blocked"):
                await client.async_get_account()
        connect.assert_not_awaited()


@pytest.mark.parametrize("fail_setup", [False, True])
async def test_entry_closes_owned_session_on_unload_or_failure(
    hass: HomeAssistant, fail_setup: bool
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test-account",
        version=3,
        data={
            CONF_ACCOUNT_ID: "test-account",
            CONF_API_TOKEN: "synthetic-token",
            CONF_DEPLOYMENT_TYPE: DEPLOYMENT_SELF_HOSTED,
        },
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.netbird.async_resolve_deployment",
            new=AsyncMock(return_value=_deployment()),
        ),
        patch("custom_components.netbird.NetBirdApiClient") as client_class,
    ):
        client = client_class.return_value
        client.async_get_account = AsyncMock(
            side_effect=NetBirdAddressError("blocked") if fail_setup else None,
            return_value=NetBirdAccount("test-account"),
        )
        client.async_get_peers = AsyncMock(
            return_value=(NetBirdPeer("peer", name="Self-hosted peer", connected=True),)
        )
        client.async_get_networks = AsyncMock(return_value=())
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        session = client_class.call_args.args[0]
        if fail_setup:
            assert not result
            assert entry.state is ConfigEntryState.SETUP_RETRY
        else:
            assert result
            assert not session.closed
            assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert session.closed


async def test_dns_failure_is_retryable_during_entry_setup(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test-account",
        version=3,
        data={CONF_ACCOUNT_ID: "test-account", CONF_API_TOKEN: "synthetic-token"},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.netbird.async_resolve_deployment",
        new=AsyncMock(side_effect=NetBirdResolutionError("DNS unavailable")),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
