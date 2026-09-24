"""Shared identity and lookup helpers for NetBird topology entities."""

from __future__ import annotations

from typing import override

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
        account_id = entry.runtime_data.account_id
        self._attr_unique_id = f"{account_id}:network:{network_id}:{key}"
        self._attr_extra_state_attributes = {"netbird_key": key}
        item = self.network_topology
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{account_id}:network:{network_id}")},
            manufacturer="NetBird",
            name=item.network.name if item is not None else network_id,
            via_device_id=via_device_id,
            configuration_url=build_dashboard_url("network", network_id=network_id),
        )

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
        account_id = entry.runtime_data.account_id
        prefix = f"{account_id}:network:{network_id}"
        self._attr_unique_id = f"{prefix}:resource:{resource.id}:{key}"
        self._attr_extra_state_attributes = {"netbird_key": key}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{prefix}:resource:{resource.id}")},
            manufacturer="NetBird",
            name=resource.name,
            via_device_id=via_device_id,
            configuration_url=build_dashboard_url(
                "resource", network_id=network_id, resource_id=resource.id
            ),
        )

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

    @property
    @override
    def available(self) -> bool:
        return super().available and self.resource is not None
