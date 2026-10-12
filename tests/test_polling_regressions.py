"""Regression proof for private failures, request lifetime and retry hints."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.api import (
    NetBirdAuthenticationError,
    NetBirdRateLimitError,
    NetBirdTransportError,
)
from custom_components.netbird.config_flow import (
    NetBirdConfigFlow,
    _async_validate_topology_contract,
)
from custom_components.netbird.const import CONF_API_URL, CONF_CA_CERTIFICATE, DOMAIN
from custom_components.netbird.coordinator import NetBirdPeerCoordinator
from custom_components.netbird.deployment import NetBirdResolutionError
from custom_components.netbird.models import NetBirdNetwork
from custom_components.netbird.topology import NetBirdTopologyCoordinator


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 60),
        ("", 60),
        ("900", 900),
        ("0", 60),
        ("-1", 60),
        ("nan", 60),
        ("inf", 60),
        ("9" * 400, 60),
        ("1.5", 60),
        ("private-invalid-header", 60),
    ],
)
def test_retry_delay_rejects_invalid_or_short_hints(
    value: str | None, expected: float
) -> None:
    assert NetBirdRateLimitError(value).retry_delay(60) == expected


def test_retry_delay_accepts_http_dates() -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    with patch("custom_components.netbird.api.datetime") as clock:
        clock.now.return_value = now
        future = format_datetime(now + timedelta(seconds=900), usegmt=True)
        assert NetBirdRateLimitError(future).retry_delay(60) == 900
        past = format_datetime(now - timedelta(seconds=900), usegmt=True)
        assert NetBirdRateLimitError(past).retry_delay(60) == 60
        assert NetBirdRateLimitError("Fri, 09 Oct 2026 00:15:00").retry_delay(60) == 900


@pytest.mark.parametrize("nested", [False, True])
async def test_topology_debug_log_excludes_exception_details(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, nested: bool
) -> None:
    """Neither transport causes nor unexpected nested failures reach logs."""
    client = AsyncMock()
    client.async_get_networks.return_value = (NetBirdNetwork("n-1", "Demo"),)
    secret = "private-transport-detail-sentinel"
    error = NetBirdTransportError("safe")
    error.__cause__ = OSError(secret)
    if nested:
        client.async_get_network_resources.side_effect = RuntimeError(secret)
        client.async_get_network_routers.return_value = ()
    else:
        client.async_get_networks.side_effect = error
    coordinator = NetBirdTopologyCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), client
    )
    with caplog.at_level(logging.DEBUG, logger="custom_components.netbird.topology"):
        await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert secret not in caplog.text


@pytest.mark.parametrize("flow", [False, True])
@pytest.mark.parametrize("cancel", [False, True])
async def test_request_batch_drains_before_returning(
    hass: HomeAssistant, flow: bool, cancel: bool
) -> None:
    """Authentication failure and caller cancellation leave no owned requests."""
    client = AsyncMock()
    client.async_get_networks.return_value = tuple(
        NetBirdNetwork(f"n-{index}", "Demo") for index in range(4)
    )
    started = asyncio.Event()
    release = asyncio.Event()
    active = 0

    async def request(network_id: str) -> tuple[()]:
        nonlocal active
        active += 1
        if active == 6:
            started.set()
        try:
            if network_id == "n-0" and not cancel:
                await started.wait()
                raise NetBirdAuthenticationError("safe")
            await release.wait()
            return ()
        finally:
            await asyncio.sleep(0)
            active -= 1

    client.async_get_network_resources.side_effect = request
    client.async_get_network_routers.side_effect = request
    coordinator = NetBirdTopologyCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), client
    )
    task = asyncio.create_task(
        _async_validate_topology_contract(client)
        if flow
        else coordinator._async_update_data()
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        if cancel:
            task.cancel()
        expected = (
            asyncio.CancelledError
            if cancel
            else NetBirdAuthenticationError
            if flow
            else ConfigEntryAuthFailed
        )
        with pytest.raises(expected):
            await task
        assert active == 0
    finally:
        release.set()
        await hass.async_block_till_done()


@pytest.mark.parametrize("kind", ["peers", "networks", "resources", "routers"])
async def test_rate_limit_reaches_coordinator_scheduler(
    hass: HomeAssistant, kind: str
) -> None:
    """A nested 429 must not become a successful, incomplete snapshot."""
    client = AsyncMock()
    client.async_get_networks.return_value = (NetBirdNetwork("n-1", "Demo"),)
    client.async_get_network_resources.return_value = ()
    client.async_get_network_routers.return_value = ()
    method = {
        "peers": client.async_get_peers,
        "networks": client.async_get_networks,
        "resources": client.async_get_network_resources,
        "routers": client.async_get_network_routers,
    }[kind]
    method.side_effect = NetBirdRateLimitError("900")
    coordinator = (
        NetBirdPeerCoordinator(hass, MockConfigEntry(domain=DOMAIN), client)
        if kind == "peers"
        else NetBirdTopologyCoordinator(hass, MockConfigEntry(domain=DOMAIN), client)
    )
    with pytest.raises(UpdateFailed) as caught:
        await coordinator._async_update_data()
    assert caught.value.retry_after == 900


async def test_self_hosted_dns_failure_is_retryable(hass: HomeAssistant) -> None:
    flow = NetBirdConfigFlow()
    flow.hass = hass
    with patch(
        "custom_components.netbird.config_flow.async_validate_https_origin",
        side_effect=NetBirdResolutionError("safe"),
    ):
        deployment, error = await flow._async_prepare_self_hosted(
            {CONF_API_URL: "https://netbird.example"}
        )
    assert deployment is None
    assert error == "cannot_connect"


async def test_self_hosted_non_ascii_ca_is_a_form_error(hass: HomeAssistant) -> None:
    flow = NetBirdConfigFlow()
    flow.hass = hass
    with patch(
        "custom_components.netbird.config_flow.async_validate_https_origin",
        return_value="https://netbird.example",
    ):
        deployment, error = await flow._async_prepare_self_hosted(
            {CONF_API_URL: "https://netbird.example", CONF_CA_CERTIFICATE: "сертифікат"}
        )
    assert deployment is None
    assert error == "invalid_ca"
