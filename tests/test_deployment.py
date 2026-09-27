"""Tests for safe Cloud and self-hosted deployment profiles."""

from __future__ import annotations

import socket
import ssl
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.netbird.const import (
    API_BASE_URL,
    CONF_API_URL,
    CONF_CA_CERTIFICATE,
    CONF_DASHBOARD_URL,
    CONF_DEPLOYMENT_TYPE,
    DASHBOARD_BASE_URL,
    DEPLOYMENT_CLOUD,
    DEPLOYMENT_SELF_HOSTED,
)
from custom_components.netbird.deployment import (
    NetBirdBlockedAddressError,
    NetBirdCertificateError,
    NetBirdUrlError,
    async_resolve_deployment,
    async_validate_https_origin,
    build_ssl_context,
    normalize_https_origin,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://NetBird.Example/", "https://netbird.example"),
        ("https://netbird.example:443", "https://netbird.example"),
        ("https://netbird.example:8443", "https://netbird.example:8443"),
        ("https://[2001:db8::1]:8443", "https://[2001:db8::1]:8443"),
    ],
)
def test_normalize_https_origin(value: str, expected: str) -> None:
    assert normalize_https_origin(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://netbird.example",
        "https://user:pass@netbird.example",
        "https://netbird.example/api",
        "https://netbird.example?query=yes",
        "https://netbird.example/#fragment",
        "https://netbird.example\x7f",
    ],
)
def test_rejects_non_origin_or_non_https_urls(value: str) -> None:
    with pytest.raises(NetBirdUrlError):
        normalize_https_origin(value)


@pytest.mark.parametrize("value", ["", "https://netbird.example:99999"])
def test_rejects_empty_or_invalid_port(value: str) -> None:
    with pytest.raises(NetBirdUrlError):
        normalize_https_origin(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1",
        "https://[::1]",
        "https://[::ffff:127.0.0.1]",
        "https://169.254.1.1",
    ],
)
def test_rejects_blocked_literal_addresses(value: str) -> None:
    with pytest.raises(NetBirdBlockedAddressError):
        normalize_https_origin(value)


async def test_rejects_hostname_resolving_to_blocked_address(
    hass: HomeAssistant,
) -> None:
    result = [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("127.0.0.1", 443),
        )
    ]
    with (
        patch(
            "custom_components.netbird.deployment.socket.getaddrinfo",
            return_value=result,
        ),
        pytest.raises(NetBirdBlockedAddressError),
    ):
        await async_validate_https_origin(hass, "https://netbird.example")


async def test_hostname_resolution_success_and_failures(hass: HomeAssistant) -> None:
    public_result = [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("192.0.2.10", 443),
        )
    ]
    with patch(
        "custom_components.netbird.deployment.socket.getaddrinfo",
        return_value=public_result,
    ):
        assert (
            await async_validate_https_origin(hass, "https://netbird.example/")
            == "https://netbird.example"
        )
    with (
        patch(
            "custom_components.netbird.deployment.socket.getaddrinfo",
            side_effect=OSError,
        ),
        pytest.raises(NetBirdUrlError),
    ):
        await async_validate_https_origin(hass, "https://netbird.example")
    with (
        patch(
            "custom_components.netbird.deployment.socket.getaddrinfo", return_value=[]
        ),
        pytest.raises(NetBirdUrlError),
    ):
        await async_validate_https_origin(hass, "https://netbird.example")


def test_custom_ca_builds_verifying_context_without_private_key() -> None:
    context = MagicMock(spec=ssl.SSLContext)
    with patch(
        "custom_components.netbird.deployment.ssl.create_default_context",
        return_value=context,
    ):
        assert build_ssl_context("-----BEGIN CERTIFICATE-----\nTEST\n") is context
    context.load_verify_locations.assert_called_once_with(
        cadata="-----BEGIN CERTIFICATE-----\nTEST\n"
    )


def test_custom_ca_rejects_private_key_material() -> None:
    with pytest.raises(NetBirdCertificateError):
        build_ssl_context("-----BEGIN PRIVATE KEY-----\nsecret")


def test_custom_ca_rejects_malformed_and_oversized_bundles() -> None:
    with pytest.raises(NetBirdCertificateError):
        build_ssl_context("not a certificate")
    with pytest.raises(NetBirdCertificateError):
        build_ssl_context("x" * 65_537)


async def test_resolve_cloud_defaults_for_legacy_entry(hass: HomeAssistant) -> None:
    deployment = await async_resolve_deployment(hass, {})

    assert deployment.deployment_type == DEPLOYMENT_CLOUD
    assert deployment.api_url == API_BASE_URL
    assert deployment.dashboard_url == DASHBOARD_BASE_URL
    assert deployment.ssl_context is None
    assert deployment.custom_ca is False


async def test_resolve_explicit_self_hosted_profile(hass: HomeAssistant) -> None:
    deployment = await async_resolve_deployment(
        hass,
        {
            CONF_DEPLOYMENT_TYPE: DEPLOYMENT_SELF_HOSTED,
            CONF_API_URL: "https://NETBIRD.example:443/",
            CONF_DASHBOARD_URL: "",
            CONF_CA_CERTIFICATE: "",
        },
    )

    assert deployment.api_url == "https://netbird.example"
    assert deployment.dashboard_url is None
    assert deployment.custom_ca is False


@pytest.mark.parametrize(
    "data",
    [
        {CONF_DEPLOYMENT_TYPE: "invalid"},
        {CONF_DEPLOYMENT_TYPE: DEPLOYMENT_SELF_HOSTED},
        {
            CONF_DEPLOYMENT_TYPE: DEPLOYMENT_SELF_HOSTED,
            CONF_API_URL: "https://netbird.example",
            CONF_DASHBOARD_URL: 123,
        },
        {
            CONF_DEPLOYMENT_TYPE: DEPLOYMENT_SELF_HOSTED,
            CONF_API_URL: "https://netbird.example",
            CONF_CA_CERTIFICATE: 123,
        },
    ],
)
async def test_resolve_rejects_invalid_stored_profile(
    hass: HomeAssistant, data: dict[str, object]
) -> None:
    with pytest.raises((NetBirdUrlError, NetBirdCertificateError, ValueError)):
        await async_resolve_deployment(hass, data)
