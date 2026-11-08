#!/usr/bin/env python3
"""Standalone Maxi-Cosi (Tuya) login tester with et=3 encrypted transport.

Run on your own machine (needs internet to reach Tuya EU):
    uv run --with requests --with cryptography python tools/login_test.py
  or
    pip install requests cryptography && python tools/login_test.py

Prompts for email / password / country code, handles the emailed MFA code,
then prints each device's devId + localKey. Read-only against Tuya's cloud.

et=3 scheme (reverse-engineered from libthing_security.so):
  key = hex(HMAC_SHA256(key=requestId, msg=SIGNING_KEY[+"_"+ecode]))[:16]  (ascii)
  postData = base64( nonce(12) || AES128GCM(key,nonce,plaintext) || tag(16) )
  response.result is the same framing, decrypted with the same key.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import os
import time
import uuid

import requests
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import load_pem_public_key

APP_KEY = "nw5j4d84qn8fwv5j94fe"
_PKG = "com.smart.maxicosi"
_CERT = "D8:E7:21:96:81:D0:70:B4:51:4B:0B:84:CF:EB:99:79:B3:F5:CB:72:C2:55:76:62:3C:FE:FC:94:13:D6:44:C5"
_EMB = "pmf7xrdfg59qk8etxtafcdwa7nptgpm4"
_SEC = "e3yufvppcfhmq7cwepygj8hmj33dkv5e"
SIGNING_KEY = f"{_PKG}_{_CERT}_{_EMB}_{_SEC}"
API = "https://a1.tuyaeu.com/api.json"
WL = {"a","v","lat","lon","lang","deviceId","appVersion","ttid","isH5","h5Token",
      "os","clientId","postData","time","requestId","et","n4h5","sid","chKey","sp"}

# Replicated verbatim from the app's own requests (chKey is derived from this
# deviceId, so the pair must stay together). Used to pass the gateway's client check.
APP_DEVICE_ID = "7089bfc638d2d5a6a3fc459d9e5e71d2453e40eb9619"
APP_CHKEY = "6245ddd6"
APP_BIZDATA = ('{"brand":"waydroid","customDomainSupport":"1","miniappVersion":"{\\"AIKit\\":\\"1.4.3\\",'
               '\\"AIStreamKit\\":\\"1.1.2\\",\\"BaseKit\\":\\"3.24.9\\",\\"BizKit\\":\\"4.20.4\\",'
               '\\"CategoryCommonBizKit\\":\\"6.4.1\\",\\"DeviceKit\\":\\"4.21.4\\",\\"HealthKit\\":\\"6.6.0\\",'
               '\\"HomeKit\\":\\"3.10.0\\",\\"IPCKit\\":\\"6.8.5\\",\\"LightKit\\":\\"1.0.10\\",'
               '\\"MapKit\\":\\"6.9.5\\",\\"MediaKit\\":\\"3.6.2\\",\\"MediaPlayerKit\\":\\"1.0.21\\",'
               '\\"MiniKit\\":\\"3.21.1\\",\\"P2PKit\\":\\"6.4.2\\",\\"PlayNetKit\\":\\"1.3.31\\",'
               '\\"SweeperKit\\":\\"2.0.0\\",\\"WearKit\\":\\"1.2.7\\",\\"basicLib\\":\\"2.33.4\\",'
               '\\"container\\":\\"3.32.58\\"}","nd":"1","sdkInt":"33"}')


def _load_env(path=".env"):
    try:
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


def enc_key(request_id: str, ecode: str | None) -> bytes:
    msg = SIGNING_KEY + (f"_{ecode}" if ecode else "")
    return hmac.new(request_id.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16].encode()


def encrypt_post(request_id, ecode, plaintext: str) -> str:
    key = enc_key(request_id, ecode)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_result(request_id, ecode, b64: str) -> str:
    key = enc_key(request_id, ecode)
    blob = base64.b64decode(b64)
    return AESGCM(key).decrypt(blob[:12], blob[12:], None).decode()


def _swap(s: str) -> str:
    return s[8:16] + s[0:8] + s[24:32] + s[16:24] if len(s) == 32 else s


def sign(p: dict) -> str:
    f = {k: v for k, v in p.items() if k in WL and v}
    if f.get("postData"):  # sign over swap(md5(encrypted base64)), not the raw blob
        f["postData"] = _swap(hashlib.md5(f["postData"].encode()).hexdigest())
    return hmac.new(SIGNING_KEY.encode(),
                    "||".join(f"{k}={f[k]}" for k in sorted(f)).encode(),
                    hashlib.sha256).hexdigest()


class Tuya:
    def __init__(self, country):
        self.country = country
        self.sid = ""
        self.ecode = None
        self.device_id = APP_DEVICE_ID

    def call(self, action, version="1.0", post=None, extra=None):
        rid = str(uuid.uuid4())
        ecode = self.ecode if self.sid else None
        p = {
            "a": action, "v": version, "time": str(int(time.time())),
            "appVersion": "3.0.5", "appRnVersion": "5.97", "channel": "oem",
            "clientId": APP_KEY, "deviceCoreVersion": "6.9.5", "deviceId": self.device_id,
            "et": "3", "nd": "1", "lang": "en_US", "os": "Android", "osSystem": "13",
            "platform": "WayDroid x86_64 Device", "requestId": rid, "sdkVersion": "6.9.5",
            "sid": self.sid, "timeZoneId": "Europe/Brussels",
            "ttid": f"sdk_international@{APP_KEY}",
            "chKey": APP_CHKEY, "bizData": APP_BIZDATA,
        }
        if post is not None:
            raw = json.dumps(post) if not isinstance(post, str) else post
            p["postData"] = encrypt_post(rid, ecode, raw)
        if extra:  # top-level params like gid (not part of the signed whitelist)
            p.update({k: str(v) for k, v in extra.items()})
        p["sign"] = sign(p)
        r = requests.post(API, data=p, headers={
            "User-Agent": "Thing-UA=APP/Android/3.0.5/SDK/6.9.5",
            "x-client-trace-id": rid,
        }, timeout=15)
        j = r.json()
        # Outer (plaintext) error envelope.
        if j.get("success") is False or j.get("errorCode"):
            print(f"  -> {action}: FAIL {j.get('errorCode')} {j.get('errorMsg')}")
            raise RuntimeError(f"{j.get('errorCode')}: {j.get('errorMsg')}")
        res = j.get("result")
        # et=3: result is an encrypted {success, result:{...}} envelope.
        if isinstance(res, str) and res:
            inner = json.loads(decrypt_result(rid, ecode, res))
            if isinstance(inner, dict):
                if inner.get("success") is False or inner.get("errorCode"):
                    print(f"  -> {action}: FAIL {inner.get('errorCode')} {inner.get('errorMsg')}")
                    raise RuntimeError(f"{inner.get('errorCode')}: {inner.get('errorMsg')}")
                res = inner.get("result", inner)
        print(f"  -> {action}: OK")
        return res

    def _enc_pw(self, password, pb_key):
        md5 = hashlib.md5(password.encode()).hexdigest()
        pem = f"-----BEGIN PUBLIC KEY-----\n{pb_key}\n-----END PUBLIC KEY-----\n"
        return load_pem_public_key(pem.encode()).encrypt(md5.encode(), padding.PKCS1v15()).hex()

    def login(self, email, password, mfa=""):
        tok = self.call("smartlife.m.user.username.token.get", "2.0",
                        {"countryCode": self.country, "username": email, "isUid": False})
        enc = self._enc_pw(password, tok["pbKey"])
        self.sid = ""
        res = self.call("smartlife.m.user.email.password.login", "3.0", {
            "countryCode": self.country, "email": email, "passwd": enc,
            "token": tok["token"], "ifencrypt": 1,
            "options": json.dumps({"group": 1, "mfaCode": mfa}),
        })
        self.sid = res["sid"]
        self.ecode = res.get("ecode")
        print("     sid/ecode acquired:", bool(self.sid), bool(self.ecode))
        return res

    def send_mfa(self, email, password):
        tok = self.call("smartlife.m.user.username.token.get", "2.0",
                        {"countryCode": self.country, "username": email, "isUid": False})
        enc = self._enc_pw(password, tok["pbKey"])
        self.sid = ""
        return self.call("smartlife.m.user.username.mfa.code.get", "1.0", {
            "countryCode": self.country, "username": email, "passwd": enc,
            "token": tok["token"], "ifencrypt": 1,
            "options": json.dumps({"group": 1, "mfaCode": "null"}),
        })

    def get_device(self, dev_id):
        return self.call("tuya.m.device.get", "1.0", {"devId": dev_id})

    def set_dp(self, dev_id, dps):
        dps_str = json.dumps(dps)
        attempts = [
            ("tuya.m.device.dp.publish", "2.0", {"devId": dev_id, "gwId": dev_id, "dps": dps_str}),
            ("tuya.m.device.dp.publish", "2.0", {"devId": dev_id, "dps": dps_str}),
            ("tuya.m.device.dp.publish", "1.0", {"devId": dev_id, "gwId": dev_id, "dps": dps_str}),
            ("tuya.m.device.dp.publish", "2.0", {"devId": dev_id, "gwId": dev_id, "dps": dps}),
            ("m.smart.device.dp.publish", "1.0", {"devId": dev_id, "gwId": dev_id, "dps": dps_str}),
        ]
        for a, v, p in attempts:
            try:
                r = self.call(a, v, p)
                print(f"   set_dp OK via {a} v{v} (dps={'str' if isinstance(p['dps'],str) else 'obj'})")
                return r
            except RuntimeError as e:
                print(f"   set_dp fail {a} v{v}: {e}")
        raise RuntimeError("all dp.publish variants failed")

    def devices(self):
        homes = self.call("m.life.home.space.list") or []
        print("     homes:", json.dumps(homes)[:600])
        out = []
        for h in homes:
            gid = h.get("gid") or h.get("groupId") or h.get("id") or h.get("homeId") or h.get("ownerId")
            for action in ("tuya.m.my.group.device.list", "tuya.m.my.group.device.relation.list"):
                try:
                    res = self.call(action, "1.0", extra={"gid": gid} if gid else None)
                except RuntimeError:
                    continue
                if isinstance(res, list):
                    out.extend(res)
        return out


def main():
    print("Maxi-Cosi login test (et=3)\n")
    _load_env()
    email = os.environ.get("EMAIL") or input("Email: ").strip()
    password = os.environ.get("PASS") or getpass.getpass("Password: ")
    country = os.environ.get("COUNTRY") or input("Country calling code [32]: ").strip() or "32"
    print(f"Using email={email} country={country}")
    t = Tuya(country)
    try:
        t.login(email, password)
    except RuntimeError as e:
        if "MFA" in str(e).upper():
            print("\nMFA required — requesting email code...")
            try:
                t.send_mfa(email, password)
            except RuntimeError as e2:
                print("  (send_mfa:", e2, ")")
            code = input("Enter the code from your email: ").strip()
            t.login(email, password, code)
        else:
            raise
    print("\nLogin OK.\nDiscovering devices...")
    seen = {}
    for d in t.devices():
        did = d.get("devId") or d.get("deviceId")
        if did:
            seen[did] = d
    print(f"\n{len(seen)} device(s):")
    for d in seen.values():
        print(f"  - {d.get('name') or d.get('deviceName')}: "
              f"devId={d.get('devId') or d.get('deviceId')} "
              f"localKey={d.get('localKey')} ip={d.get('ip','?')}")

    if os.environ.get("ONVIF_ENABLE"):
        mon = next((d for d in seen.values()
                    if "onitor" in (d.get("name") or d.get("deviceName") or "")), None)
        if not mon:
            print("\nNo monitor device found for ONVIF."); return
        mid = mon.get("devId") or mon.get("deviceId")
        print(f"\n=== ONVIF setup for {mon.get('name')} ({mid}) ===")
        dev = t.get_device(mid)
        dps = dev.get("dps", {}) if isinstance(dev, dict) else {}
        print("current ONVIF dps 253/254/255:",
              {k: dps.get(k) for k in ("253", "254", "255")})
        # control test: toggle a known-good DP via the same cloud path
        osd = dps.get("104")
        print(f"\ncontrol test: cloud-set DP104 (basic_osd) {osd} -> {not osd}")
        t.set_dp(mid, {"104": (not osd) if isinstance(osd, bool) else True})
        time.sleep(6)
        osd2 = (t.get_device(mid) or {}).get("dps", {}).get("104")
        print(f"   DP104 now {osd2}  -> cloud writes {'REACH device' if osd2 != osd else 'do NOT reach device'}")
        if isinstance(osd, bool):
            t.set_dp(mid, {"104": osd})  # restore

        pwd = os.environ.get("ONVIF_PASS", "MaxiCosi123!")
        print(f"\nenabling ONVIF via cloud (253=<pwd>, 255=True)...")
        t.set_dp(mid, {"253": pwd, "255": True})
        time.sleep(10)
        dps = (t.get_device(mid) or {}).get("dps", {})
        print("after enable 253/254/255:",
              {k: dps.get(k) for k in ("253", "254", "255")})
        print("  ONVIF password:", pwd)


if __name__ == "__main__":
    main()
