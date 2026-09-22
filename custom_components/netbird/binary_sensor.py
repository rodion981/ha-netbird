"""NetBird peer connectivity and problem binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NetBirdConfigEntry
from .const import DOMAIN
from .entity import NetBirdPeerEntity
from .models import NetBirdPeer, NetBirdResource
from .topology_entity import NetBirdResourceEntity

PARALLEL_UPDATES = 0

DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    BinarySensorEntityDescription(
        key="login_expired",
        translation_key="login_expired",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="approval_required",
        translation_key="approval_required",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="ssh_enabled",
        translation_key="ssh_enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="ephemeral",
        translation_key="ephemeral",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

BINARY_VALUE_GETTERS: dict[str, Callable[[NetBirdPeer], bool | None]] = {
    "connected": lambda peer: peer.connected,
    "login_expired": lambda peer: peer.login_expired,
    "approval_required": lambda peer: peer.approval_required,
    "ssh_enabled": lambda peer: peer.ssh_enabled,
    "ephemeral": lambda peer: peer.ephemeral,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NetBirdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create applicable entities now and when new peers are discovered."""
    coordinator = entry.runtime_data.coordinator
    known_entities: set[tuple[str, str]] = set()

    def add_new_entities() -> None:
        """Add entity descriptions newly supported by a successful snapshot."""
        if not coordinator.last_update_success:
            return

        registry = er.async_get(hass)
        account_id = entry.runtime_data.account_id
        known_entities.intersection_update(
            identity
            for identity in known_entities
            if registry.async_get_entity_id(
                "binary_sensor",
                DOMAIN,
                f"{account_id}:{identity[0]}:{identity[1]}",
            )
            is not None
        )

        entities: list[NetBirdPeerBinarySensor] = []
        for peer in coordinator.data:
            for description in DESCRIPTIONS:
                identity = (peer.id, description.key)
                if identity in known_entities or (
                    description.key == "approval_required"
                    and peer.approval_required is None
                ):
                    continue
                known_entities.add(identity)
                entities.append(NetBirdPeerBinarySensor(entry, peer, description))

        if entities:
            async_add_entities(entities)

    add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_new_entities))

    topology = entry.runtime_data.topology_coordinator
    known_resources: set[str] = set()
    device_registry = dr.async_get(hass)
    account_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.runtime_data.account_id)},
        manufacturer="NetBird",
        name="NetBird account",
    )

    def add_new_resource_entities() -> None:
        if not topology.last_update_success or topology.data is None:
            return
        registry = er.async_get(hass)
        known_resources.intersection_update(
            unique_id
            for unique_id in known_resources
            if registry.async_get_entity_id("binary_sensor", DOMAIN, unique_id)
            is not None
        )
        entities: list[NetBirdResourceEnabledBinarySensor] = []
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
            for resource in item.resources or ():
                unique_id = (
                    f"{entry.runtime_data.account_id}:network:{item.network.id}:"
                    f"resource:{resource.id}:enabled"
                )
                if unique_id in known_resources:
                    continue
                known_resources.add(unique_id)
                entities.append(
                    NetBirdResourceEnabledBinarySensor(
                        entry, item.network.id, resource, network_device.id
                    )
                )
        if entities:
            async_add_entities(entities)

    add_new_resource_entities()
    entry.async_on_unload(topology.async_add_listener(add_new_resource_entities))


class NetBirdPeerBinarySensor(NetBirdPeerEntity, BinarySensorEntity):
    """A peer field with availability independent from its boolean state."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        entry: NetBirdConfigEntry,
        peer: NetBirdPeer,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor from an entity description."""
        super().__init__(entry, peer, description.key)
        self.entity_description = description

    @property
    @override
    def available(self) -> bool:
        """Missing boolean data is unknown, not a false problem/offline state."""
        peer = self.peer
        return super().available and peer is not None and self._value(peer) is not None

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the current peer field, including an unknown optional value."""
        peer = self.peer
        return self._value(peer) if peer is not None else None

    def _value(self, peer: NetBirdPeer) -> bool | None:
        """Select only approved typed peer fields."""
        return BINARY_VALUE_GETTERS[self.entity_description.key](peer)


class NetBirdResourceEnabledBinarySensor(NetBirdResourceEntity, BinarySensorEntity):
    """Whether one network resource is enabled."""

    _attr_translation_key = "resource_enabled"

    def __init__(
        self,
        entry: NetBirdConfigEntry,
        network_id: str,
        resource: NetBirdResource,
        via_device_id: str,
    ) -> None:
        super().__init__(entry, network_id, resource, "enabled", via_device_id)

    @property
    @override
    def is_on(self) -> bool | None:
        resource = self.resource
        return resource.enabled if resource is not None else None
