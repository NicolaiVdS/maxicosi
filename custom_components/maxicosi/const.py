"""Constants for the Maxi-Cosi integration."""

from __future__ import annotations

DOMAIN = "maxicosi"

CONF_DEVICE_ID = "device_id"
CONF_HOST = "host"
CONF_LOCAL_KEY = "local_key"
CONF_PROTOCOL_VERSION = "protocol_version"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PROTOCOL_VERSION = "3.4"
PROTOCOL_VERSIONS = ["3.1", "3.2", "3.3", "3.4", "3.5"]

DEFAULT_SCAN_INTERVAL = 120  # seconds; temperature/humidity change slowly
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

# Retries per update cycle; the device sometimes refuses a local socket while
# the app is streaming, so a brief retry avoids gaps in history.
POLL_RETRIES = 3
POLL_RETRY_DELAY = 1.5  # seconds between attempts

# Tuya datapoint (DP) ids for the See Pro Baby Monitor, from its schema.
DP_TEMPERATURE = "142"
DP_HUMIDITY = "143"
