"""NetBird peer diagnostic sensors."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NetBirdConfigEntry
from .const import DOMAIN
from .coordinator import NetBirdPeerCoordinator
from .dashboard_urls import build_dashboard_url
from .entity import NetBirdPeerEntity
from .models import NetBirdPeer, NetBirdResource
from .topology import NetBirdTopologyCoordinator
from .topology_entity import NetBirdNetworkEntity, NetBirdResourceEntity

PARALLEL_UPDATES = 0

PEER_DESCRIPTIONS = (
    SensorEntityDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="ip_address",
        translation_key="ip_address",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="accessible_peers",
        translation_key="accessible_peers",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_login",
        translation_key="last_login",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="ipv6_address",
        translation_key="ipv6_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="hostname",
        translation_key="hostname",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="dns_label",
        translation_key="dns_label",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="operating_system",
        translation_key="operating_system",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)

SENSOR_VALUE_GETTERS: dict[str, Callable[[NetBirdPeer], StateType | datetime]] = {
    "last_seen": lambda peer: peer.last_seen,
    "ip_address": lambda peer: peer.ip,
    "accessible_peers": lambda peer: peer.accessible_peers_count,
    "last_login": lambda peer: peer.last_login,
    "ipv6_address": lambda peer: peer.ipv6,
    "hostname": lambda peer: peer.hostname,
    "dns_label": lambda peer: peer.dns_label,
    "operating_system": lambda peer: peer.os,
}

OPTIONAL_SENSOR_KEYS = frozenset(
    {"ipv6_address", "hostname", "dns_label", "operating_system"}
)

ACCOUNT_DESCRIPTIONS = (
    SensorEntityDescription(key="peer_count", translation_key="peer_count"),
    SensorEntityDescription(
        key="connected_peer_count", translation_key="connected_peer_count"
    ),
)

ACCOUNT_TOPOLOGY_DESCRIPTIONS = (
    SensorEntityDescription(key="network_count", translation_key="network_count"),
    SensorEntityDescription(key="resource_count", translation_key="resource_count"),
    SensorEntityDescription(
        key="enabled_resource_count", translation_key="enabled_resource_count"
    ),
    SensorEntityDescription(key="router_count", translation_key="router_count"),
    SensorEntityDescription(
        key="enabled_router_count", translation_key="enabled_router_count"
    ),
)

NETWORK_DESCRIPTIONS = (
    SensorEntityDescription(key="resource_count", translation_key="resource_count"),
    SensorEntityDescription(
        key="enabled_resource_count", translation_key="enabled_resource_count"
    ),
    SensorEntityDescription(key="router_count", translation_key="router_count"),
    SensorEntityDescription(
        key="enabled_router_count", translation_key="enabled_router_count"
    ),
    SensorEntityDescription(
        key="connected_routing_peers", translation_key="connected_routing_peers"
    ),
)

RESOURCE_SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(key="address", translation_key="resource_address"),
    SensorEntityDescription(key="resource_type", translation_key="resource_type"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NetBirdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create account counts and diagnostics for newly discovered peers."""
    coordinator = entry.runtime_data.coordinator
    known_entities: set[tuple[str, str]] = set()
    async_add_entities(
        NetBirdAccountSensor(entry, description) for description in ACCOUNT_DESCRIPTIONS
    )
    async_add_entities(
        NetBirdAccountTopologySensor(entry, description)
        for description in ACCOUNT_TOPOLOGY_DESCRIPTIONS
    )

    def add_new_peer_entities() -> None:
        """Add one diagnostic entity for each peer in a successful snapshot."""
        if not coordinator.last_update_success:
            return

        registry = er.async_get(hass)
        account_id = entry.runtime_data.account_id
        known_entities.intersection_update(
            identity
            for identity in known_entities
            if registry.async_get_entity_id(
                "sensor", DOMAIN, f"{account_id}:{identity[0]}:{identity[1]}"
            )
            is not None
        )

        entities: list[NetBirdPeerSensor] = []
        for peer in coordinator.data:
            for description in PEER_DESCRIPTIONS:
                identity = (peer.id, description.key)
                if identity in known_entities or (
                    description.key in OPTIONAL_SENSOR_KEYS
                    and SENSOR_VALUE_GETTERS[description.key](peer) is None
                ):
                    continue
                known_entities.add(identity)
                entities.append(NetBirdPeerSensor(entry, peer, description))
        if entities:
            async_add_entities(entities)

    add_new_peer_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_new_peer_entities))

    topology = entry.runtime_data.topology_coordinator
    known_topology_entities: set[str] = set()
    device_registry = dr.async_get(hass)
    account_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.runtime_data.account_id)},
        manufacturer="NetBird",
        name="NetBird account",
    )

    def add_new_topology_entities() -> None:
        if not topology.last_update_success or topology.data is None:
            return
        registry = er.async_get(hass)
        known_topology_entities.intersection_update(
            unique_id
            for unique_id in known_topology_entities
            if registry.async_get_entity_id("sensor", DOMAIN, unique_id) is not None
        )
        entities: list[SensorEntity] = []
        for item in topology.data.networks:
            network_device = device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={
                    (
                        DOMAIN,
                        f"{entry.runtime_data.account_id}:network:{item.network.id}",
                    )
                },
                manufacturer="NetBird",
                name=item.network.name,
                via_device_id=account_device.id,
            )
            for description in NETWORK_DESCRIPTIONS:
                unique_id = (
                    f"{entry.runtime_data.account_id}:network:{item.network.id}:"
                    f"{description.key}"
                )
                if unique_id not in known_topology_entities:
                    known_topology_entities.add(unique_id)
                    entities.append(
                        NetBirdNetworkSensor(
                            entry, item.network.id, description, account_device.id
                        )
                    )
            if item.resources is None:
                continue
            for resource in item.resources:
                for description in RESOURCE_SENSOR_DESCRIPTIONS:
                    unique_id = (
                        f"{entry.runtime_data.account_id}:network:{item.network.id}:"
                        f"resource:{resource.id}:{description.key}"
                    )
                    if unique_id not in known_topology_entities:
                        known_topology_entities.add(unique_id)
                        entities.append(
                            NetBirdResourceSensor(
                                entry,
                                item.network.id,
                                resource,
                                description,
                                network_device.id,
                            )
                        )
        if entities:
            async_add_entities(entities)

    add_new_topology_entities()
    entry.async_on_unload(topology.async_add_listener(add_new_topology_entities))


