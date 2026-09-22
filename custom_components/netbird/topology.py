"""Independent, rate-aware NetBird topology coordination."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
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
from .const import (
    DOMAIN,
    TOPOLOGY_REQUEST_CONCURRENCY,
    TOPOLOGY_UPDATE_INTERVAL_SECONDS,
)
from .models import NetBirdNetwork, NetBirdResource, NetBirdRouter

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NetBirdNetworkTopology:
    """One network and independently available nested sections."""

    network: NetBirdNetwork
    resources: tuple[NetBirdResource, ...] | None
    routers: tuple[NetBirdRouter, ...] | None


@dataclass(frozen=True, slots=True)
class NetBirdTopologySnapshot:
    """Current Networks topology snapshot."""

    networks: tuple[NetBirdNetworkTopology, ...]


class NetBirdTopologyCoordinator(DataUpdateCoordinator[NetBirdTopologySnapshot]):
    """Poll current Networks without affecting peer monitoring."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: NetBirdApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_topology",
            update_interval=timedelta(seconds=TOPOLOGY_UPDATE_INTERVAL_SECONDS),
            always_update=False,
        )
        self._client = client
        self._successful_refresh_listeners: set[
            Callable[[NetBirdTopologySnapshot], None]
        ] = set()

    @callback
    def async_add_successful_refresh_listener(
        self, update_callback: Callable[[NetBirdTopologySnapshot], None]
    ) -> Callable[[], None]:
        """Listen to every successful topology snapshot, including unchanged data."""
        self._successful_refresh_listeners.add(update_callback)
        return lambda: self._successful_refresh_listeners.discard(update_callback)

    @callback
    @override
    def _async_refresh_finished(self) -> None:
        if not self.last_update_success or self.data is None:
            return
        for update_callback in self._successful_refresh_listeners:
            update_callback(self.data)

    @override
    async def _async_update_data(self) -> NetBirdTopologySnapshot:
        try:
            networks = await self._client.async_get_networks()
        except NetBirdAuthenticationError:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from None
        except NetBirdPermissionError as err:
            raise UpdateFailed("NetBird topology permission denied") from err
        except NetBirdDataError as err:
            raise UpdateFailed("NetBird topology response is invalid") from err
        except NetBirdUpdateError as err:
            raise UpdateFailed("NetBird topology connection failed") from err
        except Exception as err:
            raise UpdateFailed("Unexpected NetBird topology failure") from err

        semaphore = asyncio.Semaphore(TOPOLOGY_REQUEST_CONCURRENCY)

        async def resources_for(
            network: NetBirdNetwork,
        ) -> tuple[NetBirdResource, ...] | None:
            async with semaphore:
                try:
                    return await self._client.async_get_network_resources(network.id)
                except NetBirdAuthenticationError:
                    raise
                except NetBirdUpdateError:
                    return None

        async def routers_for(
            network: NetBirdNetwork,
        ) -> tuple[NetBirdRouter, ...] | None:
            async with semaphore:
                try:
                    return await self._client.async_get_network_routers(network.id)
                except NetBirdAuthenticationError:
                    raise
                except NetBirdUpdateError:
                    return None

        try:
            resource_sections, router_sections = await asyncio.gather(
                asyncio.gather(*(resources_for(network) for network in networks)),
                asyncio.gather(*(routers_for(network) for network in networks)),
            )
        except NetBirdAuthenticationError:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from None
        return NetBirdTopologySnapshot(
            networks=tuple(
                NetBirdNetworkTopology(network, resources, routers)
                for network, resources, routers in zip(
                    networks, resource_sections, router_sections, strict=True
                )
            )
        )
