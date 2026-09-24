"""Validate live NetBird Cloud shapes without logging response data."""

from __future__ import annotations

import json
import os
import ssl
import sys
from collections.abc import Mapping
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from typing import Final, Never, cast
from urllib.parse import quote

API_HOST: Final = "api.netbird.io"
MAX_RESPONSE_BYTES: Final = 5 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS: Final = 10
CONTRACT_REVISION: Final = 3
API_CONTRACT_CONTEXT: Final = "unversioned-cloud"


class ContractError(Exception):
    """A failure containing only a fixed, non-sensitive code."""


def _fail(code: str) -> Never:
    raise ContractError(code)


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        _fail(code)
    return cast(Mapping[str, object], value)


def _items(value: object, code: str) -> list[object]:
    if not isinstance(value, list):
        _fail(code)
    return cast(list[object], value)


def _required_string(data: Mapping[str, object], field: str, code: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        _fail(code)
    return value


def _required_bool(data: Mapping[str, object], field: str, code: str) -> None:
    if type(data.get(field)) is not bool:
        _fail(code)


def _required_int(data: Mapping[str, object], field: str, code: str) -> None:
    if type(data.get(field)) is not int:
        _fail(code)


def _optional_fields(
    data: Mapping[str, object],
    *,
    strings: tuple[str, ...] = (),
    booleans: tuple[str, ...] = (),
    integers: tuple[str, ...] = (),
    code: str,
) -> None:
    for field in strings:
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            _fail(code)
    for field in booleans:
        value = data.get(field)
        if value is not None and type(value) is not bool:
            _fail(code)
    for field in integers:
        value = data.get(field)
        if value is not None and type(value) is not int:
            _fail(code)


def _string_list(value: object, code: str) -> tuple[str, ...]:
    values = _items(value, code)
    if not all(isinstance(item, str) and item.strip() for item in values):
        _fail(code)
    return tuple(cast(str, item) for item in values)


def _validate_group(value: object, code_prefix: str) -> None:
    group = _mapping(value, f"{code_prefix}_ITEM_SCHEMA")
    _required_string(group, "id", f"{code_prefix}_ID_SCHEMA")
    _optional_fields(
        group,
        strings=("name", "issued"),
        integers=("peers_count", "resources_count"),
        code=f"{code_prefix}_OPTIONAL_FIELDS_SCHEMA",
    )


def validate_accounts(payload: object) -> None:
    """Validate the documented single-account response shape."""
    accounts = _items(payload, "ACCOUNTS_SCHEMA")
    if len(accounts) != 1:
        _fail("ACCOUNTS_CARDINALITY")
    account = _mapping(accounts[0], "ACCOUNTS_SCHEMA")
    _required_string(account, "id", "ACCOUNTS_SCHEMA")
    _mapping(account.get("settings"), "ACCOUNTS_SCHEMA")


def validate_peers(payload: object) -> int:
    """Validate bulk peers and return only group-reference coverage."""
    group_references = 0
    for value in _items(payload, "PEERS_SCHEMA"):
        peer = _mapping(value, "PEERS_SCHEMA")
        _required_string(peer, "id", "PEERS_SCHEMA")
        _optional_fields(
            peer,
            strings=(
                "name",
                "created_at",
                "ip",
                "ipv6",
                "connection_ip",
                "last_seen",
                "os",
                "kernel_version",
                "version",
                "user_id",
                "hostname",
                "ui_version",
                "dns_label",
                "last_login",
                "country_code",
                "city_name",
                "serial_number",
            ),
            booleans=(
                "connected",
                "ssh_enabled",
                "login_expiration_enabled",
                "login_expired",
                "inactivity_expiration_enabled",
                "approval_required",
                "ephemeral",
            ),
            integers=("geoname_id", "accessible_peers_count"),
            code="PEERS_SCHEMA",
        )
        groups = _items(peer.get("groups"), "PEER_GROUP_LIST_SCHEMA")
        for group in groups:
            _validate_group(group, "PEER_GROUP")
        group_references += len(groups)
        labels = peer.get("extra_dns_labels")
        if labels is not None:
            _string_list(labels, "PEERS_SCHEMA")
    return group_references


def validate_networks(payload: object) -> tuple[str, ...]:
    """Validate Networks and return IDs only for nested read-only calls."""
    network_ids: list[str] = []
    for value in _items(payload, "NETWORKS_SCHEMA"):
        network = _mapping(value, "NETWORKS_SCHEMA")
        network_ids.append(_required_string(network, "id", "NETWORKS_SCHEMA"))
        _required_string(network, "name", "NETWORKS_SCHEMA")
        _optional_fields(
            network,
            strings=("description",),
            integers=("routing_peers_count",),
            code="NETWORKS_SCHEMA",
        )
        for field in ("routers", "resources", "policies"):
            if field in network:
                _string_list(network[field], "NETWORKS_SCHEMA")
    return tuple(network_ids)


def validate_resources(payload: object) -> int:
    """Validate Network resources and return item coverage only."""
    resources = _items(payload, "RESOURCES_SCHEMA")
    for value in resources:
        resource = _mapping(value, "RESOURCES_SCHEMA")
        for field in ("id", "type", "name", "address"):
            _required_string(resource, field, "RESOURCES_SCHEMA")
        _optional_fields(resource, strings=("description",), code="RESOURCES_SCHEMA")
        _required_bool(resource, "enabled", "RESOURCES_SCHEMA")
        for group in _items(resource.get("groups"), "RESOURCE_GROUP_LIST_SCHEMA"):
            _validate_group(group, "RESOURCE_GROUP")
    return len(resources)


def validate_routers(payload: object) -> tuple[int, int]:
    """Validate Network routers and return item and group-router coverage."""
    routers = _items(payload, "ROUTERS_SCHEMA")
    group_router_references = 0
    for value in routers:
        router = _mapping(value, "ROUTERS_SCHEMA")
        _required_string(router, "id", "ROUTERS_SCHEMA")
        _optional_fields(router, strings=("peer",), code="ROUTERS_SCHEMA")
        peer_groups = _string_list(router.get("peer_groups"), "ROUTER_GROUP_SCHEMA")
        _required_int(router, "metric", "ROUTERS_SCHEMA")
        _required_bool(router, "masquerade", "ROUTERS_SCHEMA")
        _required_bool(router, "enabled", "ROUTERS_SCHEMA")
        group_router_references += len(peer_groups)
    return len(routers), group_router_references


def _request_json(token: str, path: str) -> object:
    connection = HTTPSConnection(
        API_HOST,
        timeout=REQUEST_TIMEOUT_SECONDS,
        context=ssl.create_default_context(),
    )
    try:
        connection.request(
            "GET",
            path,
            headers={"Accept": "application/json", "Authorization": f"Token {token}"},
        )
        response = connection.getresponse()
        if response.status != 200:
            _fail("HTTP_RESPONSE")
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            _fail("RESPONSE_SIZE")
    except ContractError:
        raise
    except HTTPException, OSError, TimeoutError, ssl.SSLError:
        _fail("TRANSPORT")
    finally:
        connection.close()

    try:
        return cast(object, json.loads(body))
    except UnicodeDecodeError, json.JSONDecodeError, TypeError:
        _fail("JSON_RESPONSE")


def _integration_version() -> str:
    manifest_path = (
        Path(__file__).parents[1] / "custom_components" / "netbird" / "manifest.json"
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        _fail("VERSION_CONTEXT")
    if not isinstance(manifest, dict):
        _fail("VERSION_CONTEXT")
    return _required_string(manifest, "version", "VERSION_CONTEXT")


def run_contract() -> None:
    """Run the fixed Cloud read-only contract and print safe evidence only."""
    token = os.environ.get("NETBIRD_LIVE_API_TOKEN")
    if token is None or not token.strip():
        _fail("MISSING_ENVIRONMENT_SECRET")

    validate_accounts(_request_json(token, "/api/accounts"))
    peer_group_references = validate_peers(_request_json(token, "/api/peers"))
    network_ids = validate_networks(_request_json(token, "/api/networks"))
    if peer_group_references == 0:
        _fail("PEER_GROUP_COVERAGE")
    if not network_ids:
        _fail("NETWORK_COVERAGE")

    resource_count = 0
    router_count = 0
    group_router_references = 0
    for network_id in network_ids:
        encoded_id = quote(network_id, safe="")
        resource_count += validate_resources(
            _request_json(token, f"/api/networks/{encoded_id}/resources")
        )
        items, group_references = validate_routers(
            _request_json(token, f"/api/networks/{encoded_id}/routers")
        )
        router_count += items
        group_router_references += group_references

    if resource_count == 0:
        _fail("RESOURCE_COVERAGE")
    if router_count == 0:
        _fail("ROUTER_COVERAGE")
    if group_router_references == 0:
        _fail("ROUTER_GROUP_COVERAGE")

    version = _integration_version()
    print(
        "live_contract_result=pass "
        f"integration_version={version} api_contract={API_CONTRACT_CONTEXT} "
        f"contract_revision={CONTRACT_REVISION}"
    )


def main() -> int:
    try:
        run_contract()
    except ContractError as error:
        print(f"live_contract_result=fail code={error}", file=sys.stderr)
        return 1
    except Exception:  # The workflow must never print raw exception details.
        print("live_contract_result=fail code=UNEXPECTED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