class NetBirdAccountSensor(CoordinatorEntity[NetBirdPeerCoordinator], SensorEntity):
    """An account count computed solely from the shared peer snapshot."""

    _attr_has_entity_name = True
    entity_description: SensorEntityDescription

    def __init__(
        self, entry: NetBirdConfigEntry, description: SensorEntityDescription
    ) -> None:
        """Bind one stable account-level entity to the coordinator."""
        super().__init__(entry.runtime_data.coordinator)
        self.entity_description = description
        account_id = entry.runtime_data.account_id
        self._attr_unique_id = f"{account_id}:{description.key}"
        self._attr_extra_state_attributes = {"netbird_key": description.key}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_id)},
            manufacturer="NetBird",
            name="NetBird account",
            configuration_url=build_dashboard_url("account"),
        )

    @property
    @override
    def native_value(self) -> int:
        """Return zero for an empty authoritative snapshot."""
        if self.entity_description.key == "peer_count":
            return len(self.coordinator.data)
        return sum(peer.connected is True for peer in self.coordinator.data)


class NetBirdAccountTopologySensor(
    CoordinatorEntity[NetBirdTopologyCoordinator], SensorEntity
):
    """An aggregate computed from the isolated topology snapshot."""

    _attr_has_entity_name = True
    entity_description: SensorEntityDescription

    def __init__(
        self, entry: NetBirdConfigEntry, description: SensorEntityDescription
    ) -> None:
        super().__init__(entry.runtime_data.topology_coordinator)
        self.entity_description = description
        account_id = entry.runtime_data.account_id
        self._attr_unique_id = f"{account_id}:{description.key}"
        self._attr_extra_state_attributes = {"netbird_key": description.key}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_id)},
            manufacturer="NetBird",
            name="NetBird account",
            configuration_url=build_dashboard_url("account"),
        )

    @property
    @override
    def available(self) -> bool:
        if not super().available or self.coordinator.data is None:
            return False
        key = self.entity_description.key
        if "resource" in key:
            return all(
                item.resources is not None for item in self.coordinator.data.networks
            )
        if "router" in key:
            return all(
                item.routers is not None for item in self.coordinator.data.networks
            )
        return True

    @property
    @override
    def native_value(self) -> int:
        snapshot = self.coordinator.data
        if self.entity_description.key == "network_count":
            return len(snapshot.networks)
        if "resource" in self.entity_description.key:
            resources = tuple(
                resource
                for item in snapshot.networks
                for resource in (item.resources or ())
            )
            return (
                sum(resource.enabled for resource in resources)
                if self.entity_description.key == "enabled_resource_count"
                else len(resources)
            )
        routers = tuple(
            router for item in snapshot.networks for router in (item.routers or ())
        )
        return (
            sum(router.enabled for router in routers)
            if self.entity_description.key == "enabled_router_count"
            else len(routers)
        )


