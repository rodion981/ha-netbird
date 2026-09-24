"""Best-effort links to matching NetBird Cloud dashboard pages."""

from __future__ import annotations

from typing import Literal, assert_never
from urllib.parse import urlencode

from .const import DASHBOARD_BASE_URL

DashboardTarget = Literal["account", "peer", "network", "resource"]


def _valid_identifier(value: object) -> bool:
    """Accept opaque query values while rejecting ambiguous or control input."""
    return (
        isinstance(value, str)
        and bool(value)
        and value.strip() == value
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def build_dashboard_url(
    target: DashboardTarget,
    *,
    peer_id: str | None = None,
    network_id: str | None = None,
    resource_id: str | None = None,
) -> str | None:
    """Build one Cloud dashboard URL without interpolating opaque identifiers."""
    if target == "account":
        return f"{DASHBOARD_BASE_URL}/peers"

    if target == "peer":
        if not _valid_identifier(peer_id):
            return None
        return f"{DASHBOARD_BASE_URL}/peer?{urlencode({'id': peer_id})}"

    if target == "network":
        if not _valid_identifier(network_id):
            return None
        return f"{DASHBOARD_BASE_URL}/network?{urlencode({'id': network_id})}"

    if target == "resource":
        if not _valid_identifier(network_id) or not _valid_identifier(resource_id):
            return None
        query = urlencode({"id": network_id, "resource": resource_id})
        return f"{DASHBOARD_BASE_URL}/network?{query}"

    assert_never(target)
