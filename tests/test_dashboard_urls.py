"""Tests for best-effort NetBird Cloud dashboard URLs."""

from custom_components.netbird.dashboard_urls import build_dashboard_url


def test_dashboard_urls_encode_each_identifier_independently() -> None:
    """Reserved characters cannot change paths or query boundaries."""
    assert build_dashboard_url("account") == "https://app.netbird.io/peers"
    assert (
        build_dashboard_url("peer", peer_id="peer /?&=+")
        == "https://app.netbird.io/peer?id=peer+%2F%3F%26%3D%2B"
    )
    assert (
        build_dashboard_url("network", network_id="network /?&=+")
        == "https://app.netbird.io/network?id=network+%2F%3F%26%3D%2B"
    )
    assert (
        build_dashboard_url(
            "resource",
            network_id="network &resource=wrong",
            resource_id="resource &id=wrong",
        )
        == "https://app.netbird.io/network?"
        "id=network+%26resource%3Dwrong&resource=resource+%26id%3Dwrong"
    )


def test_dashboard_urls_reject_missing_or_malformed_identifiers() -> None:
    """Invalid identifiers cannot create misleading or unsafe links."""
    assert build_dashboard_url("peer") is None
    assert build_dashboard_url("network", network_id="") is None
    assert (
        build_dashboard_url("resource", network_id="network", resource_id=None) is None
    )
    assert build_dashboard_url("peer", peer_id=" peer ") is None
    assert build_dashboard_url("peer", peer_id="peer\nsecond") is None
