"""Shared identity and lookup helpers for NetBird topology entities."""

from __future__ import annotations

from typing import override

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NetBirdConfigEntry
from .const import DOMAIN
from .dashboard_urls import build_dashboard_url
from .models import NetBirdResource
from .topology import NetBirdNetworkTopology, NetBirdTopologyCoordinator


class NetBirdNetworkEntity(CoordinatorEntity[NetBirdTopologyCoordinator]):
    """Base for one stable network entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: NetBirdConfigEntry,
        network_id: str,
        key: str,
        via_device_id: str,
    ) -> None:
        super().__init__(entry.runtime_data.topology_coordinator)
        self._network_id = network_id
        self._netbird_key = key
        account_id = entry.runtime_data.account_id
        self._attr_unique_id = f"{account_id}:network:{network_id}:{key}"
        item = self.network_topology
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{account_id}:network:{network_id}")},
            manufacturer="NetBird",
            name=item.network.name if item is not None else network_id,
            via_device_id=via_device_id,
            configuration_url=build_dashboard_url(
                "network",
                base_url=entry.runtime_data.dashboard_url,
                network_id=network_id,
            ),
        )

    @property
    @override
    def capability_attributes(self) -> dict[str, object]:
        """Keep dashboard discovery metadata while the entity is unavailable."""
        return {
            **(super().capability_attributes or {}),
            "netbird_key": self._netbird_key,
        }

    @property
    def network_topology(self) -> NetBirdNetworkTopology | None:
        snapshot = getattr(self.coordinator, "data", None)
        if snapshot is None:
            return None
        return next(
            (item for item in snapshot.networks if item.network.id == self._network_id),
            None,
        )

    @property
    @override
    def available(self) -> bool:
        return super().available and self.network_topology is not None


class NetBirdResourceEntity(CoordinatorEntity[NetBirdTopologyCoordinator]):
    """Base for one stable network resource entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: NetBirdConfigEntry,
        network_id: str,
        resource: NetBirdResource,
        key: str,
        via_device_id: str,
    ) -> None:
        super().__init__(entry.runtime_data.topology_coordinator)
        self._network_id = network_id
        self._resource_id = resource.id
        self._netbird_key = key
        account_id = entry.runtime_data.account_id
        prefix = f"{account_id}:network:{network_id}"
        self._attr_unique_id = f"{prefix}:resource:{resource.id}:{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{prefix}:resource:{resource.id}")},
            manufacturer="NetBird",
            name=resource.name,
            via_device_id=via_device_id,
            configuration_url=build_dashboard_url(
                "resource",
                base_url=entry.runtime_data.dashboard_url,
                network_id=network_id,
                resource_id=resource.id,
            ),
        )

    @property
    @override
    def capability_attributes(self) -> dict[str, object]:
        """Keep dashboard discovery metadata while the entity is unavailable."""
        return {
            **(super().capability_attributes or {}),
            "netbird_key": self._netbird_key,
        }

    @property
    def resource(self) -> NetBirdResource | None:
        snapshot = getattr(self.coordinator, "data", None)
        if snapshot is None:
            return None
        network = next(
            (item for item in snapshot.networks if item.network.id == self._network_id),
            None,
        )
        if network is None or network.resources is None:
            return None
        return next(
            (item for item in network.resources if item.id == self._resource_id), None
        )

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Refresh resource names while preserving user overrides and identity."""
        resource = self.resource
        if (
            self.coordinator.last_update_success
            and resource is not None
            and self.device_entry
        ):
            registry = dr.async_get(self.hass)
            device = registry.async_get(self.device_entry.id)
            if device is not None and device.name != resource.name:
                registry.async_update_device(device.id, name=resource.name)
        super()._handle_coordinator_update()

    @property
    @override
    def available(self) -> bool:
        return super().available and self.resource is not None
