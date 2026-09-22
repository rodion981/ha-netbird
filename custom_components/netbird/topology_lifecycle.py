"""Conservative cleanup for stale NetBird network and resource devices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, STALE_PEER_SNAPSHOT_THRESHOLD
from .topology import NetBirdTopologySnapshot

if TYPE_CHECKING:
    from . import NetBirdConfigEntry


class NetBirdTopologyLifecycle:
    """Count complete successful absences before deleting owned registry data."""

    def __init__(self, hass: HomeAssistant, entry: NetBirdConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = entry.runtime_data.topology_coordinator
        self._account_id = entry.runtime_data.account_id
        snapshot = self._coordinator.data
        self._known_network_ids = (
            {item.network.id for item in snapshot.networks}
            if snapshot is not None
            else set()
        )
        self._known_resources = (
            {
                (item.network.id, resource.id)
                for item in snapshot.networks
                for resource in (item.resources or ())
            }
            if snapshot is not None
            else set()
        )
        self._network_missing: dict[str, int] = {}
        self._resource_missing: dict[tuple[str, str], int] = {}

    @callback
    def async_start(self) -> None:
        self._entry.async_on_unload(
            self._coordinator.async_add_successful_refresh_listener(self._handle)
        )

    @callback
    def _handle(self, snapshot: NetBirdTopologySnapshot) -> None:
        present_networks = {item.network.id for item in snapshot.networks}
        for item in snapshot.networks:
            network_id = item.network.id
            self._network_missing.pop(network_id, None)
            if item.resources is None:
                continue
            present_resources = {
                (network_id, resource.id) for resource in item.resources
            }
            for identity in present_resources:
                self._resource_missing.pop(identity, None)
            self._known_resources.update(present_resources)
            for identity in self._known_resources - present_resources:
                if identity[0] != network_id:
                    continue
                count = min(
                    self._resource_missing.get(identity, 0) + 1,
                    STALE_PEER_SNAPSHOT_THRESHOLD,
                )
                self._resource_missing[identity] = count
                if count == STALE_PEER_SNAPSHOT_THRESHOLD and self._cleanup_resource(
                    *identity
                ):
                    self._known_resources.discard(identity)

        self._known_network_ids.update(present_networks)
        for network_id in self._known_network_ids - present_networks:
            count = min(
                self._network_missing.get(network_id, 0) + 1,
                STALE_PEER_SNAPSHOT_THRESHOLD,
            )
            self._network_missing[network_id] = count
            if count == STALE_PEER_SNAPSHOT_THRESHOLD:
                for identity in tuple(self._known_resources):
                    if identity[0] == network_id and self._cleanup_resource(*identity):
                        self._known_resources.discard(identity)
                if self._cleanup_network(network_id):
                    self._known_network_ids.discard(network_id)

    def _cleanup_resource(self, network_id: str, resource_id: str) -> bool:
        prefix = f"{self._account_id}:network:{network_id}:resource:{resource_id}"
        return self._cleanup_device(prefix)

    def _cleanup_network(self, network_id: str) -> bool:
        prefix = f"{self._account_id}:network:{network_id}"
        device_registry = dr.async_get(self._hass)
        if any(
            domain == DOMAIN and identifier.startswith(f"{prefix}:resource:")
            for device in device_registry.devices
            for domain, identifier in device.identifiers
        ):
            return False
        return self._cleanup_device(prefix)

    def _cleanup_device(self, identifier: str) -> bool:
        entity_registry = er.async_get(self._hass)
        device_registry = dr.async_get(self._hass)
        device = device_registry.async_get_device_by_identifier(
            (DOMAIN, identifier), self._entry.entry_id
        )
        owned = [
            entity
            for entity in er.async_entries_for_config_entry(
                entity_registry, self._entry.entry_id
            )
            if entity.platform == DOMAIN
            and entity.unique_id.startswith(f"{identifier}:")
        ]
        if device is not None:
            linked = {
                entity.entity_id
                for entity in entity_registry.entities.values()
                if entity.device_id == device.id
            }
            if linked != {entity.entity_id for entity in owned}:
                return False
        for entity in owned:
            entity_registry.async_remove(entity.entity_id)
        if device is not None:
            device_registry.async_remove_device(device.id)
        return True


@callback
def async_setup_topology_lifecycle(
    hass: HomeAssistant, entry: NetBirdConfigEntry
) -> None:
    lifecycle = NetBirdTopologyLifecycle(hass, entry)
    lifecycle.async_start()
