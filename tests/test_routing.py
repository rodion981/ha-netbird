"""Tests for resolving Network routers to concrete NetBird peers."""

from custom_components.netbird.models import NetBirdPeer, NetBirdRouter
from custom_components.netbird.routing import (
    count_connected_routing_peers,
    resolve_routing_peer_ids,
)


def _router(
    router_id: str,
    *,
    enabled: bool = True,
    peer_id: str | None = None,
    peer_group_ids: tuple[str, ...] = (),
) -> NetBirdRouter:
    return NetBirdRouter(
        id=router_id,
        network_id="network",
        enabled=enabled,
        peer_id=peer_id,
        peer_group_ids=peer_group_ids,
    )


def test_concrete_and_group_routers_resolve_and_deduplicate_peers() -> None:
    """A peer referenced directly and through groups appears only once."""
    peers = (
        NetBirdPeer("peer-1", group_ids=("group-1", "group-2"), groups_present=True),
        NetBirdPeer("peer-2", group_ids=("group-1",), groups_present=True),
        NetBirdPeer("peer-3", group_ids=(), groups_present=True),
    )
    routers = (
        _router("concrete", peer_id="peer-1"),
        _router("group-1", peer_group_ids=("group-1",)),
        _router("group-2", peer_group_ids=("group-2",)),
    )

    resolution = resolve_routing_peer_ids(routers, peers)

    assert resolution.peer_ids == frozenset({"peer-1", "peer-2"})
    assert resolution.complete


def test_incomplete_group_membership_preserves_known_resolution() -> None:
    """Known peers remain usable without presenting a partial result as complete."""
    peers = (
        NetBirdPeer("peer-1"),
        NetBirdPeer("peer-2", group_ids=("group-1",), groups_present=True),
        NetBirdPeer("peer-3", group_ids=None, groups_present=True),
    )
    routers = (
        _router("concrete", peer_id="peer-1"),
        _router("group", peer_group_ids=("group-1",)),
    )

    resolution = resolve_routing_peer_ids(routers, peers)

    assert resolution.peer_ids == frozenset({"peer-1", "peer-2"})
    assert not resolution.complete


def test_missing_concrete_peer_marks_resolution_incomplete() -> None:
    """A stale concrete router reference cannot silently become a complete zero."""
    resolution = resolve_routing_peer_ids(
        (_router("router", peer_id="missing"),),
        (NetBirdPeer("peer", group_ids=(), groups_present=True),),
    )

    assert resolution.peer_ids == frozenset()
    assert not resolution.complete


def test_concrete_router_does_not_require_group_membership_data() -> None:
    """Missing group fields do not weaken an independently resolvable router."""
    resolution = resolve_routing_peer_ids(
        (_router("router", peer_id="peer"),),
        (NetBirdPeer("peer"),),
    )

    assert resolution.peer_ids == frozenset({"peer"})
    assert resolution.complete


def test_partial_sections_remain_isolated() -> None:
    """Missing router or required peer data is incomplete, not an empty snapshot."""
    router = _router("router", peer_id="peer")

    assert not resolve_routing_peer_ids(None, (NetBirdPeer("peer"),)).complete
    assert not resolve_routing_peer_ids((router,), None).complete


def test_empty_and_disabled_router_sets_need_no_peer_snapshot() -> None:
    """No enabled routing references is a complete empty resolution."""
    empty = resolve_routing_peer_ids((), None)
    disabled = resolve_routing_peer_ids(
        (_router("disabled", enabled=False, peer_id="missing"),), None
    )

    assert empty.peer_ids == frozenset()
    assert empty.complete
    assert disabled.peer_ids == frozenset()
    assert disabled.complete


def test_enabled_router_without_target_is_incomplete() -> None:
    """An enabled router with no concrete or group target is not resolved."""
    resolution = resolve_routing_peer_ids(
        (_router("router"),),
        (NetBirdPeer("peer", group_ids=(), groups_present=True),),
    )

    assert resolution.peer_ids == frozenset()
    assert not resolution.complete


def test_connected_count_includes_group_peers_and_deduplicates() -> None:
    """Concrete and group paths count each connected peer once."""
    peers = (
        NetBirdPeer(
            "peer-1", connected=True, group_ids=("group-1",), groups_present=True
        ),
        NetBirdPeer(
            "peer-2", connected=False, group_ids=("group-1",), groups_present=True
        ),
    )
    routers = (
        _router("concrete", peer_id="peer-1"),
        _router("group", peer_group_ids=("group-1",)),
    )

    assert count_connected_routing_peers(routers, peers) == 1


def test_connected_count_rejects_incomplete_resolution() -> None:
    """Missing group membership cannot silently lower the count."""
    peers = (
        NetBirdPeer("peer-1", connected=True),
        NetBirdPeer(
            "peer-2", connected=True, group_ids=("group-1",), groups_present=True
        ),
    )

    assert (
        count_connected_routing_peers(
            (_router("group", peer_group_ids=("group-1",)),), peers
        )
        is None
    )


def test_connected_count_rejects_unknown_connection_state() -> None:
    """An unresolved connected flag is unavailable instead of false."""
    peers = (NetBirdPeer("peer-1", connected=None),)

    assert (
        count_connected_routing_peers((_router("concrete", peer_id="peer-1"),), peers)
        is None
    )


def test_connected_count_is_zero_without_enabled_routers() -> None:
    """A known empty routing set remains a valid zero without peer data."""
    assert count_connected_routing_peers((), None) == 0
