"""Constants for the NetBird integration."""

from typing import Final

DOMAIN: Final = "netbird"

API_BASE_URL: Final = "https://api.netbird.io"
API_TIMEOUT_SECONDS: Final = 10
PEER_UPDATE_INTERVAL_SECONDS: Final = 60

CONF_ACCOUNT_ID: Final = "account_id"
CONF_API_TOKEN: Final = "api_token"

SENSITIVE_CONFIG_KEYS: Final = frozenset({CONF_API_TOKEN})
