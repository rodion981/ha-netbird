"""Tests for the NetBird integration foundation."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.loader import async_get_integration
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird import (
    NetBirdRuntimeData,
    async_setup_entry,
)
from custom_components.netbird.const import (
    CONF_ACCOUNT_ID,
    CONF_API_TOKEN,
    DOMAIN,
    SENSITIVE_CONFIG_KEYS,
)
from custom_components.netbird.models import NetBirdAccount, NetBirdPeer

INTEGRATION_DIR = Path(__file__).parents[1] / "custom_components" / DOMAIN
REPOSITORY_ROOT = Path(__file__).parents[1]


def assert_entry_state(entry: ConfigEntry[Any], expected: ConfigEntryState) -> None:
    """Assert a config entry state without leaking type narrowing across awaits."""
    assert entry.state is expected


async def test_integration_manifest_is_discoverable(hass: HomeAssistant) -> None:
    """Test Home Assistant discovers the custom integration manifest."""
    integration = await async_get_integration(hass, DOMAIN)

    assert integration.domain == DOMAIN
    assert integration.name == "NetBird"


async def test_config_entry_setup_reload_and_unload(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Test the foundation supports the config entry lifecycle without I/O."""
    secret = "test-pat-must-not-be-logged"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: "account-test-id", CONF_API_TOKEN: secret},
        unique_id="account-test-id",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.netbird.NetBirdApiClient") as client_class:
        client = client_class.return_value
        client.async_get_account = AsyncMock(
            return_value=NetBirdAccount(id="account-test-id")
        )
        client.async_get_peers = AsyncMock(return_value=(NetBirdPeer(id="peer"),))

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert_entry_state(entry, ConfigEntryState.LOADED)
        assert isinstance(entry.runtime_data, NetBirdRuntimeData)
        assert entry.runtime_data.account_id == "account-test-id"
        assert entry.runtime_data.coordinator.data == (NetBirdPeer(id="peer"),)
        assert secret not in caplog.text

        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert_entry_state(entry, ConfigEntryState.LOADED)
        assert entry.runtime_data.account_id == "account-test-id"

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert_entry_state(entry, ConfigEntryState.NOT_LOADED)
    assert secret not in caplog.text


async def test_setup_entry_handles_invalid_account_identifier(
    hass: HomeAssistant,
) -> None:
    """Test invalid foundation data does not escape the typed runtime contract."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNT_ID: 1234},
    )

    with pytest.raises(ConfigEntryError, match="identity is missing"):
        await async_setup_entry(hass, entry)


def test_manifest_and_translation_baseline() -> None:
    """Test manifest metadata and translations are valid JSON and aligned."""
    manifest = json.loads(
        (INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    strings = json.loads((INTEGRATION_DIR / "strings.json").read_text(encoding="utf-8"))

    assert manifest["domain"] == DOMAIN
    assert manifest["iot_class"] == "cloud_polling"
    assert manifest["integration_type"] == "hub"
    assert manifest["config_flow"] is True

    for language in ("en", "uk"):
        translation = json.loads(
            (INTEGRATION_DIR / "translations" / f"{language}.json").read_text(
                encoding="utf-8"
            )
        )
        if language == "en":
            assert translation == strings
        else:
            assert translation.keys() == strings.keys()
            assert translation["config"].keys() == strings["config"].keys()
            assert translation["exceptions"].keys() == strings["exceptions"].keys()
            for key in strings["exceptions"]:
                assert translation["exceptions"][key]["message"]


def test_hacs_metadata() -> None:
    """Test the planned HACS distribution metadata is minimal and valid."""
    hacs = json.loads((REPOSITORY_ROOT / "hacs.json").read_text(encoding="utf-8"))

    assert hacs == {"name": "NetBird", "render_readme": True}


def test_fixture_convention(
    load_netbird_fixture: Callable[[str], Any],
) -> None:
    """Test fixture loader and documented NetBird response shapes."""
    accounts = load_netbird_fixture("accounts.json")
    peers = load_netbird_fixture("peers.json")

    assert accounts[0]["id"] == "account-test-id"
    assert peers[0]["id"] == "peer-test-id"
    assert peers[0]["connected"] is True


def test_sensitive_configuration_boundary() -> None:
    """Test sensitive configuration keys stay explicit and out of resources."""
    assert frozenset({CONF_API_TOKEN}) == SENSITIVE_CONFIG_KEYS

    resource_files = [
        REPOSITORY_ROOT / "hacs.json",
        INTEGRATION_DIR / "manifest.json",
        *sorted((Path(__file__).parent / "fixtures").glob("*.json")),
    ]
    for resource_file in resource_files:
        content = resource_file.read_text(encoding="utf-8")
        assert CONF_API_TOKEN not in content
        assert "authorization" not in content.casefold()
