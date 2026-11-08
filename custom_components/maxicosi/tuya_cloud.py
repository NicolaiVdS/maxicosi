"""Minimal Tuya Mobile SDK API client for the Maxi-Cosi app.

Used only at setup time: log in with the user's Maxi-Cosi account and
auto-discover each device's ``devId`` and ``localKey``. Afterwards the
integration talks to the monitor purely locally (see coordinator.py).

Implements Tuya's ``et=3`` encrypted transport, reverse-engineered from
``libthing_security.so`` and verified against the live app:

* signing key / app credentials below are constants compiled into the app
* request/response ``postData`` is AES-128-GCM, key derived per request:
  ``key = hex(HMAC_SHA256(key=requestId, msg=signingKey[+"_"+ecode]))[:16]``
  blob = ``base64( nonce(12) || ciphertext || tag(16) )``
* the signature covers ``swap(md5(encrypted_postData))`` within a fixed
  parameter whitelist (HMAC-SHA256 with the signing key)

These may break if the vendor re-signs the app or rotates its keys.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid

import aiohttp
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import load_pem_public_key

_LOGGER = logging.getLogger(__name__)

APP_KEY = "nw5j4d84qn8fwv5j94fe"
_PKG = "com.smart.maxicosi"
_CERT = "D8:E7:21:96:81:D0:70:B4:51:4B:0B:84:CF:EB:99:79:B3:F5:CB:72:C2:55:76:62:3C:FE:FC:94:13:D6:44:C5"
_EMBEDDED = "pmf7xrdfg59qk8etxtafcdwa7nptgpm4"
_APP_SECRET = "e3yufvppcfhmq7cwepygj8hmj33dkv5e"
SIGNING_KEY = f"{_PKG}_{_CERT}_{_EMBEDDED}_{_APP_SECRET}"

API_HOST = "https://a1.tuyaeu.com/api.json"

# Replicated from the app's own requests to pass the gateway's client check.
# chKey is derived from this deviceId, so the pair must stay together.
_APP_DEVICE_ID = "7089bfc638d2d5a6a3fc459d9e5e71d2453e40eb9619"
_APP_CHKEY = "6245ddd6"
_APP_BIZDATA = (
    '{"brand":"waydroid","customDomainSupport":"1","miniappVersion":"{\\"AIKit\\":\\"1.4.3\\",'
    '\\"AIStreamKit\\":\\"1.1.2\\",\\"BaseKit\\":\\"3.24.9\\",\\"BizKit\\":\\"4.20.4\\",'
    '\\"CategoryCommonBizKit\\":\\"6.4.1\\",\\"DeviceKit\\":\\"4.21.4\\",\\"HealthKit\\":\\"6.6.0\\",'
    '\\"HomeKit\\":\\"3.10.0\\",\\"IPCKit\\":\\"6.8.5\\",\\"LightKit\\":\\"1.0.10\\",'
    '\\"MapKit\\":\\"6.9.5\\",\\"MediaKit\\":\\"3.6.2\\",\\"MediaPlayerKit\\":\\"1.0.21\\",'
    '\\"MiniKit\\":\\"3.21.1\\",\\"P2PKit\\":\\"6.4.2\\",\\"PlayNetKit\\":\\"1.3.31\\",'
    '\\"SweeperKit\\":\\"2.0.0\\",\\"WearKit\\":\\"1.2.7\\",\\"basicLib\\":\\"2.33.4\\",'
    '\\"container\\":\\"3.32.58\\"}","nd":"1","sdkInt":"33"}'
)

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
        self.code = code or "UNKNOWN"
        self.message = message or ""


def _swap(s: str) -> str:
    return s[8:16] + s[0:8] + s[24:32] + s[16:24] if len(s) == 32 else s


def _enc_key(request_id: str, ecode: str | None) -> bytes:
    msg = SIGNING_KEY + (f"_{ecode}" if ecode else "")
    return hmac.new(request_id.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16].encode()


def _encrypt_post(request_id: str, ecode: str | None, plaintext: str) -> str:
    key = _enc_key(request_id, ecode)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def _decrypt_result(request_id: str, ecode: str | None, b64: str) -> str:
    key = _enc_key(request_id, ecode)
    blob = base64.b64decode(b64)
    return AESGCM(key).decrypt(blob[:12], blob[12:], None).decode()


def _sign(params: dict[str, str]) -> str:
    f = {k: v for k, v in params.items() if k in _SIGN_WHITELIST and v}
    if f.get("postData"):  # sign over swap(md5(encrypted base64)), not the raw blob
        f["postData"] = _swap(hashlib.md5(f["postData"].encode()).hexdigest())
    body = "||".join(f"{k}={f[k]}" for k in sorted(f))
    return hmac.new(SIGNING_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()


class TuyaCloud:
    """Async Tuya mobile API client (setup-time use only)."""

    def __init__(self, session: aiohttp.ClientSession, country_code: str = "32") -> None:
        self._session = session
        self._country = country_code
        self.sid = ""
        self.ecode: str | None = None
        self._device_id = _APP_DEVICE_ID

    async def _call(self, action, version="1.0", post=None, extra=None):
        rid = str(uuid.uuid4())
        ecode = self.ecode if self.sid else None
        p = {
            "a": action, "v": version, "time": str(int(time.time())),
            "appVersion": "3.0.5", "appRnVersion": "5.97", "channel": "oem",
            "clientId": APP_KEY, "deviceCoreVersion": "6.9.5", "deviceId": self._device_id,
            "et": "3", "nd": "1", "lang": "en_US", "os": "Android", "osSystem": "13",
            "platform": "WayDroid x86_64 Device", "requestId": rid, "sdkVersion": "6.9.5",
            "sid": self.sid, "timeZoneId": "Europe/Brussels",
            "ttid": f"sdk_international@{APP_KEY}", "chKey": _APP_CHKEY, "bizData": _APP_BIZDATA,
        }
        if post is not None:
            raw = json.dumps(post) if not isinstance(post, str) else post
            p["postData"] = _encrypt_post(rid, ecode, raw)
        if extra:
            p.update({k: str(v) for k, v in extra.items()})
        p["sign"] = _sign(p)
        async with self._session.post(
            API_HOST, data=p,
            headers={"User-Agent": "Thing-UA=APP/Android/3.0.5/SDK/6.9.5", "x-client-trace-id": rid},
        ) as resp:
            j = await resp.json(content_type=None)
        if j.get("success") is False or j.get("errorCode"):
            raise TuyaCloudError(j.get("errorCode"), j.get("errorMsg"))
        res = j.get("result")
        if isinstance(res, str) and res:
            inner = json.loads(_decrypt_result(rid, ecode, res))
            if isinstance(inner, dict):
                if inner.get("success") is False or inner.get("errorCode"):
                    raise TuyaCloudError(inner.get("errorCode"), inner.get("errorMsg"))
                res = inner.get("result", inner)
        return res

    # -- login -----------------------------------------------------------------
    @staticmethod
    def _encrypt_password(password: str, pb_key: str) -> str:
        md5 = hashlib.md5(password.encode()).hexdigest()
        pem = f"-----BEGIN PUBLIC KEY-----\n{pb_key}\n-----END PUBLIC KEY-----\n"
        return load_pem_public_key(pem.encode()).encrypt(md5.encode(), padding.PKCS1v15()).hex()

    async def login(self, email: str, password: str, mfa_code: str = "") -> dict:
        """Log in. Raises TuyaCloudError('MFA...') when an email code is needed."""
        tok = await self._call(
            "smartlife.m.user.username.token.get", "2.0",
            {"countryCode": self._country, "username": email, "isUid": False},
        )
        enc = self._encrypt_password(password, tok["pbKey"])
        self.sid = ""
        res = await self._call(
            "smartlife.m.user.email.password.login", "3.0",
            {
                "countryCode": self._country, "email": email, "passwd": enc,
                "token": tok["token"], "ifencrypt": 1,
                "options": json.dumps({"group": 1, "mfaCode": mfa_code}),
            },
        )
        self.sid = res["sid"]
        self.ecode = res.get("ecode")
        return res

    async def send_mfa(self, email: str, password: str) -> None:
        """Ask Tuya to email a MFA code."""
        tok = await self._call(
            "smartlife.m.user.username.token.get", "2.0",
            {"countryCode": self._country, "username": email, "isUid": False},
        )
        enc = self._encrypt_password(password, tok["pbKey"])
        self.sid = ""
        await self._call(
            "smartlife.m.user.username.mfa.code.get", "1.0",
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
            gid = home.get("gid") or home.get("groupId")
            if not gid:
                continue
            for action in ("tuya.m.my.group.device.list", "tuya.m.my.group.device.relation.list"):
                try:
                    devs = await self._call(action, "1.0", extra={"gid": gid})
                except TuyaCloudError:
                    continue
                for dev in devs or []:
                    dev_id = dev.get("devId") or dev.get("deviceId")
                    if dev_id:
                        seen.setdefault(dev_id, dev)
        return list(seen.values())
