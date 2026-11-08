"""Constants for the Maxi-Cosi integration."""

from __future__ import annotations

DOMAIN = "maxicosi"

CONF_DEVICE_ID = "device_id"
CONF_HOST = "host"
CONF_LOCAL_KEY = "local_key"
CONF_PROTOCOL_VERSION = "protocol_version"

DEFAULT_PROTOCOL_VERSION = "3.4"
PROTOCOL_VERSIONS = ["3.1", "3.2", "3.3", "3.4", "3.5"]

DEFAULT_SCAN_INTERVAL = 60  # seconds; temperature/humidity change slowly

# Tuya datapoint (DP) ids for the See Pro Baby Monitor, from its schema.
DP_TEMPERATURE = "142"
DP_HUMIDITY = "143"
