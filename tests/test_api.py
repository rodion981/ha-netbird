"""Tests for the async NetBird Cloud API client."""

from __future__ import annotations

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
from custom_components.netbird.models import NetBirdAccount, NetBirdPeer

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


async def test_missing_optional_peer_fields_are_normalized() -> None:
    """Test omitted and unavailable optional fields do not fail a refresh."""
    client, _ = make_client(FakeResponse([{"id": "peer-minimal"}]))

    peers = await client.async_get_peers()

    assert peers == (NetBirdPeer(id="peer-minimal"),)


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
