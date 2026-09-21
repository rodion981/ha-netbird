"""Home Assistant runtime tests for coordinated NetBird peer refresh."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird import NetBirdRuntimeData, async_setup_entry
from custom_components.netbird.api import (
    NetBirdAuthenticationError,
    NetBirdJsonError,
    NetBirdPermissionError,
    NetBirdRateLimitError,
    NetBirdSchemaError,
    NetBirdServerError,
    NetBirdTimeoutError,
    NetBirdTransportError,
)
from custom_components.netbird.const import (
    CONF_ACCOUNT_ID,
    CONF_API_TOKEN,
    DOMAIN,
    PEER_UPDATE_INTERVAL_SECONDS,
)
from custom_components.netbird.coordinator import (
    NetBirdPeerCoordinator,
    NetBirdRefreshError,
)
from custom_components.netbird.models import NetBirdAccount, NetBirdPeer

ACCOUNT_ID = "account-test-id"
TOKEN = "test-secret-pat-never-log"
PEERS = (NetBirdPeer(id="peer-1", connected=False),)


def _entry() -> MockConfigEntry:
    """Create a valid ConfigEntry without production credentials."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: ACCOUNT_ID, CONF_API_TOKEN: TOKEN},
        unique_id=ACCOUNT_ID,
    )


async def _setup(
    hass: HomeAssistant,
    *,
    account_result: NetBirdAccount | Exception | None = None,
    peer_result: tuple[NetBirdPeer, ...] | Exception | None = None,
) -> tuple[MockConfigEntry, Any]:
    """Set up a real HA entry while substituting only the Cloud boundary."""
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.netbird.NetBirdApiClient") as client_class:
        client = client_class.return_value
        client.async_get_account = AsyncMock(
            side_effect=account_result
            if isinstance(account_result, Exception)
            else None,
            return_value=account_result
            if isinstance(account_result, NetBirdAccount)
            else NetBirdAccount(id=ACCOUNT_ID),
        )
        client.async_get_peers = AsyncMock(
            side_effect=peer_result if isinstance(peer_result, Exception) else None,
            return_value=peer_result if isinstance(peer_result, tuple) else PEERS,
        )
        await hass.config_entries.async_setup(entry.entry_id)
    return entry, client


