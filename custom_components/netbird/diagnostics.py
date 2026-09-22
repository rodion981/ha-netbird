"""Allowlisted diagnostics for a NetBird config entry."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from . import NetBirdConfigEntry, NetBirdRuntimeData
from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NetBirdConfigEntry
) -> dict[str, Any]:
    """Return cached aggregate state without copying private source mappings."""
    integration = await async_get_integration(hass, DOMAIN)
    runtime: NetBirdRuntimeData | None = getattr(entry, "runtime_data", None)
    coordinator = runtime.coordinator if runtime is not None else None
    peers = coordinator.data if coordinator is not None else None
    error = coordinator.last_exception if coordinator is not None else None
    topology = runtime.topology_coordinator if runtime is not None else None
    topology_snapshot = topology.data if topology is not None else None
    topology_error = topology.last_exception if topology is not None else None

    return {
        "integration_version": integration.version,
        "deployment_class": "cloud",
        "coordinator": {
            "last_update_success": (
                coordinator.last_update_success if coordinator is not None else False
            ),
            "last_successful_refresh": (
                coordinator.last_successful_refresh.isoformat()
                if coordinator is not None
                and coordinator.last_successful_refresh is not None
                else None
            ),
            "error_class": type(error).__name__ if error is not None else None,
        },
        "peers": {
            "total": len(peers) if peers is not None else None,
            "connected": (
                sum(peer.connected is True for peer in peers)
                if peers is not None
                else None
            ),
        },
        "topology": {
            "last_update_success": (
                topology.last_update_success if topology is not None else False
            ),
            "error_class": (
                type(topology_error).__name__ if topology_error is not None else None
            ),
            "networks": (
                len(topology_snapshot.networks)
                if topology_snapshot is not None
                else None
            ),
            "complete_resource_sections": (
                sum(item.resources is not None for item in topology_snapshot.networks)
                if topology_snapshot is not None
                else None
            ),
            "complete_router_sections": (
                sum(item.routers is not None for item in topology_snapshot.networks)
                if topology_snapshot is not None
                else None
            ),
        },
    }
