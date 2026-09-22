"""Coordinated NetBird Cloud peer refresh."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    NetBirdApiClient,
    NetBirdAuthenticationError,
    NetBirdDataError,
    NetBirdPermissionError,
    NetBirdUpdateError,
)
from .const import DOMAIN, PEER_UPDATE_INTERVAL_SECONDS
from .models import NetBirdPeer

_LOGGER = logging.getLogger(__name__)

_FAILURE_MESSAGES = {
    "insufficient_permissions": "NetBird Cloud permission denied",
    "invalid_response": "NetBird Cloud response is invalid",
    "cannot_connect": "NetBird Cloud connection failed",
    "unknown": "Unexpected NetBird Cloud failure",
}


class NetBirdRefreshError(UpdateFailed):
    """A translated, secret-safe coordinator failure."""

    translation_domain = DOMAIN

    def __init__(self, reason: str) -> None:
        """Initialize with a safe reason, never an API exception message."""
        super().__init__(_FAILURE_MESSAGES[reason])
        self.translation_key = reason


class NetBirdPeerCoordinator(DataUpdateCoordinator[tuple[NetBirdPeer, ...]]):
    """Fetch one authoritative peer list for all consumers of an entry."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: NetBirdApiClient
    ) -> None:
        """Configure one fixed-interval poll per config entry."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=PEER_UPDATE_INTERVAL_SECONDS),
            always_update=False,
        )
        self._client = client
        self.last_successful_refresh: datetime | None = None
        self._successful_refresh_listeners: set[
            Callable[[tuple[NetBirdPeer, ...]], None]
        ] = set()

    @callback
    def async_add_successful_refresh_listener(
        self, update_callback: Callable[[tuple[NetBirdPeer, ...]], None]
    ) -> Callable[[], None]:
        """Listen to every successful snapshot, including unchanged data."""
        self._successful_refresh_listeners.add(update_callback)
        return lambda: self._successful_refresh_listeners.discard(update_callback)

    @callback
    @override
    def _async_refresh_finished(self) -> None:
        """Publish every completed successful snapshot, including unchanged data."""
        if not self.last_update_success:
            return
        for update_callback in self._successful_refresh_listeners:
            update_callback(self.data)

    @override
    async def _async_update_data(self) -> tuple[NetBirdPeer, ...]:
        """Fetch peers and map failures without exposing the API payload."""
        try:
            peers = await self._client.async_get_peers()
        except NetBirdAuthenticationError:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from None
        except NetBirdPermissionError:
            raise NetBirdRefreshError("insufficient_permissions") from None
        except NetBirdDataError:
            raise NetBirdRefreshError("invalid_response") from None
        except NetBirdUpdateError:
            raise NetBirdRefreshError("cannot_connect") from None
        except Exception:
            raise NetBirdRefreshError("unknown") from None
        self.last_successful_refresh = datetime.now(UTC)
        return peers
