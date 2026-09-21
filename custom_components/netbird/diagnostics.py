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
    }
