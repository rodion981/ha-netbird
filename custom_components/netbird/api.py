"""Async client for the NetBird Cloud API."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

from aiohttp import ClientError, ClientSession, ClientTimeout, ContentTypeError

from .const import API_BASE_URL, API_TIMEOUT_SECONDS
from .models import (
    NetBirdAccount,
    NetBirdNetwork,
    NetBirdPeer,
    NetBirdResource,
    NetBirdRouter,
    NetBirdSnapshot,
)

_ACCOUNTS_PATH: Final = "/api/accounts"
_PEERS_PATH: Final = "/api/peers"
_NETWORKS_PATH: Final = "/api/networks"
_TIMEOUT: Final = ClientTimeout(total=API_TIMEOUT_SECONDS)


class NetBirdError(Exception):
    """Base exception for safe NetBird API failures."""


class NetBirdAuthenticationError(NetBirdError):
    """The NetBird PAT is invalid or expired."""


class NetBirdUpdateError(NetBirdError):
    """A refresh failed and can be retried by the coordinator."""


class NetBirdPermissionError(NetBirdUpdateError):
    """The NetBird PAT lacks a required permission without requiring reauth."""


class NetBirdResponseError(NetBirdUpdateError):
    """The NetBird API returned an unexpected HTTP response."""

    def __init__(self, status: int) -> None:
        super().__init__(f"NetBird API request failed with HTTP status {status}")
        self.status = status


class NetBirdRateLimitError(NetBirdResponseError):
    """The NetBird API rate limit was reached."""

    def __init__(self, retry_after: str | None) -> None:
        super().__init__(429)
        self.retry_after = retry_after


class NetBirdServerError(NetBirdResponseError):
    """The NetBird API returned a server error."""


class NetBirdTransportError(NetBirdUpdateError):
    """A network transport failure prevented the request."""


class NetBirdTimeoutError(NetBirdTransportError):
    """A NetBird API request exceeded its total timeout."""


class NetBirdDataError(NetBirdUpdateError):
    """The NetBird API returned unusable data."""


class NetBirdJsonError(NetBirdDataError):
    """The NetBird API response was not valid JSON."""


class NetBirdSchemaError(NetBirdDataError):
    """The NetBird API response did not match the usable schema."""


class NetBirdApiClient:
    """Read-only async client for NetBird Cloud."""

    def __init__(self, session: ClientSession, token: str) -> None:
        """Initialize the client with Home Assistant's aiohttp session."""
        self._session = session
        self._token = token

    async def async_get_account(self) -> NetBirdAccount:
        """Return the single account available to the PAT."""
        payload = await self._async_get_json(_ACCOUNTS_PATH)
        accounts = _require_list(payload, _ACCOUNTS_PATH)
        if len(accounts) != 1:
            raise NetBirdSchemaError(
                "NetBird accounts response must contain exactly one account"
            )

        account = _require_mapping(accounts[0], "account")
        return NetBirdAccount(id=_required_identifier(account, "account"))

    async def async_get_peers(self) -> tuple[NetBirdPeer, ...]:
        """Return normalized peers available to the PAT."""
        payload = await self._async_get_json(_PEERS_PATH)
        peers = _require_list(payload, _PEERS_PATH)
        parsed_peers: list[NetBirdPeer] = []
        seen_ids: set[str] = set()
        for index, peer in enumerate(peers):
            parsed_peer = _parse_peer(_require_mapping(peer, f"peer[{index}]"))
            if parsed_peer.id in seen_ids:
                raise NetBirdSchemaError(
                    "NetBird peers response contains a duplicate peer id"
                )
            seen_ids.add(parsed_peer.id)
            parsed_peers.append(parsed_peer)
        return tuple(parsed_peers)

    async def async_get_snapshot(self) -> NetBirdSnapshot:
        """Return the account and peer data for one refresh."""
        account = await self.async_get_account()
        peers = await self.async_get_peers()
        return NetBirdSnapshot(account=account, peers=peers)

    async def async_get_networks(self) -> tuple[NetBirdNetwork, ...]:
        """Return the current Networks inventory."""
        payload = await self._async_get_json(_NETWORKS_PATH)
        return tuple(
            _parse_network(_require_mapping(item, f"network[{index}]"))
            for index, item in enumerate(_require_list(payload, _NETWORKS_PATH))
        )

    async def async_get_network_resources(
        self, network_id: str
    ) -> tuple[NetBirdResource, ...]:
        """Return resources attached to one network."""
        network_id = _validated_path_id(network_id, "network")
        path = f"/api/networks/{network_id}/resources"
        payload = await self._async_get_json(path)
        return tuple(
            _parse_resource(_require_mapping(item, f"resource[{index}]"), network_id)
            for index, item in enumerate(_require_list(payload, path))
        )

    async def async_get_network_routers(
        self, network_id: str
    ) -> tuple[NetBirdRouter, ...]:
        """Return routers attached to one network."""
        network_id = _validated_path_id(network_id, "network")
        path = f"/api/networks/{network_id}/routers"
        payload = await self._async_get_json(path)
        return tuple(
            _parse_router(_require_mapping(item, f"router[{index}]"), network_id)
            for index, item in enumerate(_require_list(payload, path))
        )

    async def _async_get_json(self, path: str) -> Any:
        """Request JSON and map all failures to integration-safe exceptions."""
        headers = {
            "Accept": "application/json",
            "Authorization": f"Token {self._token}",
        }
        try:
            async with self._session.get(
                f"{API_BASE_URL}{path}", headers=headers, timeout=_TIMEOUT
            ) as response:
                _raise_for_status(
                    response.status,
                    response.headers.get("Retry-After"),
                )
                try:
                    return await response.json(content_type=None)
                except (
                    ContentTypeError,
                    UnicodeDecodeError,
                    ValueError,
                    TypeError,
                ) as err:
                    raise NetBirdJsonError(
                        f"NetBird API returned invalid JSON for {path}"
                    ) from err
        except NetBirdError:
            raise
        except TimeoutError as err:
            raise NetBirdTimeoutError("NetBird API request timed out") from err
        except ClientError as err:
            raise NetBirdTransportError("NetBird API request failed") from err


