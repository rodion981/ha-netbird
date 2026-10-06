"""Secure deployment profiles for NetBird Cloud and self-hosted servers."""

from __future__ import annotations

import ipaddress
import socket
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from homeassistant.core import HomeAssistant

from .const import (
    API_BASE_URL,
    CONF_API_URL,
    CONF_CA_CERTIFICATE,
    CONF_DASHBOARD_URL,
    CONF_DEPLOYMENT_TYPE,
    DASHBOARD_BASE_URL,
    DEPLOYMENT_CLOUD,
    DEPLOYMENT_SELF_HOSTED,
    MAX_CA_CERTIFICATE_BYTES,
)


class NetBirdDeploymentError(ValueError):
    """Base exception for a deployment profile that is unsafe or invalid."""


class NetBirdUrlError(NetBirdDeploymentError):
    """A deployment URL is invalid."""


class NetBirdBlockedAddressError(NetBirdUrlError):
    """A deployment URL resolves to a blocked address."""


class NetBirdCertificateError(NetBirdDeploymentError):
    """A custom CA bundle is invalid or unsafe."""


class NetBirdResolutionError(NetBirdUrlError):
    """A deployment hostname could not currently be resolved."""


@dataclass(frozen=True, slots=True)
class NetBirdDeployment:
    """Resolved connection settings for one config entry."""

    deployment_type: str
    api_url: str
    dashboard_url: str | None
    ssl_context: ssl.SSLContext | None
    custom_ca: bool


def normalize_https_origin(value: str) -> str:
    """Return a canonical HTTPS origin without paths, credentials, or fragments."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise NetBirdUrlError("NetBird URL is invalid")

    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as err:
        raise NetBirdUrlError("NetBird URL is invalid") from err

    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise NetBirdUrlError("NetBird URL must be an HTTPS origin")

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as err:
        raise NetBirdUrlError("NetBird URL hostname is invalid") from err
    _reject_blocked_literal(hostname)

    display_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = display_host if port in (None, 443) else f"{display_host}:{port}"
    normalized = SplitResult("https", netloc, "", "", "")
    return urlunsplit(normalized)


async def async_validate_https_origin(hass: HomeAssistant, value: str) -> str:
    """Normalize an origin and reject unsafe literal or resolved addresses."""
    origin = normalize_https_origin(value)
    parsed = urlsplit(origin)
    assert parsed.hostname is not None
    try:
        results = await hass.async_add_executor_job(
            socket.getaddrinfo,
            parsed.hostname,
            parsed.port or 443,
            0,
            socket.SOCK_STREAM,
        )
    except OSError as err:
        raise NetBirdResolutionError(
            "NetBird URL hostname could not be resolved"
        ) from err
    if not results:
        raise NetBirdResolutionError("NetBird URL hostname could not be resolved")
    for result in results:
        _reject_blocked_ip(ipaddress.ip_address(result[4][0]))
    return origin


def build_ssl_context(ca_certificate: str | None) -> ssl.SSLContext | None:
    """Build a verifying SSL context from an optional PEM CA bundle."""
    if ca_certificate is None or not ca_certificate.strip():
        return None
    if len(ca_certificate.encode("utf-8")) > MAX_CA_CERTIFICATE_BYTES:
        raise NetBirdCertificateError("NetBird CA bundle is too large")
    if "PRIVATE KEY" in ca_certificate.upper():
        raise NetBirdCertificateError("NetBird CA bundle must not contain a key")
    try:
        context = ssl.create_default_context()
        context.load_verify_locations(cadata=ca_certificate)
    except (OSError, ssl.SSLError) as err:
        raise NetBirdCertificateError("NetBird CA bundle is invalid") from err
    return context


async def async_resolve_deployment(
    hass: HomeAssistant, data: Mapping[str, object]
) -> NetBirdDeployment:
    """Resolve stored config entry data into safe runtime connection settings."""
    deployment_type = data.get(CONF_DEPLOYMENT_TYPE, DEPLOYMENT_CLOUD)
    if deployment_type == DEPLOYMENT_CLOUD:
        return NetBirdDeployment(
            deployment_type=DEPLOYMENT_CLOUD,
            api_url=API_BASE_URL,
            dashboard_url=DASHBOARD_BASE_URL,
            ssl_context=None,
            custom_ca=False,
        )
    if deployment_type != DEPLOYMENT_SELF_HOSTED:
        raise NetBirdDeploymentError("NetBird deployment type is invalid")

    api_value = data.get(CONF_API_URL)
    dashboard_value = data.get(CONF_DASHBOARD_URL)
    ca_value = data.get(CONF_CA_CERTIFICATE)
    if not isinstance(api_value, str):
        raise NetBirdUrlError("NetBird API URL is missing")
    api_url = normalize_https_origin(api_value)
    dashboard_url = None
    if dashboard_value not in (None, ""):
        if not isinstance(dashboard_value, str):
            raise NetBirdUrlError("NetBird dashboard URL is invalid")
        dashboard_url = normalize_https_origin(dashboard_value)
    if ca_value is not None and not isinstance(ca_value, str):
        raise NetBirdCertificateError("NetBird CA bundle is invalid")
    api_url = await async_validate_https_origin(hass, api_url)
    ssl_context = await hass.async_add_executor_job(build_ssl_context, ca_value)
    return NetBirdDeployment(
        deployment_type=DEPLOYMENT_SELF_HOSTED,
        api_url=api_url,
        dashboard_url=dashboard_url,
        ssl_context=ssl_context,
        custom_ca=ssl_context is not None,
    )


def _reject_blocked_literal(hostname: str) -> None:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    _reject_blocked_ip(address)


def _reject_blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if (
        address.is_loopback
        or address.is_unspecified
        or address.is_link_local
        or address.is_multicast
    ):
        raise NetBirdBlockedAddressError("NetBird URL uses a blocked address")
