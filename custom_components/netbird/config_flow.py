"""Config flow for the NetBird integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, override

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    NetBirdApiClient,
    NetBirdAuthenticationError,
    NetBirdDataError,
    NetBirdPermissionError,
    NetBirdUpdateError,
)
from .const import CONF_ACCOUNT_ID, CONF_API_TOKEN, DOMAIN
from .models import NetBirdSnapshot

_LOGGER = logging.getLogger(__name__)

_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_TOKEN): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
    }
)


class NetBirdConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle NetBird Cloud configuration."""

    VERSION = 1

    async def _async_validate_token(
        self, token: str
    ) -> tuple[NetBirdSnapshot | None, str | None]:
        """Validate a PAT without exposing credentials or response data."""
        client = NetBirdApiClient(async_get_clientsession(self.hass), token)
        try:
            return await client.async_get_snapshot(), None
        except NetBirdAuthenticationError:
            return None, "invalid_auth"
        except NetBirdPermissionError:
            return None, "insufficient_permissions"
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
        """Handle setup initiated by a user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN]
            snapshot, error = await self._async_validate_token(token)
            if error is None:
                assert snapshot is not None
                await self.async_set_unique_id(snapshot.account.id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="NetBird Cloud",
                    data={
                        CONF_ACCOUNT_ID: snapshot.account.id,
                        CONF_API_TOKEN: token,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user", data_schema=_TOKEN_SCHEMA, errors=errors
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
            snapshot, error = await self._async_validate_token(token)
            if error is None:
                assert snapshot is not None
                await self.async_set_unique_id(snapshot.account.id)
                self._abort_if_unique_id_mismatch(reason="reauth_account_mismatch")
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={
                        CONF_ACCOUNT_ID: snapshot.account.id,
                        CONF_API_TOKEN: token,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=_TOKEN_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow an existing account to replace its PAT manually."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN]
            snapshot, error = await self._async_validate_token(token)
            if error is None:
                assert snapshot is not None
                await self.async_set_unique_id(snapshot.account.id)
                self._abort_if_unique_id_mismatch(reason="reconfigure_account_mismatch")
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates={
                        CONF_ACCOUNT_ID: snapshot.account.id,
                        CONF_API_TOKEN: token,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure", data_schema=_TOKEN_SCHEMA, errors=errors
        )
