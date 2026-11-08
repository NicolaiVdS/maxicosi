#!/usr/bin/env python3
"""Probe why token.get returns ILLEGAL_CLIENT_ID: vary et / ttid / params and
print each result. Read-only, hits only the token.get endpoint.

Run: uv run --with requests python tools/probe.py
"""
import hashlib, hmac, json, time, uuid
import requests

APP_KEY = "nw5j4d84qn8fwv5j94fe"
_PKG = "com.smart.maxicosi"
_CERT = "D8:E7:21:96:81:D0:70:B4:51:4B:0B:84:CF:EB:99:79:B3:F5:CB:72:C2:55:76:62:3C:FE:FC:94:13:D6:44:C5"
_EMB = "pmf7xrdfg59qk8etxtafcdwa7nptgpm4"
_SEC = "e3yufvppcfhmq7cwepygj8hmj33dkv5e"
SK = f"{_PKG}_{_CERT}_{_EMB}_{_SEC}"
API = "https://a1.tuyaeu.com/api.json"
WL = {"a","v","lat","lon","lang","deviceId","appVersion","ttid","isH5","h5Token",
      "os","clientId","postData","time","requestId","et","n4h5","sid","chKey","sp"}

def sign(p):
    f = {k:v for k,v in p.items() if k in WL and v}
    return hmac.new(SK.encode(), "||".join(f"{k}={f[k]}" for k in sorted(f)).encode(),
                    hashlib.sha256).hexdigest()

DEV = uuid.uuid4().hex

def call(label, *, et, ttid, extra=None, drop=()):
    p = {
        "a": "thing.m.user.username.token.get", "v": "2.0", "time": str(int(time.time())),
        "appVersion": "3.0.5", "appRnVersion": "5.97", "channel": "oem", "clientId": APP_KEY,
        "cp": "gzip", "deviceCoreVersion": "6.9.5", "deviceId": DEV, "et": et, "nd": "1",
        "lang": "en_US", "os": "Android", "osSystem": "13", "platform": "python_test",
        "requestId": str(uuid.uuid4()), "sdkVersion": "6.9.5", "sid": "",
        "timeZoneId": "Europe/Brussels", "ttid": ttid,
        "postData": json.dumps({"countryCode": "32", "username": "probe@example.com", "isUid": False}),
    }
    for k in drop:
        p.pop(k, None)
    if extra:
        p.update(extra)
    p["sign"] = sign(p)
    try:
        j = requests.post(API, data=p,
                          headers={"User-Agent": "Thing-UA=APP/Android/3.0.5/SDK/6.9.5"},
                          timeout=15).json()
        print(f"{label:28} -> success={j.get('success')} {j.get('errorCode','')} {j.get('errorMsg','')}")
    except Exception as e:
        print(f"{label:28} -> EXC {e}")

TTID_SDK = f"sdk_international@{APP_KEY}"
call("et=0.0.1 ttid=sdk", et="0.0.1", ttid=TTID_SDK)
call("et=3     ttid=sdk", et="3", ttid=TTID_SDK)
call("no-et    ttid=sdk", et="0.0.1", ttid=TTID_SDK, drop=("et",))
call("et=0.0.1 ttid=smartmaxicosi", et="0.0.1", ttid="smartmaxicosi")
call("et=3     ttid=smartmaxicosi", et="3", ttid="smartmaxicosi")
call("et=0.0.1 +sp", et="0.0.1", ttid=TTID_SDK, extra={"sp": ""})