def _raise_for_status(status: int, retry_after: str | None) -> None:
    """Map an HTTP status without reading or exposing its response body."""
    if 200 <= status < 300:
        return
    if status == 401:
        raise NetBirdAuthenticationError("NetBird API authentication failed")
    if status == 403:
        raise NetBirdPermissionError("NetBird API permission denied")
    if status == 429:
        raise NetBirdRateLimitError(retry_after)
    if status >= 500:
        raise NetBirdServerError(status)
    raise NetBirdResponseError(status)


def _require_list(value: Any, context: str) -> list[Any]:
    """Return a JSON list or raise a safe schema error."""
    if not isinstance(value, list):
        raise NetBirdSchemaError(f"NetBird {context} response must be a list")
    return value


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    """Return a JSON object or raise a safe schema error."""
    if not isinstance(value, dict):
        raise NetBirdSchemaError(f"NetBird {context} must be an object")
    return value


def _required_identifier(data: Mapping[str, Any], context: str) -> str:
    """Return a non-empty resource identifier."""
    value = data.get("id")
    if not isinstance(value, str) or not value.strip():
        raise NetBirdSchemaError(f"NetBird {context} id must be a non-empty string")
    return value


def _required_string(data: Mapping[str, Any], field: str, context: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise NetBirdSchemaError(
            f"NetBird {context} {field} must be a non-empty string"
        )
    return value


def _required_bool(data: Mapping[str, Any], field: str, context: str) -> bool:
    value = data.get(field)
    if not isinstance(value, bool):
        raise NetBirdSchemaError(f"NetBird {context} {field} must be a boolean")
    return value


def _validated_path_id(value: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip() or "/" in value:
        raise NetBirdSchemaError(f"NetBird {context} id is invalid")
    return value


def _optional_string(data: Mapping[str, Any], field: str) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise NetBirdSchemaError(f"NetBird peer {field} must be a string or null")
    return value


def _optional_bool(data: Mapping[str, Any], field: str) -> bool | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise NetBirdSchemaError(f"NetBird peer {field} must be a boolean or null")
    return value


def _optional_int(data: Mapping[str, Any], field: str) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise NetBirdSchemaError(f"NetBird peer {field} must be an integer or null")
    return value


def _optional_datetime(data: Mapping[str, Any], field: str) -> datetime | None:
    value = _optional_string(data, field)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise NetBirdSchemaError(
            f"NetBird peer {field} must be an ISO 8601 timestamp"
        ) from err
    if parsed.tzinfo is None:
        raise NetBirdSchemaError(f"NetBird peer {field} must include a timezone offset")
    return parsed


def _optional_string_tuple(data: Mapping[str, Any], field: str) -> tuple[str, ...]:
    value = data.get(field)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise NetBirdSchemaError(
            f"NetBird peer {field} must be a list of strings or null"
        )
    return tuple(value)


def _parse_peer(data: Mapping[str, Any]) -> NetBirdPeer:
    """Normalize one peer while tolerating omitted optional fields."""
    return NetBirdPeer(
        id=_required_identifier(data, "peer"),
        name=_optional_string(data, "name"),
        created_at=_optional_timestamp(data, "created_at"),
        ip=_optional_string(data, "ip"),
        ipv6=_optional_string(data, "ipv6"),
        connection_ip=_optional_string(data, "connection_ip"),
        connected=_optional_bool(data, "connected"),
        last_seen=_optional_timestamp(data, "last_seen"),
        os=_optional_string(data, "os"),
        kernel_version=_optional_string(data, "kernel_version"),
        geoname_id=_optional_int(data, "geoname_id"),
        version=_optional_string(data, "version"),
        ssh_enabled=_optional_bool(data, "ssh_enabled"),
        user_id=_optional_string(data, "user_id"),
        hostname=_optional_string(data, "hostname"),
        ui_version=_optional_string(data, "ui_version"),
        dns_label=_optional_string(data, "dns_label"),
        login_expiration_enabled=_optional_bool(data, "login_expiration_enabled"),
        login_expired=_optional_bool(data, "login_expired"),
        last_login=_optional_timestamp(data, "last_login"),
        inactivity_expiration_enabled=_optional_bool(
            data, "inactivity_expiration_enabled"
        ),
        approval_required=_optional_bool(data, "approval_required"),
        country_code=_optional_string(data, "country_code"),
        city_name=_optional_string(data, "city_name"),
        serial_number=_optional_string(data, "serial_number"),
        extra_dns_labels=_optional_string_tuple(data, "extra_dns_labels"),
        ephemeral=_optional_bool(data, "ephemeral"),
        accessible_peers_count=_optional_int(data, "accessible_peers_count"),
    )


def _parse_network(data: Mapping[str, Any]) -> NetBirdNetwork:
    return NetBirdNetwork(
        id=_required_identifier(data, "network"),
        name=_required_string(data, "name", "network"),
        description=_optional_string(data, "description"),
    )


def _parse_resource(data: Mapping[str, Any], network_id: str) -> NetBirdResource:
    return NetBirdResource(
        id=_required_identifier(data, "resource"),
        network_id=network_id,
        name=_required_string(data, "name", "resource"),
        address=_required_string(data, "address", "resource"),
        type=_required_string(data, "type", "resource"),
        enabled=_required_bool(data, "enabled", "resource"),
    )


def _parse_router(data: Mapping[str, Any], network_id: str) -> NetBirdRouter:
    peer_group_ids = _optional_string_tuple(data, "peer_groups")
    return NetBirdRouter(
        id=_required_identifier(data, "router"),
        network_id=network_id,
        enabled=_required_bool(data, "enabled", "router"),
        peer_id=_optional_string(data, "peer"),
        peer_group_ids=peer_group_ids,
    )


def _optional_timestamp(data: Mapping[str, Any], field: str) -> datetime | None:
    """Treat an invalid optional timestamp as unknown, not a bad snapshot."""
    try:
        value = _optional_datetime(data, field)
    except NetBirdSchemaError:
        return None
    return value.astimezone(UTC) if value is not None else None
