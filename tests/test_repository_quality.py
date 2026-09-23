"""Repository metadata, documentation, and translation contracts."""

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


def test_v020_release_metadata_and_documentation() -> None:
    """Release metadata and bilingual docs describe the shipped monitoring model."""
    manifest = json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (ROOT / "uv.lock").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_uk = (ROOT / "README.uk.md").read_text(encoding="utf-8")

    assert manifest["version"] == "0.2.0"
    assert 'version = "0.2.0"' in pyproject
    assert 'name = "ha-netbird"\nversion = "0.2.0"' in lockfile
    assert "auto-entities" not in readme.casefold()
    assert "auto-entities" not in readme_uk.casefold()
    for text in (readme, readme_uk):
        assert "Networks" in text
        assert "Recorder" in text
        assert "1 + 2N" in text


def test_v020_documentation_contract_is_current() -> None:
    """Public documentation describes the complete shipped v0.2.0 contract."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_uk = (ROOT / "README.uk.md").read_text(encoding="utf-8")
    quality_scale = (ROOT / "docs" / "QUALITY_SCALE.md").read_text(encoding="utf-8")
    endpoint_paths = (
        "/api/accounts",
        "/api/peers",
        "/api/networks",
        "/api/networks/{id}/resources",
        "/api/networks/{id}/routers",
    )

    for text in (readme, readme_uk, quality_scale):
        assert "0.2.0" in text
        assert "1 + 2N" in text
        assert "live API" in text
        for endpoint_path in endpoint_paths:
            assert endpoint_path in text

    assert "Group-based routers" in readme
    assert "Групові routers" in readme_uk
    assert "Group-based routers" in quality_scale
    assert "post-`0.1.0`" not in quality_scale
    assert "branding" in quality_scale.casefold()
    assert "HACS" in quality_scale


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
