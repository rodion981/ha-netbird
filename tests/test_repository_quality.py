"""Repository metadata and translation contracts for the MVP gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "netbird"


@pytest.mark.parametrize(
    "path",
    [
        *sorted(INTEGRATION.glob("*.json")),
        *sorted((INTEGRATION / "translations").glob("*.json")),
        *sorted((ROOT / "tests" / "fixtures").glob("*.json")),
        ROOT / "hacs.json",
    ],
)
def test_all_repository_json_is_valid(path: Path) -> None:
    """Parse every integration, translation, fixture, and HACS JSON file."""
    assert json.loads(path.read_text(encoding="utf-8")) is not None


def test_ci_yaml_is_valid() -> None:
    """The checked-in quality workflow must parse as YAML."""
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    assert isinstance(workflow, dict)
    assert "jobs" in workflow


def _assert_translation_shape(reference: Any, translated: Any) -> None:
    """Require every nested key and non-empty translated leaf."""
    if isinstance(reference, dict):
        assert isinstance(translated, dict)
        assert translated.keys() == reference.keys()
        for key, value in reference.items():
            _assert_translation_shape(value, translated[key])
    elif isinstance(reference, str):
        assert isinstance(translated, str)
        assert translated.strip()
    else:
        assert translated == reference


@pytest.mark.parametrize("language", ["en", "uk"])
def test_translations_cover_all_nested_strings(language: str) -> None:
    """Every translated config, error, and entity key matches strings.json."""
    source = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    translated = json.loads(
        (INTEGRATION / "translations" / f"{language}.json").read_text(encoding="utf-8")
    )
    _assert_translation_shape(source, translated)
