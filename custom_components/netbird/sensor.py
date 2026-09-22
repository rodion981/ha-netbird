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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NetBirdConfigEntry
from .const import DOMAIN
from .coordinator import NetBirdPeerCoordinator
from .entity import NetBirdPeerEntity
from .models import NetBirdPeer

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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_id)},
            manufacturer="NetBird",
            name="NetBird account",
        )

    @property
    @override
    def native_value(self) -> int:
        """Return zero for an empty authoritative snapshot."""
        if self.entity_description.key == "peer_count":
            return len(self.coordinator.data)
        return sum(peer.connected is True for peer in self.coordinator.data)


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
