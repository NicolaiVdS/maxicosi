# Maxi-Cosi Baby Monitor — Home Assistant integration

Local (cloud-free) integration for the **Maxi-Cosi See Pro Baby Monitor**.
It polls the monitor directly on your LAN using the Tuya local protocol and
exposes its environment sensors in Home Assistant:

- 🌡️ **Temperature** (°C)
- 💧 **Humidity** (%)

No Tuya cloud account, no internet round-trip. The official Maxi-Cosi app keeps
working alongside it.

> Video (the camera stream) is **not** included yet — the monitor exposes an
> ONVIF/RTSP endpoint (datapoints 254/255) which can be fed to `go2rtc`/HA
> separately. A future release may add it to this integration.

## Installation (Marketplace)

Home Assistant 2026.11+ has a built-in **Marketplace** (the former HACS).

1. **Settings → Marketplace → ⋮ → Add from link** → enter
   `https://github.com/NicolaiVdS/maxicosi` (or `NicolaiVdS/maxicosi`).
   You'll be asked to connect GitHub once (reads public info only).
2. Install **Maxi-Cosi Baby Monitor**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Maxi-Cosi**.

> On older setups still running standalone HACS, add the same URL as a
> *custom repository* (category: Integration) instead.

## Configuration

Two ways to set it up — pick one when you add the integration:

### Option A — Log in (recommended)

Choose **"Log in with my Maxi-Cosi account"** and enter your app email,
password and country calling code (e.g. `32` for Belgium). The integration logs
in to Tuya exactly like the app — including its encrypted `et=3` transport — lets
you pick your monitor, and fetches the device ID and **local key automatically**,
then tries to detect its LAN IP. Your credentials are used only at setup; all
polling afterwards is local. If your account has email 2FA, you'll be asked for
the code.

> Login uses the Maxi-Cosi app's signing keys, which live in this repo. If the
> vendor ever rotates them, login may stop working until the keys are refreshed —
> Option B always keeps working.

### Option B — Manual

Choose **"Enter device details manually"** and provide:

| Field | Example | Notes |
|-------|---------|-------|
| Device ID | `bfc45ac6...` | Tuya device id (`devId`), stable per device |
| IP address | `10.0.0.151` | The monitor's LAN IP (reserve it in your router's DHCP) |
| Local key | `~xvBj8$f...` | Per-device secret; **changes if you re-pair the monitor** |
| Protocol version | `3.4` | See Pro uses `3.4` |

#### Getting the Device ID and Local Key manually

These are credentials for **your own** device. The standard way is the
[`tinytuya` setup wizard](https://github.com/jasonacox/tinytuya#setup-wizard),
which links a free Tuya IoT developer account to your Maxi-Cosi app account and
lists each device's `localKey`:

```bash
python -m pip install tinytuya
python -m tinytuya wizard
```

If the whitelabel app account can't be linked to a Tuya IoT project, the key can
also be read from the running app on a device you control (e.g. via Frida) — see
`docs/` for the method used to bootstrap this integration.

> ⚠️ If polling starts failing with auth errors after a factory reset or
> re-pairing, the local key changed — re-fetch it and reconfigure.

## How it works

`tinytuya` opens a persistent local socket to the monitor and reads its
datapoints every 120 s by default (configurable 10–3600 s via the integration's
**Configure** button). Temperature is DP `142`, humidity is DP `143` (both plain
integers, no scaling). A `DataUpdateCoordinator` shares one poll across both
entities and retries briefly on a failed read, so the app streaming at the same
time doesn't leave gaps in history.

## Credits

Built by reverse-engineering the Tuya-based Maxi-Cosi app for interoperability.
The Tuya local protocol work builds on [tinytuya](https://github.com/jasonacox/tinytuya).

## License

MIT
