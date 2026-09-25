"""Repository metadata, documentation, and translation contracts."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "netbird"
DOCUMENTATION_PATHS = (
    ROOT / "README.md",
    ROOT / "README.uk.md",
    ROOT / "docs" / "QUALITY_SCALE.md",
)
DOCUMENTATION_CONTRACT_PATTERN = re.compile(
    r"<!-- netbird-doc-contract: (?P<contract>\{.*\}) -->"
)
EXPECTED_ENDPOINTS = (
    "/api/accounts",
    "/api/peers",
    "/api/networks",
    "/api/networks/{id}/resources",
    "/api/networks/{id}/routers",
)
LIVE_CONTRACT_RUN_URL = (
    "https://github.com/rodion981/ha-netbird/actions/runs/36159603786/job/108170984157"
)


def _read(path: Path) -> str:
    """Read one UTF-8 repository document."""
    return path.read_text(encoding="utf-8")


def _documentation_contract(path: Path) -> dict[str, Any]:
    """Read the single semantic documentation contract marker."""
    matches = DOCUMENTATION_CONTRACT_PATTERN.findall(_read(path))
    assert len(matches) == 1, f"{path.name}: expected one documentation contract"
    contract = json.loads(matches[0])
    assert isinstance(contract, dict), f"{path.name}: contract must be an object"
    return contract


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


def test_release_versions_match() -> None:
    """Manifest, project, lock, and documentation versions stay aligned."""
    manifest = json.loads(_read(INTEGRATION / "manifest.json"))
    pyproject = tomllib.loads(_read(ROOT / "pyproject.toml"))
    lockfile = tomllib.loads(_read(ROOT / "uv.lock"))
    locked_project = next(
        package for package in lockfile["package"] if package["name"] == "ha-netbird"
    )
    documented_versions = {
        _documentation_contract(path)["release"] for path in DOCUMENTATION_PATHS
    }

    assert documented_versions == {
        manifest["version"],
        pyproject["project"]["version"],
        locked_project["version"],
    }


def test_bilingual_readmes_keep_shared_monitoring_contract() -> None:
    """English and Ukrainian docs retain the same material monitoring facts."""
    readme = _read(ROOT / "README.md")
    readme_uk = _read(ROOT / "README.uk.md")

    assert _documentation_contract(ROOT / "README.md") == _documentation_contract(
        ROOT / "README.uk.md"
    )
    assert "auto-entities" not in readme.casefold()
    assert "auto-entities" not in readme_uk.casefold()
    for text in (readme, readme_uk):
        assert "Networks" in text
        assert "Recorder" in text
        assert "1 + 2N" in text


def test_documentation_endpoint_inventory_is_current() -> None:
    """Every public contract names exactly the shipped endpoint inventory."""
    for path in DOCUMENTATION_PATHS:
        contract = _documentation_contract(path)
        assert tuple(contract["endpoints"]) == EXPECTED_ENDPOINTS, path.name
        text = _read(path)
        for endpoint_path in EXPECTED_ENDPOINTS:
            assert endpoint_path in text


def test_documentation_limitations_and_evidence_are_current() -> None:
    """Limitations and evidence classes remain explicit and equivalent."""
    expected = {
        "group_router_resolution": "unsupported",
        "evidence": ["mocked-tests", "hosted-ci", "manual-live"],
    }
    for path in DOCUMENTATION_PATHS:
        contract = _documentation_contract(path)
        assert {key: contract[key] for key in expected} == expected, path.name
        assert LIVE_CONTRACT_RUN_URL in _read(path), path.name


def test_public_distribution_contract_uses_local_facts() -> None:
    """HACS, branding, and release claims have checked-in evidence."""
    manifest = json.loads(_read(INTEGRATION / "manifest.json"))
    hacs = json.loads(_read(ROOT / "hacs.json"))
    version = manifest["version"]
    expected_distribution = {
        "distribution": ["hacs-custom", "manual"],
        "branding": "included",
    }

    assert hacs["name"] == manifest["name"]
    assert hacs["render_readme"] is True
    assert (
        (INTEGRATION / "brand" / "icon.png")
        .read_bytes()
        .startswith(b"\x89PNG\r\n\x1a\n")
    )
    for path in DOCUMENTATION_PATHS:
        contract = _documentation_contract(path)
        assert {
            key: contract[key] for key in expected_distribution
        } == expected_distribution, path.name
    for path in DOCUMENTATION_PATHS[:2]:
        text = _read(path)
        assert "my.home-assistant.io/redirect/hacs_repository/" in text
        assert f"github.com/rodion981/ha-netbird/releases/tag/v{version}" in text


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
