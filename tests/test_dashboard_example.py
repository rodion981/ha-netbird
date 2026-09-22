"""Contract tests for the dependency-free NetBird dashboard example."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml  # type: ignore[import-untyped]
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.const import CONF_ACCOUNT_ID, CONF_API_TOKEN, DOMAIN
from custom_components.netbird.models import (
    NetBirdAccount,
    NetBirdNetwork,
    NetBirdPeer,
    NetBirdResource,
    NetBirdRouter,
)

ROOT = Path(__file__).parents[1]
DASHBOARD = ROOT / "examples" / "netbird-dashboard.yaml"


def test_dashboard_uses_native_dynamic_discovery() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    dashboard = yaml.safe_load(source)

    assert isinstance(dashboard, dict)
    assert "custom:auto-entities" not in source
    assert 'integration_entities("netbird")' in source
    assert "netbird_key" in source
    assert "Peers" in source
    assert "Networks" in source
    assert "Network resources" in source
    assert "device_id(" in source
    assert "device_entities(" in source


def test_dashboard_jinja_is_valid_and_empty_state_renders(
    hass: HomeAssistant,
) -> None:
    dashboard = yaml.safe_load(DASHBOARD.read_text(encoding="utf-8"))
    content = dashboard["views"][0]["cards"][0]["content"]
    template = Template(content, hass)

    template.ensure_valid()
    rendered = template.async_render(parse_result=False)
    assert "No peer entities" in rendered
    assert "No networks" in rendered
    assert "No network resources" in rendered


async def test_dashboard_populated_tables_have_contiguous_rows(
    hass: HomeAssistant,
) -> None:
    """Rendered table rows immediately follow their Markdown delimiters."""
    account_id = "dashboard-account"
    network = NetBirdNetwork("network-1", "Home LAN")
    resource = NetBirdResource(
        "resource-1", "network-1", "Home subnet", "192.0.2.0/24", "subnet", True
    )
    router = NetBirdRouter("router-1", "network-1", True, peer_id="peer-1")
    with patch("custom_components.netbird.NetBirdApiClient") as client_class:
        client = client_class.return_value
        client.async_get_account = AsyncMock(return_value=NetBirdAccount(account_id))
        client.async_get_peers = AsyncMock(
            return_value=(
                NetBirdPeer(
                    "peer-1",
                    name="Demo peer",
                    ip="192.0.2.10",
                    connected=True,
                    accessible_peers_count=1,
                ),
            )
        )
        client.async_get_networks = AsyncMock(return_value=(network,))
        client.async_get_network_resources = AsyncMock(return_value=(resource,))
        client.async_get_network_routers = AsyncMock(return_value=(router,))
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_ACCOUNT_ID: account_id, CONF_API_TOKEN: "test-token"},
            unique_id=account_id,
            version=2,
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dashboard = yaml.safe_load(DASHBOARD.read_text(encoding="utf-8"))
    content = dashboard["views"][0]["cards"][0]["content"]
    rendered = Template(content, hass).async_render(parse_result=False)

    assert ("|:--|:--:|:--|:--|:--|--:|:--:|:--:|:--:|:--:|\n| Demo peer |") in rendered
    assert "|:--|--:|--:|--:|--:|--:|\n| Home LAN |" in rendered
    assert "|:--|:--|:--:|:--|:--|\n| Home subnet | Home LAN |" in rendered
