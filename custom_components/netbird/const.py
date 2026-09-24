"""Constants for the NetBird integration."""

from typing import Final

DOMAIN: Final = "netbird"

API_BASE_URL: Final = "https://api.netbird.io"
DASHBOARD_BASE_URL: Final = "https://app.netbird.io"
API_TIMEOUT_SECONDS: Final = 10
PEER_UPDATE_INTERVAL_SECONDS: Final = 60
TOPOLOGY_UPDATE_INTERVAL_SECONDS: Final = 300
TOPOLOGY_REQUEST_CONCURRENCY: Final = 6
STALE_PEER_SNAPSHOT_THRESHOLD: Final = 10

CONF_ACCOUNT_ID: Final = "account_id"
CONF_API_TOKEN: Final = "api_token"

SENSITIVE_CONFIG_KEYS: Final = frozenset({CONF_API_TOKEN})
