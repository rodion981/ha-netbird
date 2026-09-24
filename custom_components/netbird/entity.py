"""Shared identity and availability for NetBird peer entities."""

from __future__ import annotations

from typing import override

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
        account_id = entry.runtime_data.account_id
        self._attr_unique_id = f"{account_id}:{peer.id}:{key}"
        self._attr_extra_state_attributes = {"netbird_key": key}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{account_id}:{peer.id}")},
            manufacturer="NetBird",
            name=peer.name or peer.id,
            sw_version=peer.version,
            configuration_url=build_dashboard_url("peer", peer_id=peer.id),
        )

    @property
    def peer(self) -> NetBirdPeer | None:
        """Read current data, never a stale peer object after refresh."""
        return next(
            (peer for peer in self.coordinator.data if peer.id == self._peer_id),
            None,
        )

    @property
    @override
    def available(self) -> bool:
        """A failed refresh or an absent peer must not expose an old state."""
        return super().available and self.peer is not None
