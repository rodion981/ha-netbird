"""Contract tests for the dependency-free NetBird dashboard example."""

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

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


def test_dashboard_jinja_is_valid(hass: HomeAssistant) -> None:
    dashboard = yaml.safe_load(DASHBOARD.read_text(encoding="utf-8"))
    content = dashboard["views"][0]["cards"][0]["content"]

    Template(content, hass).ensure_valid()
