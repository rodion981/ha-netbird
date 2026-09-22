"""NetBird peer diagnostic sensors."""

from __future__ import annotations

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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NetBirdConfigEntry
from .const import DOMAIN
from .coordinator import NetBirdPeerCoordinator
from .entity import NetBirdPeerEntity
from .models import NetBirdPeer

PARALLEL_UPDATES = 0

LAST_SEEN_DESCRIPTION = SensorEntityDescription(
    key="last_seen",
    translation_key="last_seen",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
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
    known_peer_ids: set[str] = set()
    async_add_entities(
        NetBirdAccountSensor(entry, description) for description in ACCOUNT_DESCRIPTIONS
    )

    def add_new_peer_entities() -> None:
        """Add one diagnostic entity for each peer in a successful snapshot."""
        if not coordinator.last_update_success:
            return

        registry = er.async_get(hass)
        account_id = entry.runtime_data.account_id
        known_peer_ids.intersection_update(
            peer_id
            for peer_id in known_peer_ids
            if registry.async_get_entity_id(
                "sensor", DOMAIN, f"{account_id}:{peer_id}:last_seen"
            )
            is not None
        )

        entities: list[NetBirdPeerLastSeen] = []
        for peer in coordinator.data:
            if peer.id in known_peer_ids:
                continue
            known_peer_ids.add(peer.id)
            entities.append(NetBirdPeerLastSeen(entry, peer))
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


class NetBirdPeerLastSeen(NetBirdPeerEntity, SensorEntity):
    """The last valid, timezone-aware timestamp for a peer."""

    entity_description = LAST_SEEN_DESCRIPTION

    def __init__(self, entry: NetBirdConfigEntry, peer: NetBirdPeer) -> None:
        """Initialize with a stable peer identity."""
        super().__init__(entry, peer, LAST_SEEN_DESCRIPTION.key)

    @property
    @override
    def native_value(self) -> datetime | None:
        """Return a UTC instant or unknown for missing/invalid timestamps."""
        peer = self.peer
        value = peer.last_seen if peer is not None else None
        return value.astimezone(UTC) if value is not None and value.tzinfo else None
