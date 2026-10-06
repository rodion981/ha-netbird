"""Config flow for the NetBird integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any, override

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .api import (
    NetBirdAddressError,
    NetBirdApiClient,
    NetBirdAuthenticationError,
    NetBirdDataError,
    NetBirdPermissionError,
    NetBirdRedirectError,
    NetBirdResponseError,
    NetBirdTlsError,
    NetBirdUpdateError,
)
from .const import (
    API_BASE_URL,
    CONF_ACCOUNT_ID,
    CONF_API_TOKEN,
    CONF_API_URL,
    CONF_CA_CERTIFICATE,
    CONF_DASHBOARD_URL,
    CONF_DEPLOYMENT_TYPE,
    DASHBOARD_BASE_URL,
    DEPLOYMENT_CLOUD,
    DEPLOYMENT_SELF_HOSTED,
    DOMAIN,
    TOPOLOGY_REQUEST_CONCURRENCY,
)
from .deployment import (
    NetBirdBlockedAddressError,
    NetBirdCertificateError,
    NetBirdDeployment,
    NetBirdDeploymentError,
    NetBirdResolutionError,
    NetBirdUrlError,
    async_resolve_deployment,
    async_validate_https_origin,
    build_ssl_context,
)
from .models import NetBirdSnapshot
from .transport import async_netbird_session

_LOGGER = logging.getLogger(__name__)

_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_TOKEN): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
    }
)

_SELF_HOSTED_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_URL): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
        ),
        vol.Optional(CONF_DASHBOARD_URL): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
        ),
        vol.Required(CONF_API_TOKEN): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_CA_CERTIFICATE): selector.TextSelector(
            selector.TextSelectorConfig(multiline=True)
        ),
    }
)


class NetBirdConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle NetBird Cloud and self-hosted configuration."""

    VERSION = 3

    async def _async_validate_connection(
        self,
        token: str,
        deployment: NetBirdDeployment,
        *,
        full_contract: bool,
    ) -> tuple[NetBirdSnapshot | None, str | None]:
        """Validate a PAT without exposing credentials or response data."""
        try:
            async with async_netbird_session(self.hass, deployment) as session:
                client = NetBirdApiClient(
                    session,
                    token,
                    base_url=deployment.api_url,
                    ssl_context=deployment.ssl_context,
                )
                snapshot = await client.async_get_snapshot()
                if full_contract:
                    await _async_validate_topology_contract(client)
                return snapshot, None
        except NetBirdAuthenticationError:
            return None, "invalid_auth"
        except NetBirdPermissionError:
            return None, "insufficient_permissions"
        except NetBirdRedirectError:
            return None, "redirect_not_allowed"
        except NetBirdTlsError:
            return None, "invalid_tls"
        except NetBirdAddressError:
            return None, "blocked_address"
        except NetBirdResponseError as err:
            if full_contract and err.status == 404:
                return None, "unsupported_server"
            return None, "cannot_connect"
        except NetBirdDataError:
            return None, "invalid_response"
        except NetBirdUpdateError:
            return None, "cannot_connect"
        except Exception as err:
            _LOGGER.error(
                "Unexpected error while validating NetBird credentials (%s)",
                type(err).__name__,
            )
            return None, "unknown"

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a deployment profile."""
        return self.async_show_menu(
            step_id="user", menu_options=[DEPLOYMENT_CLOUD, DEPLOYMENT_SELF_HOSTED]
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure NetBird Cloud."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN]
            deployment = NetBirdDeployment(
                deployment_type=DEPLOYMENT_CLOUD,
                api_url=API_BASE_URL,
                dashboard_url=DASHBOARD_BASE_URL,
                ssl_context=None,
                custom_ca=False,
            )
            snapshot, error = await self._async_validate_connection(
                token, deployment, full_contract=False
            )
            if error is None:
                assert snapshot is not None
                await self.async_set_unique_id(snapshot.account.id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="NetBird Cloud",
                    data={
                        CONF_ACCOUNT_ID: snapshot.account.id,
                        CONF_API_TOKEN: token,
                        CONF_DEPLOYMENT_TYPE: DEPLOYMENT_CLOUD,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="cloud", data_schema=_TOKEN_SCHEMA, errors=errors
        )

    async def async_step_self_hosted(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a self-hosted NetBird deployment."""
        errors: dict[str, str] = {}
        if user_input is not None:
            deployment, error = await self._async_prepare_self_hosted(user_input)
            snapshot = None
            if error is None:
                assert deployment is not None
                snapshot, error = await self._async_validate_connection(
                    user_input[CONF_API_TOKEN], deployment, full_contract=True
                )
            if error is None:
                assert deployment is not None
                assert snapshot is not None
                await self.async_set_unique_id(snapshot.account.id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="NetBird Self-hosted",
                    data=_self_hosted_entry_data(user_input, deployment, snapshot),
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="self_hosted", data_schema=_SELF_HOSTED_SCHEMA, errors=errors
        )

    async def _async_prepare_self_hosted(
        self, user_input: Mapping[str, Any]
    ) -> tuple[NetBirdDeployment | None, str | None]:
        """Validate self-hosted URLs and an optional custom CA."""
        try:
            api_url = await async_validate_https_origin(
                self.hass, user_input[CONF_API_URL]
            )
            dashboard_input = user_input.get(CONF_DASHBOARD_URL)
            dashboard_url = (
                await async_validate_https_origin(self.hass, dashboard_input)
                if dashboard_input
                else None
            )
            ca_certificate = user_input.get(CONF_CA_CERTIFICATE)
            ssl_context = await self.hass.async_add_executor_job(
                build_ssl_context, ca_certificate
            )
        except NetBirdBlockedAddressError:
            return None, "blocked_address"
        except NetBirdUrlError:
            return None, "invalid_url"
        except NetBirdCertificateError:
            return None, "invalid_ca"
        return (
            NetBirdDeployment(
                deployment_type=DEPLOYMENT_SELF_HOSTED,
                api_url=api_url,
                dashboard_url=dashboard_url,
                ssl_context=ssl_context,
                custom_ca=ssl_context is not None,
            ),
            None,
        )

    async def async_step_reauth(
        self, _entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication for an existing entry."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and store a replacement PAT."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN]
            deployment: NetBirdDeployment | None = None
            snapshot: NetBirdSnapshot | None = None
            error: str | None
            try:
                deployment = await async_resolve_deployment(
                    self.hass, self._get_reauth_entry().data
                )
            except NetBirdBlockedAddressError:
                error = "blocked_address"
            except NetBirdCertificateError:
                error = "invalid_ca"
            except NetBirdResolutionError:
                error = "cannot_connect"
            except NetBirdDeploymentError:
                error = "invalid_url"
            else:
                snapshot, error = await self._async_validate_connection(
                    token, deployment, full_contract=False
                )
            if error is None:
                assert deployment is not None
                assert snapshot is not None
                await self.async_set_unique_id(snapshot.account.id)
                self._abort_if_unique_id_mismatch(reason="reauth_account_mismatch")
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={
                        CONF_ACCOUNT_ID: snapshot.account.id,
                        CONF_API_TOKEN: token,
                        CONF_DEPLOYMENT_TYPE: deployment.deployment_type,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=_TOKEN_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Atomically update credentials and deployment settings."""
        entry = self._get_reconfigure_entry()
        deployment_type = entry.data.get(CONF_DEPLOYMENT_TYPE, DEPLOYMENT_CLOUD)
        if deployment_type == DEPLOYMENT_SELF_HOSTED:
            return await self._async_step_reconfigure_self_hosted(entry, user_input)

        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN]
            deployment = NetBirdDeployment(
                deployment_type=DEPLOYMENT_CLOUD,
                api_url=API_BASE_URL,
                dashboard_url=DASHBOARD_BASE_URL,
                ssl_context=None,
                custom_ca=False,
            )
            snapshot, error = await self._async_validate_connection(
                token, deployment, full_contract=False
            )
            if error is None:
                assert snapshot is not None
                await self.async_set_unique_id(snapshot.account.id)
                self._abort_if_unique_id_mismatch(reason="reconfigure_account_mismatch")
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates={
                        CONF_ACCOUNT_ID: snapshot.account.id,
                        CONF_API_TOKEN: token,
                        CONF_DEPLOYMENT_TYPE: DEPLOYMENT_CLOUD,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure", data_schema=_TOKEN_SCHEMA, errors=errors
        )

    async def _async_step_reconfigure_self_hosted(
        self,
        entry: ConfigEntry[Any],
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Validate and atomically replace a self-hosted profile."""
        errors: dict[str, str] = {}
        if user_input is not None:
            deployment, error = await self._async_prepare_self_hosted(user_input)
            snapshot = None
            if error is None:
                assert deployment is not None
                snapshot, error = await self._async_validate_connection(
                    user_input[CONF_API_TOKEN], deployment, full_contract=True
                )
            if error is None:
                assert deployment is not None
                assert snapshot is not None
                await self.async_set_unique_id(snapshot.account.id)
                self._abort_if_unique_id_mismatch(reason="reconfigure_account_mismatch")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=_self_hosted_entry_data(
                        user_input, deployment, snapshot
                    ),
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_self_hosted_schema(entry.data),
            errors=errors,
        )


