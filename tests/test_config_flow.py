"""Tests for the NetBird UI config flow and reauthentication."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.api import (
    NetBirdAuthenticationError,
    NetBirdJsonError,
    NetBirdPermissionError,
    NetBirdSchemaError,
    NetBirdServerError,
    NetBirdTimeoutError,
    NetBirdTransportError,
)
from custom_components.netbird.const import CONF_ACCOUNT_ID, CONF_API_TOKEN, DOMAIN
from custom_components.netbird.models import NetBirdAccount, NetBirdSnapshot

ACCOUNT_ID = "account-test-id"
OLD_TOKEN = "old-test-pat"
NEW_TOKEN = "new-test-pat"


def _snapshot(account_id: str = ACCOUNT_ID) -> NetBirdSnapshot:
    """Return a minimal validated snapshot."""
    return NetBirdSnapshot(account=NetBirdAccount(id=account_id), peers=())


def _mock_client_result(result: NetBirdSnapshot | Exception) -> Any:
    """Patch the API client to return or raise one validation result."""
    client_patcher = patch("custom_components.netbird.config_flow.NetBirdApiClient")
    client_class = client_patcher.start()
    if isinstance(result, Exception):
        client_class.return_value.async_get_snapshot = AsyncMock(side_effect=result)
    else:
        client_class.return_value.async_get_snapshot = AsyncMock(return_value=result)
    return client_patcher, client_class


async def test_user_form_uses_password_selector(hass: HomeAssistant) -> None:
    """Test PAT input is rendered with password semantics."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["data_schema"] is not None
    schema_values = list(result["data_schema"].schema.values())
    assert len(schema_values) == 1
    assert schema_values[0].config["type"] == "password"


async def test_user_success_creates_account_bound_entry(
    hass: HomeAssistant,
) -> None:
    """Test a valid PAT creates one minimal account-bound entry."""
    client_patcher, client_class = _mock_client_result(_snapshot())
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_API_TOKEN: NEW_TOKEN},
        )
    finally:
        client_patcher.stop()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "NetBird Cloud"
    assert result["data"] == {
        CONF_ACCOUNT_ID: ACCOUNT_ID,
        CONF_API_TOKEN: NEW_TOKEN,
    }
    assert result["result"].unique_id == ACCOUNT_ID
    client_class.return_value.async_get_snapshot.assert_awaited_once_with()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_duplicate_account_aborts_with_different_pat(
    hass: HomeAssistant,
) -> None:
    """Test account identity, not the PAT, prevents duplicates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: ACCOUNT_ID, CONF_API_TOKEN: OLD_TOKEN},
        unique_id=ACCOUNT_ID,
    )
    entry.add_to_hass(hass)
    client_patcher, _ = _mock_client_result(_snapshot())
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_API_TOKEN: NEW_TOKEN},
        )
    finally:
        client_patcher.stop()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_API_TOKEN] == OLD_TOKEN
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.parametrize(
    ("failure_factory", "expected_error"),
    [
        (lambda: NetBirdAuthenticationError("safe"), "invalid_auth"),
        (lambda: NetBirdPermissionError("safe"), "insufficient_permissions"),
        (lambda: NetBirdTimeoutError("safe"), "cannot_connect"),
        (lambda: NetBirdTransportError("safe"), "cannot_connect"),
        (lambda: NetBirdServerError(503), "cannot_connect"),
        (lambda: NetBirdJsonError("safe"), "invalid_response"),
        (lambda: NetBirdSchemaError("safe"), "invalid_response"),
        (lambda: RuntimeError(NEW_TOKEN), "unknown"),
    ],
)
async def test_user_errors_are_distinct_and_secret_safe(
    hass: HomeAssistant,
    caplog: Any,
    failure_factory: Callable[[], Exception],
    expected_error: str,
) -> None:
    """Test validation failures remain recoverable, distinct, and secret-safe."""
    client_patcher, _ = _mock_client_result(failure_factory())
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_API_TOKEN: NEW_TOKEN},
        )
    finally:
        client_patcher.stop()

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}
    assert result["description_placeholders"] is None
    assert not hass.config_entries.async_entries(DOMAIN)
    assert NEW_TOKEN not in caplog.text
    assert NEW_TOKEN not in repr(result)


async def test_reauth_updates_same_account_and_schedules_one_reload(
    hass: HomeAssistant,
) -> None:
    """Test a same-account PAT is stored and the entry reloads exactly once."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: ACCOUNT_ID, CONF_API_TOKEN: OLD_TOKEN},
        unique_id=ACCOUNT_ID,
    )
    entry.add_to_hass(hass)
    client_patcher, _ = _mock_client_result(_snapshot())
    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        try:
            start = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
                data=entry.data,
            )
            result = await hass.config_entries.flow.async_configure(
                start["flow_id"], {CONF_API_TOKEN: NEW_TOKEN}
            )
        finally:
            client_patcher.stop()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {
        CONF_ACCOUNT_ID: ACCOUNT_ID,
        CONF_API_TOKEN: NEW_TOKEN,
    }
    schedule_reload.assert_called_once_with(entry.entry_id)


async def test_reauth_rejects_account_mismatch_without_mutation(
    hass: HomeAssistant,
) -> None:
    """Test reauth cannot move an entry to a different account."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: ACCOUNT_ID, CONF_API_TOKEN: OLD_TOKEN},
        unique_id=ACCOUNT_ID,
    )
    entry.add_to_hass(hass)
    client_patcher, _ = _mock_client_result(_snapshot("different-account"))
    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        try:
            start = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
                data=entry.data,
            )
            result = await hass.config_entries.flow.async_configure(
                start["flow_id"], {CONF_API_TOKEN: NEW_TOKEN}
            )
        finally:
            client_patcher.stop()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_account_mismatch"
    assert entry.data[CONF_API_TOKEN] == OLD_TOKEN
    schedule_reload.assert_not_called()


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (NetBirdAuthenticationError("safe"), "invalid_auth"),
        (NetBirdPermissionError("safe"), "insufficient_permissions"),
        (NetBirdTimeoutError("safe"), "cannot_connect"),
        (NetBirdJsonError("safe"), "invalid_response"),
    ],
)
async def test_reauth_failure_preserves_entry_and_does_not_reload(
    hass: HomeAssistant,
    failure: Exception,
    expected_error: str,
) -> None:
    """Test reauth errors keep the old PAT and allow a safe retry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: ACCOUNT_ID, CONF_API_TOKEN: OLD_TOKEN},
        unique_id=ACCOUNT_ID,
    )
    entry.add_to_hass(hass)
    client_patcher, _ = _mock_client_result(failure)
    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        try:
            start = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
                data=entry.data,
            )
            assert start["type"] is FlowResultType.FORM
            assert start["step_id"] == "reauth_confirm"
            assert start["data_schema"] is not None
            assert (
                next(iter(start["data_schema"].schema.values())).config["type"]
                == "password"
            )
            result = await hass.config_entries.flow.async_configure(
                start["flow_id"], {CONF_API_TOKEN: NEW_TOKEN}
            )
        finally:
            client_patcher.stop()

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}
    assert NEW_TOKEN not in repr(result["description_placeholders"])
    assert OLD_TOKEN not in repr(result["description_placeholders"])
    assert entry.data[CONF_API_TOKEN] == OLD_TOKEN
    schedule_reload.assert_not_called()
