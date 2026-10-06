"""Shared identity and availability for NetBird peer entities."""

from __future__ import annotations

from typing import override

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NetBirdConfigEntry
from .const import DOMAIN
from .coordinator import NetBirdPeerCoordinator
from .dashboard_urls import build_dashboard_url
from .models import NetBirdPeer


class NetBirdPeerEntity(CoordinatorEntity[NetBirdPeerCoordinator]):
    """An entity backed by the shared, authoritative peer snapshot."""

    _attr_has_entity_name = True

    def __init__(self, entry: NetBirdConfigEntry, peer: NetBirdPeer, key: str) -> None:
        """Bind a stable peer identity without retaining sensitive API data."""
        super().__init__(entry.runtime_data.coordinator)
        self._peer_id = peer.id
        self._netbird_key = key
        account_id = entry.runtime_data.account_id
        self._attr_unique_id = f"{account_id}:{peer.id}:{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{account_id}:{peer.id}")},
            manufacturer="NetBird",
            name=peer.name or peer.id,
            sw_version=peer.version,
            configuration_url=build_dashboard_url(
                "peer",
                base_url=entry.runtime_data.dashboard_url,
                peer_id=peer.id,
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
    def peer(self) -> NetBirdPeer | None:
        """Read current data, never a stale peer object after refresh."""
        return next(
            (peer for peer in self.coordinator.data if peer.id == self._peer_id),
            None,
        )

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Refresh device metadata without changing identity or user names."""
        peer = self.peer
        if (
            self.coordinator.last_update_success
            and peer is not None
            and self.device_entry
        ):
            registry = dr.async_get(self.hass)
            device = registry.async_get(self.device_entry.id)
            name = peer.name or peer.id
            if isinstance(device, dr.DeviceEntry) and (
                device.name != name or device.sw_version != peer.version
            ):
                registry.async_update_device(
                    device.id, name=name, sw_version=peer.version
                )
        super()._handle_coordinator_update()

    @property
    @override
    def available(self) -> bool:
        """A failed refresh or an absent peer must not expose an old state."""
        return super().available and self.peer is not None
