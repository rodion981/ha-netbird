"""Tests for the async NetBird Cloud API client."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Self, cast

import pytest
from aiohttp import ClientConnectionError, ClientSession, ClientTimeout

from custom_components.netbird.api import (
    NetBirdApiClient,
    NetBirdAuthenticationError,
    NetBirdJsonError,
    NetBirdPermissionError,
    NetBirdRateLimitError,
    NetBirdResponseError,
    NetBirdSchemaError,
    NetBirdServerError,
    NetBirdTimeoutError,
    NetBirdTransportError,
    NetBirdUpdateError,
)
from custom_components.netbird.const import API_BASE_URL, API_TIMEOUT_SECONDS
from custom_components.netbird.models import (
    NetBirdAccount,
    NetBirdNetwork,
    NetBirdPeer,
    NetBirdResource,
    NetBirdRouter,
)

TOKEN = "test-pat-must-not-be-logged"


class FakeResponse:
    """Minimal async response used to isolate client behavior."""

    def __init__(
        self,
        payload: Any = None,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.status = status
        self.headers = headers or {}
        self.json_error = json_error

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def json(self, *, content_type: None = None) -> Any:
        assert content_type is None
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeSession:
    """Record requests and return queued fake responses."""

    def __init__(self, *responses: FakeResponse | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_client(
    *responses: FakeResponse | Exception,
) -> tuple[NetBirdApiClient, FakeSession]:
    """Return a client backed by a recording fake session."""
    session = FakeSession(*responses)
    return NetBirdApiClient(cast(ClientSession, session), TOKEN), session


async def test_snapshot_success_and_request_contract(
    load_netbird_fixture: Any,
) -> None:
    """Test typed snapshots, Cloud URLs, headers, and timeout."""
    accounts = load_netbird_fixture("accounts.json")
    peers = load_netbird_fixture("peers.json")
    client, session = make_client(FakeResponse(accounts), FakeResponse(peers))

    snapshot = await client.async_get_snapshot()

    assert snapshot.account == NetBirdAccount(id="account-test-id")
    assert snapshot.peers == (
        NetBirdPeer(
            id="peer-test-id",
            name="test-peer",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            ip="100.64.0.2",
            connected=True,
            last_seen=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
            os="linux",
            version="0.0.0-test",
        ),
    )
    assert [request[0] for request in session.requests] == [
        f"{API_BASE_URL}/api/accounts",
        f"{API_BASE_URL}/api/peers",
    ]
    for _, kwargs in session.requests:
        assert kwargs["headers"] == {
            "Accept": "application/json",
            "Authorization": f"Token {TOKEN}",
        }
        assert kwargs["timeout"] == ClientTimeout(total=API_TIMEOUT_SECONDS)


async def test_anonymized_live_bulk_shape_fixture(load_netbird_fixture: Any) -> None:
    """Parse synthetic values matching fields/types observed in Cloud bulk data."""
    payload = load_netbird_fixture("peers_live_shape.json")
    client, session = make_client(FakeResponse(payload))

    assert await client.async_get_peers() == (
        NetBirdPeer(
            id="peer-anonymized",
            name="test-peer",
            connected=True,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            last_seen=datetime(2026, 1, 2, tzinfo=UTC),
            last_login=datetime(2026, 1, 1, 1, tzinfo=UTC),
            accessible_peers_count=2,
            login_expired=False,
            approval_required=False,
            ephemeral=False,
        ),
    )
    assert len(session.requests) == 1


async def test_missing_optional_peer_fields_are_normalized() -> None:
    """Test omitted and unavailable optional fields do not fail a refresh."""
    client, _ = make_client(FakeResponse([{"id": "peer-minimal"}]))

    peers = await client.async_get_peers()

    assert peers == (NetBirdPeer(id="peer-minimal"),)


async def test_null_optional_peer_fields_are_normalized() -> None:
    """Optional null values do not reject an otherwise valid bulk list."""
    client, _ = make_client(
        FakeResponse(
            [
                {
                    "id": "peer",
                    "name": None,
                    "connected": None,
                    "created_at": None,
                    "last_seen": None,
                    "last_login": None,
                    "accessible_peers_count": None,
                    "extra_dns_labels": None,
                }
            ]
        )
    )

    assert await client.async_get_peers() == (NetBirdPeer(id="peer"),)


async def test_authentication_error_is_secret_safe(caplog: Any) -> None:
    """Test HTTP 401 is an authentication failure without secret leakage."""
    client, _ = make_client(FakeResponse(status=401))

    with pytest.raises(NetBirdAuthenticationError, match="authentication failed"):
        await client.async_get_account()

    assert TOKEN not in caplog.text


async def test_permission_error_is_distinct_and_secret_safe(caplog: Any) -> None:
    """Test HTTP 403 is not classified as an authentication failure."""
    client, _ = make_client(FakeResponse(status=403))

    with pytest.raises(NetBirdPermissionError, match="permission denied") as raised:
        await client.async_get_account()

    assert not isinstance(raised.value, NetBirdAuthenticationError)
    assert isinstance(raised.value, NetBirdUpdateError)
    assert TOKEN not in str(raised.value)
    assert TOKEN not in caplog.text


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, NetBirdAuthenticationError),
        (403, NetBirdPermissionError),
    ],
)
async def test_auth_and_permission_errors_hide_response_content(
    status: int, expected: type[Exception], caplog: Any
) -> None:
    """Neither HTTP error exposes response body, headers, or credentials."""
    response_secret = "private-response-content-sentinel"
    client, _ = make_client(
        FakeResponse(
            payload={"body": response_secret},
            status=status,
            headers={"X-Private": response_secret},
        )
    )

    with pytest.raises(expected) as raised:
        await client.async_get_peers()

    assert response_secret not in str(raised.value)
    assert TOKEN not in str(raised.value)
    assert response_secret not in caplog.text
    assert TOKEN not in caplog.text


@pytest.mark.parametrize("retry_after", [None, "30"])
async def test_rate_limit_preserves_only_supplied_retry_after(
    retry_after: str | None,
) -> None:
    """Test rate limits remain retryable without an implicit retry loop."""
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    client, session = make_client(FakeResponse(status=429, headers=headers))

    with pytest.raises(NetBirdRateLimitError) as raised:
        await client.async_get_peers()

    assert raised.value.retry_after == retry_after
    assert len(session.requests) == 1


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_server_errors_are_recoverable(status: int) -> None:
    """Test server failures map to a retryable update exception."""
    client, _ = make_client(FakeResponse(status=status))

    with pytest.raises(NetBirdServerError) as raised:
        await client.async_get_peers()

    assert raised.value.status == status


async def test_other_http_error_is_mapped_without_response_body() -> None:
    """Test unexpected HTTP failures remain safe and typed."""
    client, _ = make_client(FakeResponse(status=400))

    with pytest.raises(NetBirdResponseError) as raised:
        await client.async_get_peers()

    assert raised.value.status == 400
    assert TOKEN not in str(raised.value)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (TimeoutError(), NetBirdTimeoutError),
        (ClientConnectionError(), NetBirdTransportError),
    ],
)
async def test_transport_failures_are_recoverable(
    failure: Exception, expected: type[Exception], caplog: Any
) -> None:
    """Test timeout and network failures map without leaking the PAT."""
    client, _ = make_client(failure)

    with pytest.raises(expected):
        await client.async_get_peers()

    assert TOKEN not in caplog.text


async def test_malformed_json_is_mapped_and_secret_safe(caplog: Any) -> None:
    """Test invalid JSON is a safe, retryable data failure."""
    client, _ = make_client(
        FakeResponse(json_error=ValueError(f"bad JSON containing {TOKEN}"))
    )

    with pytest.raises(NetBirdJsonError, match="invalid JSON") as raised:
        await client.async_get_account()

    assert TOKEN not in str(raised.value)
    assert TOKEN not in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        [{"id": "one"}, {"id": "two"}],
        [{}],
        [{"id": ""}],
    ],
)
async def test_invalid_account_schema(payload: Any) -> None:
    """Test account responses require exactly one usable identifier."""
    client, _ = make_client(FakeResponse(payload))

    with pytest.raises(NetBirdSchemaError):
        await client.async_get_account()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [None],
        [{}],
        [{"id": "peer", "connected": "yes"}],
        [{"id": "peer", "accessible_peers_count": True}],
        [{"id": "peer", "extra_dns_labels": ["valid", 3]}],
    ],
)
async def test_invalid_peer_schema(payload: Any) -> None:
    """Test unusable peer shapes and optional values are rejected."""
    client, _ = make_client(FakeResponse(payload))

    with pytest.raises(NetBirdSchemaError):
        await client.async_get_peers()


@pytest.mark.parametrize("last_seen", ["not-a-timestamp", "2026-01-01", 123])
async def test_invalid_optional_last_seen_is_unknown(last_seen: Any) -> None:
    """An invalid last-seen value does not discard a valid peer snapshot."""
    client, _ = make_client(FakeResponse([{"id": "peer", "last_seen": last_seen}]))

    assert (await client.async_get_peers())[0].last_seen is None


async def test_last_seen_with_offset_is_normalized_to_utc() -> None:
    """A valid offset timestamp represents the same UTC instant."""
    client, _ = make_client(
        FakeResponse([{"id": "peer", "last_seen": "2026-01-02T05:04:00+02:00"}])
    )

    assert (await client.async_get_peers())[0].last_seen == datetime(
        2026, 1, 2, 3, 4, tzinfo=UTC
    )


@pytest.mark.parametrize("field", ["created_at", "last_login"])
@pytest.mark.parametrize("value", ["invalid", "2026-01-01", 123])
async def test_invalid_optional_peer_timestamps_are_unknown(
    field: str, value: Any
) -> None:
    """An invalid optional timestamp cannot invalidate an authoritative peer."""
    client, _ = make_client(FakeResponse([{"id": "peer", field: value}]))

    assert getattr((await client.async_get_peers())[0], field) is None


@pytest.mark.parametrize("field", ["created_at", "last_login"])
async def test_optional_peer_timestamps_are_normalized_to_utc(field: str) -> None:
    """All parsed peer timestamps use the same UTC normalization."""
    client, _ = make_client(
        FakeResponse([{"id": "peer", field: "2026-01-02T05:04:00+02:00"}])
    )

    assert getattr((await client.async_get_peers())[0], field) == datetime(
        2026, 1, 2, 3, 4, tzinfo=UTC
    )


async def test_duplicate_peer_ids_invalidate_authoritative_snapshot() -> None:
    """One peer ID cannot identify two records in the same bulk response."""
    client, _ = make_client(
        FakeResponse([{"id": "peer"}, {"id": "peer", "connected": False}])
    )

    with pytest.raises(NetBirdSchemaError, match="duplicate peer id"):
        await client.async_get_peers()


async def test_bulk_peer_request_budget_for_large_snapshot() -> None:
    """A large bulk inventory still needs only one API request."""
    client, session = make_client(
        FakeResponse([{"id": f"peer-{index}"} for index in range(1000)])
    )

    peers = await client.async_get_peers()

    assert len(peers) == 1000
    assert [url for url, _ in session.requests] == [f"{API_BASE_URL}/api/peers"]


async def test_cancelled_bulk_request_is_not_mapped_to_transport_failure() -> None:
    """Cancellation propagates to Home Assistant instead of becoming a retry."""

    class CancelledSession:
        def get(self, _url: str, **_kwargs: Any) -> None:
            raise asyncio.CancelledError

    client = NetBirdApiClient(cast(ClientSession, CancelledSession()), TOKEN)

    with pytest.raises(asyncio.CancelledError):
        await client.async_get_peers()


async def test_topology_endpoints_and_typed_models(load_netbird_fixture: Any) -> None:
    """Current topology endpoints return typed, network-scoped records."""
    client, session = make_client(
        FakeResponse(load_netbird_fixture("networks.json")),
        FakeResponse(load_netbird_fixture("network_resources.json")),
        FakeResponse(load_netbird_fixture("network_routers.json")),
    )

    assert await client.async_get_networks() == (
        NetBirdNetwork("network-test-id", "Home LAN", "Test network"),
    )
    assert await client.async_get_network_resources("network-test-id") == (
        NetBirdResource(
            "resource-test-id",
            "network-test-id",
            "Home subnet",
            "192.0.2.0/24",
            "subnet",
            True,
        ),
    )
    assert await client.async_get_network_routers("network-test-id") == (
        NetBirdRouter(
            "router-test-id",
            "network-test-id",
            True,
            peer_id="peer-test-id",
        ),
    )
    assert [url for url, _ in session.requests] == [
        f"{API_BASE_URL}/api/networks",
        f"{API_BASE_URL}/api/networks/network-test-id/resources",
        f"{API_BASE_URL}/api/networks/network-test-id/routers",
    ]
    assert all(
        request[1]["headers"]["Authorization"] == f"Token {TOKEN}"
        for request in session.requests
    )


@pytest.mark.parametrize("network_id", ["", " ", "network/id"])
async def test_topology_rejects_invalid_network_path_id(network_id: str) -> None:
    """Untrusted IDs cannot alter endpoint paths."""
    client, session = make_client()

    with pytest.raises(NetBirdSchemaError):
        await client.async_get_network_resources(network_id)

    assert not session.requests
