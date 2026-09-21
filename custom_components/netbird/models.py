"""Typed snapshots returned by the NetBird Cloud API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NetBirdAccount:
    """Normalized NetBird account snapshot."""

    id: str


@dataclass(frozen=True, slots=True)
class NetBirdPeer:
    """Normalized NetBird peer snapshot."""

    id: str
    name: str | None = None
    created_at: datetime | None = None
    ip: str | None = None
    ipv6: str | None = None
    connection_ip: str | None = None
    connected: bool | None = None
    last_seen: datetime | None = None
    os: str | None = None
    kernel_version: str | None = None
    geoname_id: int | None = None
    version: str | None = None
    ssh_enabled: bool | None = None
    user_id: str | None = None
    hostname: str | None = None
    ui_version: str | None = None
    dns_label: str | None = None
    login_expiration_enabled: bool | None = None
    login_expired: bool | None = None
    last_login: datetime | None = None
    inactivity_expiration_enabled: bool | None = None
    approval_required: bool | None = None
    country_code: str | None = None
    city_name: str | None = None
    serial_number: str | None = None
    extra_dns_labels: tuple[str, ...] = ()
    ephemeral: bool | None = None
    accessible_peers_count: int | None = None


@dataclass(frozen=True, slots=True)
class NetBirdSnapshot:
    """Normalized account and peer snapshot from one refresh."""

    account: NetBirdAccount
    peers: tuple[NetBirdPeer, ...]
