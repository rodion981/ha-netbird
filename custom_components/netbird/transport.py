"""Connection-time address validation for self-hosted NetBird."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import override

from aiohttp import ClientSession, TCPConnector
from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import (
    SERVER_SOFTWARE,
    async_get_clientsession,
)

from .const import DEPLOYMENT_CLOUD, TOPOLOGY_REQUEST_CONCURRENCY
from .deployment import NetBirdDeployment, _reject_blocked_ip


class NetBirdResolver(ThreadedResolver):
    """Validate every address returned to the actual connection attempt."""

    @override
    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        results = await super().resolve(host, port, family)
        for result in results:
            _reject_blocked_ip(ipaddress.ip_address(result["host"]))
        return results


@callback
def async_get_netbird_session(
    hass: HomeAssistant, deployment: NetBirdDeployment
) -> ClientSession:
    """Return HA's Cloud session or an owned session with a guarded resolver."""
    if deployment.deployment_type == DEPLOYMENT_CLOUD:
        return async_get_clientsession(hass)
    # HA's session factory fixes its connector, so it cannot inject this resolver.
    # The caller owns this session and must close it after validation or on unload.
    return ClientSession(
        connector=TCPConnector(
            resolver=NetBirdResolver(),
            ssl=deployment.ssl_context or True,
            limit_per_host=TOPOLOGY_REQUEST_CONCURRENCY,
        ),
        headers={"User-Agent": SERVER_SOFTWARE},
    )


@asynccontextmanager
async def async_netbird_session(
    hass: HomeAssistant, deployment: NetBirdDeployment
) -> AsyncIterator[ClientSession]:
    """Own self-hosted flow sessions without closing HA's shared Cloud session."""
    session = async_get_netbird_session(hass, deployment)
    try:
        yield session
    finally:
        if deployment.deployment_type != DEPLOYMENT_CLOUD:
            await session.close()
