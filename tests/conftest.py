"""Shared fixtures for NetBird integration tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable loading custom integrations in Home Assistant tests."""
    return


@pytest.fixture
def load_netbird_fixture() -> Callable[[str], Any]:
    """Return a loader for JSON fixtures from the NetBird fixture directory."""

    def _load(filename: str) -> Any:
        fixture_path = FIXTURES_DIR / filename
        return json.loads(fixture_path.read_text(encoding="utf-8"))

    return _load
