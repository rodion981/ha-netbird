"""Contract tests for the dependency-free NetBird dashboard example."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml  # type: ignore[import-untyped]
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.netbird.api import NetBirdTransportError
from custom_components.netbird.const import CONF_ACCOUNT_ID, CONF_API_TOKEN, DOMAIN
from custom_components.netbird.models import (
    NetBirdAccount,
    NetBirdNetwork,
    NetBirdPeer,
    NetBirdResource,
    NetBirdRouter,
)

ROOT = Path(__file__).parents[1]
DASHBOARD_EN = ROOT / "examples" / "netbird-dashboard.yaml"
DASHBOARD_UK = ROOT / "examples" / "netbird-dashboard.uk.yaml"


def _dashboard(path: Path = DASHBOARD_EN) -> dict[str, Any]:
    """Load the dashboard example."""
    dashboard = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(dashboard, dict)
    return dashboard


def _markdown_contents(dashboard: dict[str, Any]) -> list[str]:
    """Return every native Markdown template from the Sections view."""
    return [
        card["content"]
        for section in dashboard["views"][0]["sections"]
        for card in section["cards"]
        if card["type"] == "markdown"
    ]


@pytest.mark.parametrize(
    ("path", "headings"),
    [
        (
            DASHBOARD_EN,
            ["Overview", "Peers", "Networks", "Network resources"],
        ),
        (DASHBOARD_UK, ["Огляд", "Піри", "Мережі", "Мережеві ресурси"]),
    ],
)
def test_dashboard_uses_native_dynamic_discovery(
    path: Path, headings: list[str]
) -> None:
    source = path.read_text(encoding="utf-8")
    dashboard = _dashboard(path)
    view = dashboard["views"][0]
    cards = [card for section in view["sections"] for card in section["cards"]]

    assert view["type"] == "sections"
    assert view["max_columns"] == 2
    assert {card["type"] for card in cards} == {"heading", "markdown"}
    assert [card["heading"] for card in cards if card["type"] == "heading"] == headings
    assert "custom:auto-entities" not in source
    assert 'integration_entities("netbird")' in source
    assert "netbird_key" in source
    assert "routing_available" in source
    assert "as_local" in source
    assert "device_id(" in source
    assert "device_entities(" in source
    assert "| Name |" not in source


@pytest.mark.parametrize(
    ("path", "empty_messages", "overview"),
    [
        (
            DASHBOARD_EN,
            (
                "No peer entities found",
                "No networks found",
                "No network resources found",
            ),
            "— / — peers connected",
        ),
        (
            DASHBOARD_UK,
            (
                "Пірів не знайдено",
                "Мереж не знайдено",
                "Мережевих ресурсів не знайдено",
            ),
            "— / — пірів підключено",
        ),
    ],
)
def test_dashboard_jinja_is_valid_and_empty_state_renders(
    hass: HomeAssistant,
    path: Path,
    empty_messages: tuple[str, str, str],
    overview: str,
) -> None:
    rendered_cards: list[str] = []
    for content in _markdown_contents(_dashboard(path)):
        template = Template(content, hass)
        template.ensure_valid()
        rendered_cards.append(template.async_render(parse_result=False))

    rendered = "\n".join(rendered_cards)
    for message in empty_messages:
        assert message in rendered
    assert overview in rendered


async def test_dashboard_populated_sections_are_compact_and_operational(
    hass: HomeAssistant,
) -> None:
    """Render concise mobile-safe summaries from real integration entities."""
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
                    last_seen=datetime(2026, 9, 27, 18, 16, 5, tzinfo=UTC),
                    last_login=datetime(2026, 9, 27, 17, 5, 0, tzinfo=UTC),
                    ssh_enabled=True,
                    ephemeral=False,
                    login_expired=True,
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

    rendered = "\n".join(
        Template(content, hass).async_render(parse_result=False)
        for content in _markdown_contents(_dashboard(DASHBOARD_EN))
    )
    assert "**🟢 1 / 1 peers connected" in rendered
    assert "Resources: **1 / 1 enabled" in rendered
    assert "Routers: **1 / 1 enabled" in rendered
    assert "🟢 Online · **Demo peer**" in rendered
    assert "`192.0.2.10` · Seen: 27 Sep" in rendered
    assert "· Login: 27 Sep" in rendered
    assert "Accessible: 1 · SSH: On · Ephemeral: Off · ⚠ Login expired" in rendered
    assert "**Home LAN**" in rendered
    assert "Resources: **1/1** · Routers: **1/1**" in rendered
    assert "Connected routing peers: **1**" in rendered
    assert "**Home subnet** · Home LAN" in rendered
    assert "`192.0.2.0/24` · subnet · 🟢 Routed" in rendered
    assert "2026-09-27T18:16:05+00:00" not in rendered

    rendered_uk = "\n".join(
        Template(content, hass).async_render(parse_result=False)
        for content in _markdown_contents(_dashboard(DASHBOARD_UK))
    )
    assert "**🟢 1 / 1 пірів підключено" in rendered_uk
    assert "Ресурси: **1 / 1 увімкнено" in rendered_uk
    assert "🟢 Онлайн · **Demo peer**" in rendered_uk
    assert "Доступні піри: 1 · SSH: Так · Ефемерний: Ні" in rendered_uk  # noqa: RUF001
    assert "Ресурси: **1/1** · Маршрутизатори: **1/1**" in rendered_uk
    assert "Підключені піри маршрутизації: **1**" in rendered_uk
    assert "`192.0.2.0/24` · subnet · 🟢 Маршрутизується" in rendered_uk

    connection = hass.states.get("binary_sensor.demo_peer_connection")
    ip_address = hass.states.get("sensor.demo_peer_ip_address")
    assert connection is not None
    assert ip_address is not None
    hass.states.async_set(connection.entity_id, "unavailable", connection.attributes)
    hass.states.async_set(ip_address.entity_id, "unavailable", ip_address.attributes)
    degraded = "\n".join(
        Template(content, hass).async_render(parse_result=False)
        for content in _markdown_contents(_dashboard(DASHBOARD_EN))
    )
    assert "⚫ Unavailable · **Demo peer**" in degraded
    assert "`Unavailable` · Seen: 27 Sep" in degraded

    client.async_get_network_routers.side_effect = NetBirdTransportError("safe")
    await entry.runtime_data.topology_coordinator.async_refresh()
    await hass.async_block_till_done()
    degraded_network = hass.states.get("sensor.home_lan_connected_routing_peers")
    assert degraded_network is not None
    assert degraded_network.state == "unavailable"
    assert degraded_network.attributes["netbird_key"] == "connected_routing_peers"
    degraded = "\n".join(
        Template(content, hass).async_render(parse_result=False)
        for content in _markdown_contents(_dashboard(DASHBOARD_EN))
    )
    assert "**Home LAN**" in degraded
    assert "Routers: **Unavailable/Unavailable**" in degraded
