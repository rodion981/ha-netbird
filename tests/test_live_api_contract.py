"""Offline tests for the manual live API contract gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import live_api_contract as contract
from scripts.live_api_contract import (
    ContractError,
    validate_accounts,
    validate_networks,
    validate_peers,
    validate_resources,
    validate_routers,
)

ROOT = Path(__file__).parents[1]

GROUP = {
    "id": "group-sentinel",
    "name": "name-sentinel",
    "peers_count": 1,
    "resources_count": 1,
    "issued": "api",
}


def test_documented_live_shapes_validate_without_returning_payload_data() -> None:
    """Validators retain only internal IDs and aggregate coverage counts."""
    validate_accounts([{"id": "account-sentinel", "settings": {}}])
    assert validate_peers([{"id": "peer-sentinel", "groups": [GROUP]}]) == 1
    assert validate_networks(
        [
            {
                "id": "network-sentinel",
                "name": "name-sentinel",
                "description": None,
                "routers": [],
                "resources": [],
                "policies": [],
                "routing_peers_count": 1,
            }
        ]
    ) == ("network-sentinel",)
    assert (
        validate_resources(
            [
                {
                    "id": "resource-sentinel",
                    "type": "subnet",
                    "groups": [GROUP],
                    "name": "name-sentinel",
                    "description": None,
                    "address": "192.0.2.0/24",
                    "enabled": True,
                }
            ]
        )
        == 1
    )
    assert validate_routers(
        [
            {
                "id": "router-sentinel",
                "peer": None,
                "peer_groups": ["group-sentinel"],
                "metric": 100,
                "masquerade": True,
                "enabled": True,
            }
        ]
    ) == (1, 1)


def test_contract_failures_never_include_live_values() -> None:
    """Malformed production values cannot enter the safe failure message."""
    secret_value = "private-name-address-or-token-sentinel"
    with pytest.raises(ContractError) as error:
        validate_peers(
            [
                {
                    "id": "peer-sentinel",
                    "groups": [{**GROUP, "peers_count": secret_value}],
                }
            ]
        )

    assert str(error.value) == "PEER_GROUP_SCHEMA"
    assert secret_value not in str(error.value)


def test_missing_environment_secret_fails_before_any_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing protected secret produces only a fixed preflight failure."""
    monkeypatch.delenv("NETBIRD_LIVE_API_TOKEN", raising=False)
    monkeypatch.setattr(
        contract,
        "_request_json",
        lambda _token, _path: pytest.fail("request must not run"),
    )

    assert contract.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "live_contract_result=fail code=MISSING_ENVIRONMENT_SECRET\n"


def test_workflow_is_manual_environment_gated_and_non_persistent() -> None:
    """Static workflow contract excludes automatic triggers and data retention."""
    workflow = (ROOT / ".github/workflows/live-api-contract.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert all(
        trigger not in workflow
        for trigger in ("pull_request:", "push:", "schedule:", "workflow_run:")
    )
    assert "permissions:\n  contents: read" in workflow
    assert "environment: netbird-live-contract" in workflow
    assert "NETBIRD_LIVE_API_TOKEN: ${{ secrets.NETBIRD_LIVE_API_TOKEN }}" in workflow
    assert "actions/upload-artifact" not in workflow
    assert "cache:" not in workflow
    assert "setup-uv" not in workflow
