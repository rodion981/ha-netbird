"""Conservative lifecycle management for stale NetBird peers."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.issue_registry import IssueSeverity

from .const import DOMAIN, STALE_PEER_SNAPSHOT_THRESHOLD
from .models import NetBirdPeer

if TYPE_CHECKING:
    from . import NetBirdConfigEntry


class NetBirdPeerLifecycle:
    """Track successful peer absences and clean integration-owned registry data."""

    def __init__(self, hass: HomeAssistant, entry: NetBirdConfigEntry) -> None:
        """Seed runtime-only tracking from the first authoritative snapshot."""
        self._hass = hass
        self._entry = entry
        self._coordinator = entry.runtime_data.coordinator
        self._account_id = entry.runtime_data.account_id
        identifier_prefix = f"{self._account_id}:"
        registry_peer_ids = {
            identifier[len(identifier_prefix) :]
            for device in dr.async_entries_for_config_entry(
                dr.async_get(hass), entry.entry_id
            )
            for domain, identifier in device.identifiers
            if domain == DOMAIN
            and identifier.startswith(identifier_prefix)
            and len(identifier) > len(identifier_prefix)
        }
        present_peer_ids = {peer.id for peer in self._coordinator.data}
        self._known_peer_ids = registry_peer_ids | present_peer_ids
        self._missing_counts: dict[str, int] = {}
        for peer_id in present_peer_ids:
            self._clear_repair(peer_id)

    @callback
    def async_start(self) -> None:
        """Register one coordinator listener owned by the config entry."""
        self._entry.async_on_unload(
            self._coordinator.async_add_successful_refresh_listener(
                self._handle_successful_refresh
            )
        )

    @callback
    def _handle_successful_refresh(self, peers: tuple[NetBirdPeer, ...]) -> None:
        """Advance stale tracking from one successful authoritative snapshot."""
        present_peer_ids = {peer.id for peer in peers}
        for peer_id in present_peer_ids:
            self._missing_counts.pop(peer_id, None)
            self._clear_repair(peer_id)

        self._known_peer_ids.update(present_peer_ids)
        for peer_id in self._known_peer_ids - present_peer_ids:
            missing_count = min(
                self._missing_counts.get(peer_id, 0) + 1,
                STALE_PEER_SNAPSHOT_THRESHOLD,
            )
            self._missing_counts[peer_id] = missing_count
            if missing_count == STALE_PEER_SNAPSHOT_THRESHOLD:
                self._cleanup_peer(peer_id)

    @callback
    def _cleanup_peer(self, peer_id: str) -> None:
        """Remove one stale peer only when every registry association is owned."""
        entity_registry = er.async_get(self._hass)
        device_registry = dr.async_get(self._hass)
        unique_id_prefix = f"{self._account_id}:{peer_id}:"
        peer_entities = [
            entity
            for entity in er.async_entries_for_config_entry(
                entity_registry, self._entry.entry_id
            )
            if entity.platform == DOMAIN
            and entity.unique_id.startswith(unique_id_prefix)
        ]
        peer_entity_ids = {entity.entity_id for entity in peer_entities}
        entity_device_ids = {
            entity.device_id for entity in peer_entities if entity.device_id is not None
        }
        identified_device = device_registry.async_get_device_by_identifier(
            (DOMAIN, f"{self._account_id}:{peer_id}"), self._entry.entry_id
        )
        if identified_device is not None:
            entity_device_ids.add(identified_device.id)

        if len(entity_device_ids) > 1:
            self._create_repair(peer_id)
            return

        device: dr.DeviceEntry | None = None
        if entity_device_ids:
            device_id = next(iter(entity_device_ids))
            registry_device = device_registry.async_get(device_id)
            linked_entity_ids = {
                entity.entity_id
                for entity in entity_registry.entities.values()
                if entity.device_id == device_id
            }
            if (
                not isinstance(registry_device, dr.DeviceEntry)
                or registry_device.config_entry_id != self._entry.entry_id
                or linked_entity_ids != peer_entity_ids
            ):
                self._create_repair(peer_id)
                return
            device = registry_device

        for entity in peer_entities:
            entity_registry.async_remove(entity.entity_id)
        if device is not None:
            device_registry.async_remove_device(device.id)

        self._known_peer_ids.discard(peer_id)
        self._missing_counts.pop(peer_id, None)
        self._clear_repair(peer_id)

    def _repair_id(self, peer_id: str) -> str:
        """Return a stable opaque repair ID without exposing account or peer IDs."""
        digest = sha256(f"{self._account_id}:{peer_id}".encode()).hexdigest()[:16]
        return f"stale_peer_cleanup_{digest}"

    @callback
    def _create_repair(self, peer_id: str) -> None:
        """Expose safe guidance when registry ownership prevents cleanup."""
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            self._repair_id(peer_id),
            is_fixable=False,
            is_persistent=True,
            severity=IssueSeverity.WARNING,
            translation_key="stale_peer_cleanup_blocked",
        )

    @callback
    def _clear_repair(self, peer_id: str) -> None:
        """Clear obsolete guidance after return or successful cleanup."""
        ir.async_delete_issue(self._hass, DOMAIN, self._repair_id(peer_id))


@callback
def async_setup_peer_lifecycle(hass: HomeAssistant, entry: NetBirdConfigEntry) -> None:
    """Set up runtime-only stale-peer tracking for one config entry."""
    NetBirdPeerLifecycle(hass, entry).async_start()
