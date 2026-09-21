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
    _hass: HomeAssistant,
    entry: NetBirdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create account counts and one peer diagnostic per initial peer."""
    async_add_entities(
        [
            NetBirdAccountSensor(entry, description)
            for description in ACCOUNT_DESCRIPTIONS
        ]
        + [
            NetBirdPeerLastSeen(entry, peer)
            for peer in entry.runtime_data.coordinator.data
        ]
    )


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
