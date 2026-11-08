"""Minimal Tuya Mobile SDK API client for the Maxi-Cosi app.

Used only at setup time to log in with the user's Maxi-Cosi account and
auto-discover each device's ``devId`` and ``localKey``. Afterwards the
integration talks to the monitor purely locally (see coordinator.py).

The signing keys below are constants compiled into the Maxi-Cosi Android app
(same for every user); they are needed to sign requests to Tuya's mobile API,
exactly as the app does. They may change if the vendor re-signs the app.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import aiohttp
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

# --- App signing material (from com.smart.maxicosi) ---------------------------
APP_KEY = "nw5j4d84qn8fwv5j94fe"
_PKG = "com.smart.maxicosi"
_CERT = "D8:E7:21:96:81:D0:70:B4:51:4B:0B:84:CF:EB:99:79:B3:F5:CB:72:C2:55:76:62:3C:FE:FC:94:13:D6:44:C5"
_EMBEDDED = "pmf7xrdfg59qk8etxtafcdwa7nptgpm4"
_APP_SECRET = "e3yufvppcfhmq7cwepygj8hmj33dkv5e"
SIGNING_KEY = f"{_PKG}_{_CERT}_{_EMBEDDED}_{_APP_SECRET}"

API_HOST = "https://a1.tuyaeu.com/api.json"  # Maxi-Cosi app uses the EU datacentre
APP_VERSION = "3.0.5"
SDK_VERSION = "6.7.0"

_SIGN_WHITELIST = frozenset(
    [
        "a", "v", "lat", "lon", "lang", "deviceId", "appVersion", "ttid",
        "isH5", "h5Token", "os", "clientId", "postData", "time", "requestId",
        "et", "n4h5", "sid", "chKey", "sp",
    ]
)


class TuyaCloudError(Exception):
    """A Tuya API error (carries the Tuya error code)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _swap(s: str) -> str:
    return s[8:16] + s[0:8] + s[24:32] + s[16:24] if len(s) == 32 else s


def _sign(params: dict[str, str]) -> str:
    f = {k: v for k, v in params.items() if k in _SIGN_WHITELIST and v}
    if f.get("postData"):
        f["postData"] = _swap(hashlib.md5(f["postData"].encode()).hexdigest())
    body = "||".join(f"{k}={f[k]}" for k in sorted(f))
    return hmac.new(SIGNING_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()


class TuyaCloud:
    """Async Tuya mobile API client (setup-time use only)."""

    def __init__(self, session: aiohttp.ClientSession, country_code: str = "32") -> None:
        self._session = session
        self._country = country_code
        self.sid = ""
        self._device_id = uuid.uuid4().hex

    async def _call(self, action: str, version: str = "1.0", post_data: Any = None) -> Any:
        params = {
            "a": action, "v": version, "time": str(int(time.time())),
            "appVersion": APP_VERSION, "clientId": APP_KEY, "deviceId": self._device_id,
            "et": "0.0.1", "nd": "1", "lang": "en_US", "os": "Android",
            "requestId": str(uuid.uuid4()), "sdkVersion": SDK_VERSION, "sid": self.sid,
            "ttid": f"sdk_international@{APP_KEY}",
        }
        if post_data is not None:
            params["postData"] = json.dumps(post_data) if not isinstance(post_data, str) else post_data
        params["sign"] = _sign(params)
        async with self._session.post(
            API_HOST, data=params,
            headers={"User-Agent": f"Thing-UA=APP/Android/{APP_VERSION}/SDK/{SDK_VERSION}"},
        ) as resp:
            data = await resp.json(content_type=None)
        if not data.get("success"):
            raise TuyaCloudError(data.get("errorCode", "UNKNOWN"), data.get("errorMsg", ""))
        return data.get("result")

    # -- login -----------------------------------------------------------------
    async def _rsa_token(self, email: str) -> dict:
        return await self._call(
            "thing.m.user.username.token.get", "2.0",
            {"countryCode": self._country, "username": email, "isUid": False},
        )

    @staticmethod
    def _encrypt_password(password: str, pb_key: str) -> str:
        md5 = hashlib.md5(password.encode()).hexdigest()
        pem = f"-----BEGIN PUBLIC KEY-----\n{pb_key}\n-----END PUBLIC KEY-----\n"
        key = load_pem_public_key(pem.encode())
        return key.encrypt(md5.encode(), padding.PKCS1v15()).hex()

    async def login(self, email: str, password: str, mfa_code: str = "") -> str:
        """Log in. Raises TuyaCloudError('MFA...') when an email code is needed."""
        tok = await self._rsa_token(email)
        enc = self._encrypt_password(password, tok["pbKey"])
        self.sid = ""
        result = await self._call(
            "thing.m.user.email.password.login", "3.0",
            {
                "countryCode": self._country, "email": email, "passwd": enc,
                "token": tok["token"], "ifencrypt": 1,
                "options": json.dumps({"group": 1, "mfaCode": mfa_code}),
            },
        )
        self.sid = result["sid"]
        return self.sid

    async def send_mfa(self, email: str, password: str) -> None:
        """Ask Tuya to email a MFA code."""
        tok = await self._rsa_token(email)
        enc = self._encrypt_password(password, tok["pbKey"])
        self.sid = ""
        await self._call(
            "thing.m.user.username.mfa.code.get", "1.0",
            {
                "countryCode": self._country, "username": email, "passwd": enc,
                "token": tok["token"], "ifencrypt": 1,
                "options": json.dumps({"group": 1, "mfaCode": "null"}),
            },
        )

    # -- discovery -------------------------------------------------------------
    async def list_devices(self) -> list[dict]:
        """Return all devices on the account (dicts incl. devId, localKey, name)."""
        homes = await self._call("m.life.home.space.list") or []
        seen: dict[str, dict] = {}
        for home in homes:
            gid = str(home.get("gid", ""))
            if not gid:
                continue
            for action in ("tuya.m.my.group.device.list", "tuya.m.my.group.device.relation.list"):
                try:
                    devs = await self._call_with_gid(action, gid)
                except TuyaCloudError:
                    continue
                for dev in devs or []:
                    dev_id = dev.get("devId") or dev.get("deviceId")
                    if dev_id:
                        seen.setdefault(dev_id, dev)
        return list(seen.values())

    async def _call_with_gid(self, action: str, gid: str) -> Any:
        params = {
            "a": action, "v": "1.0", "time": str(int(time.time())),
            "appVersion": APP_VERSION, "clientId": APP_KEY, "deviceId": self._device_id,
            "et": "0.0.1", "nd": "1", "lang": "en_US", "os": "Android",
            "requestId": str(uuid.uuid4()), "sdkVersion": SDK_VERSION, "sid": self.sid,
            "ttid": f"sdk_international@{APP_KEY}", "gid": gid,
        }
        params["sign"] = _sign(params)
        async with self._session.post(
            API_HOST, data=params,
            headers={"User-Agent": f"Thing-UA=APP/Android/{APP_VERSION}/SDK/{SDK_VERSION}"},
        ) as resp:
            data = await resp.json(content_type=None)
        if not data.get("success"):
            raise TuyaCloudError(data.get("errorCode", "UNKNOWN"), data.get("errorMsg", ""))
        return data.get("result")