async def test_setup_uses_one_peer_request_and_typed_runtime(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Test first refresh, shared snapshot, and fixed coordinator contract."""
    entry, client = await _setup(hass)

    assert entry.state is ConfigEntryState.LOADED
    runtime = entry.runtime_data
    assert isinstance(runtime, NetBirdRuntimeData)
    assert id(runtime.client) == id(client)
    assert runtime.account == NetBirdAccount(id=ACCOUNT_ID)
    assert runtime.coordinator.data == PEERS
    assert runtime.coordinator.last_update_success
    assert runtime.coordinator.update_interval == timedelta(
        seconds=PEER_UPDATE_INTERVAL_SECONDS
    )
    assert runtime.coordinator.always_update is False
    client.async_get_account.assert_awaited_once_with()
    client.async_get_peers.assert_awaited_once_with()
    assert TOKEN not in caplog.text

    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    ("failure", "expected_state"),
    [
        (NetBirdAuthenticationError("safe"), ConfigEntryState.SETUP_ERROR),
        (NetBirdPermissionError("safe"), ConfigEntryState.SETUP_RETRY),
        (NetBirdRateLimitError("30"), ConfigEntryState.SETUP_RETRY),
        (NetBirdTimeoutError("safe"), ConfigEntryState.SETUP_RETRY),
        (NetBirdTransportError("safe"), ConfigEntryState.SETUP_RETRY),
        (NetBirdServerError(503), ConfigEntryState.SETUP_RETRY),
        (NetBirdJsonError("safe"), ConfigEntryState.SETUP_RETRY),
        (NetBirdSchemaError("safe"), ConfigEntryState.SETUP_RETRY),
        (RuntimeError(TOKEN), ConfigEntryState.SETUP_RETRY),
    ],
)
@pytest.mark.parametrize("phase", ["account", "peers"])
async def test_initial_failure_never_loads_partial_entry(
    hass: HomeAssistant,
    caplog: Any,
    failure: Exception,
    expected_state: ConfigEntryState,
    phase: str,
) -> None:
    """Test setup failures by class before any platform could be forwarded."""
    entry, client = await _setup(
        hass,
        account_result=failure if phase == "account" else None,
        peer_result=failure if phase == "peers" else None,
    )

    assert entry.state is expected_state
    assert not hasattr(entry, "runtime_data")
    if phase == "account":
        client.async_get_peers.assert_not_awaited()
    else:
        client.async_get_peers.assert_awaited_once_with()
    assert TOKEN not in caplog.text

    await hass.config_entries.async_unload(entry.entry_id)


async def test_mismatched_account_rejects_setup_before_peers(
    hass: HomeAssistant,
) -> None:
    """Test existing entries cannot silently migrate account identity."""
    entry, client = await _setup(
        hass, account_result=NetBirdAccount(id="different-account")
    )

    assert entry.state is ConfigEntryState.SETUP_ERROR
    client.async_get_peers.assert_not_awaited()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_missing_token_is_auth_failure(hass: HomeAssistant) -> None:
    """Test invalid stored credentials never instantiate an API client."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ACCOUNT_ID: ACCOUNT_ID}, unique_id=ACCOUNT_ID
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await async_setup_entry(hass, entry)


async def test_invalid_stored_account_is_permanent_failure(hass: HomeAssistant) -> None:
    """Test inconsistent entry data cannot be treated as a transient outage."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: "different-account", CONF_API_TOKEN: TOKEN},
        unique_id=ACCOUNT_ID,
    )
    with pytest.raises(ConfigEntryError, match="does not match"):
        await async_setup_entry(hass, entry)


async def test_transient_failure_retains_snapshot_and_recovers(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Test failed refresh changes availability, not authoritative data."""
    entry, client = await _setup(hass)
    coordinator = entry.runtime_data.coordinator
    updates: list[bool] = []
    unsubscribe = coordinator.async_add_listener(
        lambda: updates.append(coordinator.last_update_success)
    )

    client.async_get_peers.side_effect = NetBirdSchemaError("invalid peer id")
    await coordinator.async_refresh()
    failed = coordinator.last_update_success
    assert not failed
    snapshot_before = coordinator.data
    assert snapshot_before == PEERS
    assert updates == [False]

    client.async_get_peers.side_effect = None
    client.async_get_peers.return_value = (NetBirdPeer(id="peer-1", connected=True),)
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data == (NetBirdPeer(id="peer-1", connected=True),)
    assert updates == [False, True]
    assert client.async_get_peers.await_count == 3
    assert TOKEN not in caplog.text
    unsubscribe()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_runtime_401_starts_reauth_but_403_does_not(
    hass: HomeAssistant,
) -> None:
    """Test auth failure semantics on a running coordinator."""
    entry, client = await _setup(hass)
    coordinator = entry.runtime_data.coordinator
    with patch.object(entry, "async_start_reauth_if_available") as start_reauth:
        client.async_get_peers.side_effect = NetBirdPermissionError("safe")
        await coordinator.async_refresh()
        assert coordinator.last_update_success is False
        start_reauth.assert_not_called()

        client.async_get_peers.side_effect = NetBirdAuthenticationError("safe")
        await coordinator.async_refresh()
        start_reauth.assert_called_once_with(hass)

    assert coordinator.data == PEERS
    await hass.config_entries.async_unload(entry.entry_id)


async def test_unexpected_runtime_failure_is_secret_safe(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Test unexpected client errors cannot expose an embedded secret in logs."""
    entry, client = await _setup(hass)
    coordinator = entry.runtime_data.coordinator
    client.async_get_peers.side_effect = RuntimeError(TOKEN)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert coordinator.data == PEERS
    assert isinstance(coordinator.last_exception, NetBirdRefreshError)
    assert coordinator.last_exception.translation_key == "unknown"
    assert TOKEN not in caplog.text
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reload_and_unload_shut_down_old_coordinator(
    hass: HomeAssistant,
) -> None:
    """Test no stale callbacks or owned timers survive reload/unload."""
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.netbird.NetBirdApiClient") as client_class:
        client = client_class.return_value
        client.async_get_account = AsyncMock(return_value=NetBirdAccount(id=ACCOUNT_ID))
        client.async_get_peers = AsyncMock(return_value=PEERS)

        assert await hass.config_entries.async_setup(entry.entry_id)
        old = entry.runtime_data.coordinator
        removed = Mock()
        old.async_add_listener(removed)
        assert await hass.config_entries.async_reload(entry.entry_id)
        assert old._shutdown_requested
        assert old._unsub_refresh is None
        assert entry.runtime_data.coordinator is not old
        assert client.async_get_peers.await_count == 2

        new = entry.runtime_data.coordinator
        new.async_add_listener(removed)
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert new._shutdown_requested
        assert new._unsub_refresh is None


async def test_cancellation_is_not_masked(hass: HomeAssistant) -> None:
    """Test an in-flight peer request remains cancellable."""
    entry, client = await _setup(hass)
    coordinator: NetBirdPeerCoordinator = entry.runtime_data.coordinator
    client.async_get_peers.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await coordinator._async_update_data()

    await hass.config_entries.async_unload(entry.entry_id)
