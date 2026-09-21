"""NetBird peer connectivity and problem binary sensors."""

from __future__ import annotations

from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NetBirdConfigEntry
from .entity import NetBirdPeerEntity
from .models import NetBirdPeer

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
    ),
    BinarySensorEntityDescription(
        key="approval_required",
        translation_key="approval_required",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: NetBirdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create only the applicable entities in the initial snapshot."""
    async_add_entities(
        NetBirdPeerBinarySensor(entry, peer, description)
        for peer in entry.runtime_data.coordinator.data
        for description in DESCRIPTIONS
        if description.key != "approval_required" or peer.approval_required is not None
    )


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
        if self.entity_description.key == "connected":
            return peer.connected
        if self.entity_description.key == "login_expired":
            return peer.login_expired
        return peer.approval_required
