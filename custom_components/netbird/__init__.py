"""The NetBird integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import (
    NetBirdApiClient,
    NetBirdAuthenticationError,
    NetBirdDataError,
    NetBirdPermissionError,
    NetBirdUpdateError,
)
from .const import CONF_ACCOUNT_ID, CONF_API_TOKEN, DOMAIN
from .coordinator import NetBirdPeerCoordinator
from .models import NetBirdAccount

PLATFORMS = (Platform.BINARY_SENSOR, Platform.SENSOR)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(frozen=True, slots=True)
class NetBirdRuntimeData:
    """Runtime data owned by a NetBird config entry."""

    client: NetBirdApiClient
    coordinator: NetBirdPeerCoordinator
    account: NetBirdAccount

    @property
    def account_id(self) -> str:
        """Return the stable account identity for future platforms."""
        return self.account.id


type NetBirdConfigEntry = ConfigEntry[NetBirdRuntimeData]


async def async_setup(_hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the NetBird integration package."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NetBirdConfigEntry) -> bool:
    """Validate account identity and load the first authoritative peer snapshot."""
    account_id = entry.unique_id
    token = entry.data.get(CONF_API_TOKEN)
    if not isinstance(account_id, str) or not account_id.strip():
        raise ConfigEntryError("NetBird account identity is missing")
    if entry.data.get(CONF_ACCOUNT_ID) != account_id:
        raise ConfigEntryError("NetBird account identity does not match")
    if not isinstance(token, str) or not token:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        )

    client = NetBirdApiClient(async_get_clientsession(hass), token)
    try:
        account = await client.async_get_account()
    except NetBirdAuthenticationError:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from None
    except NetBirdPermissionError:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="insufficient_permissions"
        ) from None
    except NetBirdDataError:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="invalid_response"
        ) from None
    except NetBirdUpdateError:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from None
    except Exception:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="unknown"
        ) from None

    if account.id != account_id:
        raise ConfigEntryError("NetBird account identity changed")

    coordinator = NetBirdPeerCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = NetBirdRuntimeData(
        client=client, coordinator=coordinator, account=account
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NetBirdConfigEntry) -> bool:
    """Unload platforms and their coordinator listeners."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