async def _async_validate_topology_contract(client: NetBirdApiClient) -> None:
    """Require every currently consumed topology endpoint and schema."""
    networks = await client.async_get_networks()
    semaphore = asyncio.Semaphore(TOPOLOGY_REQUEST_CONCURRENCY)

    async def validate_resources(network_id: str) -> None:
        async with semaphore:
            await client.async_get_network_resources(network_id)

    async def validate_routers(network_id: str) -> None:
        async with semaphore:
            await client.async_get_network_routers(network_id)

    await asyncio.gather(
        *(validate_resources(network.id) for network in networks),
        *(validate_routers(network.id) for network in networks),
    )


def _self_hosted_entry_data(
    user_input: Mapping[str, Any],
    deployment: NetBirdDeployment,
    snapshot: NetBirdSnapshot,
) -> dict[str, Any]:
    """Return normalized, explicit self-hosted config entry data."""
    return {
        CONF_ACCOUNT_ID: snapshot.account.id,
        CONF_API_TOKEN: user_input[CONF_API_TOKEN],
        CONF_DEPLOYMENT_TYPE: DEPLOYMENT_SELF_HOSTED,
        CONF_API_URL: deployment.api_url,
        CONF_DASHBOARD_URL: deployment.dashboard_url or "",
        CONF_CA_CERTIFICATE: user_input.get(CONF_CA_CERTIFICATE, ""),
    }


def _self_hosted_schema(data: Mapping[str, Any]) -> vol.Schema:
    """Return the self-hosted reconfigure form with current connection values."""
    return vol.Schema(
        {
            vol.Required(
                CONF_API_URL,
                default=data.get(CONF_API_URL, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
            ),
            vol.Optional(
                CONF_DASHBOARD_URL,
                default=data.get(CONF_DASHBOARD_URL, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
            ),
            vol.Required(CONF_API_TOKEN): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_CA_CERTIFICATE,
                default=data.get(CONF_CA_CERTIFICATE, ""),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        }
    )