class NetBirdNetworkSensor(NetBirdNetworkEntity, SensorEntity):
    """A network-level resource or router summary."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: NetBirdConfigEntry,
        network_id: str,
        description: SensorEntityDescription,
        via_device_id: str,
    ) -> None:
        super().__init__(entry, network_id, description.key, via_device_id)
        self.entity_description = description
        self._peer_coordinator = entry.runtime_data.coordinator

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.entity_description.key == "connected_routing_peers":
            self.async_on_remove(
                self._peer_coordinator.async_add_listener(self.async_write_ha_state)
            )

    @property
    @override
    def available(self) -> bool:
        if not super().available:
            return False
        item = self.network_topology
        key = self.entity_description.key
        if "resource" in key:
            return item is not None and item.resources is not None
        if item is None or item.routers is None:
            return False
        return (
            key != "connected_routing_peers"
            or self._peer_coordinator.last_update_success
        )

    @property
    @override
    def native_value(self) -> int:
        item = self.network_topology
        assert item is not None
        key = self.entity_description.key
        if "resource" in key:
            values = item.resources or ()
            return (
                sum(value.enabled for value in values)
                if key.startswith("enabled")
                else len(values)
            )
        routers = item.routers or ()
        if key == "connected_routing_peers":
            connected = {
                peer.id for peer in self._peer_coordinator.data if peer.connected
            }
            return len(
                {
                    router.peer_id
                    for router in routers
                    if router.enabled and router.peer_id in connected
                }
            )
        return (
            sum(router.enabled for router in routers)
            if key.startswith("enabled")
            else len(routers)
        )


class NetBirdResourceSensor(NetBirdResourceEntity, SensorEntity):
    """An address or type state for one network resource."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: NetBirdConfigEntry,
        network_id: str,
        resource: NetBirdResource,
        description: SensorEntityDescription,
        via_device_id: str,
    ) -> None:
        super().__init__(entry, network_id, resource, description.key, via_device_id)
        self.entity_description = description

    @property
    @override
    def native_value(self) -> str | None:
        resource = self.resource
        if resource is None:
            return None
        return (
            resource.address
            if self.entity_description.key == "address"
            else resource.type
        )


class NetBirdPeerSensor(NetBirdPeerEntity, SensorEntity):
    """An approved diagnostic value from the shared peer snapshot."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: NetBirdConfigEntry,
        peer: NetBirdPeer,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize with a stable peer identity and description."""
        super().__init__(entry, peer, description.key)
        self.entity_description = description

    @property
    @override
    def native_value(self) -> StateType | datetime:
        """Return the selected value and reject naive timestamps."""
        peer = self.peer
        if peer is None:
            return None
        value = SENSOR_VALUE_GETTERS[self.entity_description.key](peer)
        if isinstance(value, datetime):
            return value.astimezone(UTC) if value.tzinfo else None
        return value
