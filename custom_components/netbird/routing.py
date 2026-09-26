"""Resolve NetBird Network routers to concrete peer identities."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import NetBirdPeer, NetBirdRouter


@dataclass(frozen=True, slots=True)
class NetBirdRoutingPeerResolution:
    """Known routing peers and whether the resolution is authoritative."""

    peer_ids: frozenset[str]
    complete: bool


def resolve_routing_peer_ids(
    routers: tuple[NetBirdRouter, ...] | None,
    peers: tuple[NetBirdPeer, ...] | None,
) -> NetBirdRoutingPeerResolution:
    """Resolve enabled concrete and group routers without hiding missing data."""
    if routers is None:
        return NetBirdRoutingPeerResolution(frozenset(), complete=False)

    enabled_routers = tuple(router for router in routers if router.enabled)
    if not enabled_routers:
        return NetBirdRoutingPeerResolution(frozenset(), complete=True)
    if peers is None:
        return NetBirdRoutingPeerResolution(frozenset(), complete=False)

    peer_ids = {peer.id for peer in peers}
    peers_by_group: defaultdict[str, set[str]] = defaultdict(set)
    group_membership_complete = True
    for peer in peers:
        if not peer.groups_present or peer.group_ids is None:
            group_membership_complete = False
            continue
        for group_id in peer.group_ids:
            peers_by_group[group_id].add(peer.id)

    resolved_peer_ids: set[str] = set()
    complete = True
    for router in enabled_routers:
        has_target = False
        if router.peer_id is not None:
            has_target = True
            if router.peer_id in peer_ids:
                resolved_peer_ids.add(router.peer_id)
            else:
                complete = False

        if router.peer_group_ids:
            has_target = True
            for group_id in router.peer_group_ids:
                resolved_peer_ids.update(peers_by_group[group_id])
            if not group_membership_complete:
                complete = False

        if not has_target:
            complete = False

    return NetBirdRoutingPeerResolution(
        peer_ids=frozenset(resolved_peer_ids),
        complete=complete,
    )
