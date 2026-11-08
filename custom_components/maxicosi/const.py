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

DEFAULT_COUNTRY_CODE = "32"  # Belgium

# (calling code, country) for the login dropdown; other values can still be typed.
CALLING_CODES: list[tuple[str, str]] = [
    ("32", "Belgium"), ("31", "Netherlands"), ("33", "France"), ("49", "Germany"),
    ("352", "Luxembourg"), ("44", "United Kingdom"), ("353", "Ireland"),
    ("34", "Spain"), ("351", "Portugal"), ("39", "Italy"), ("41", "Switzerland"),
    ("43", "Austria"), ("45", "Denmark"), ("46", "Sweden"), ("47", "Norway"),
    ("358", "Finland"), ("48", "Poland"), ("420", "Czechia"), ("421", "Slovakia"),
    ("36", "Hungary"), ("40", "Romania"), ("359", "Bulgaria"), ("30", "Greece"),
    ("385", "Croatia"), ("386", "Slovenia"), ("372", "Estonia"), ("371", "Latvia"),
    ("370", "Lithuania"), ("1", "United States / Canada"), ("52", "Mexico"),
    ("55", "Brazil"), ("54", "Argentina"), ("61", "Australia"), ("64", "New Zealand"),
    ("27", "South Africa"), ("90", "Turkey"), ("7", "Russia"), ("380", "Ukraine"),
    ("972", "Israel"), ("971", "United Arab Emirates"), ("966", "Saudi Arabia"),
    ("91", "India"), ("86", "China"), ("81", "Japan"), ("82", "South Korea"),
    ("65", "Singapore"), ("60", "Malaysia"), ("66", "Thailand"),
    ("63", "Philippines"), ("62", "Indonesia"), ("84", "Vietnam"),
]
