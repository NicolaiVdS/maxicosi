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

## Installation (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/nicolaivds/maxicosi`,
   category **Integration**.
2. Install **Maxi-Cosi Baby Monitor**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Maxi-Cosi**.

## Configuration

You need three per-device values plus the protocol version:

| Field | Example | Notes |
|-------|---------|-------|
| Device ID | `bfc45ac6...` | Tuya device id (`devId`), stable per device |
| IP address | `10.0.0.151` | The monitor's LAN IP (reserve it in your router's DHCP) |
| Local key | `~xvBj8$f...` | Per-device secret; **changes if you re-pair the monitor** |
| Protocol version | `3.4` | See Pro uses `3.4` |

### Getting the Device ID and Local Key

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
datapoints every 60 s. Temperature is DP `142`, humidity is DP `143` (both plain
integers, no scaling). A `DataUpdateCoordinator` shares one poll across both
entities.

## Credits

Built by reverse-engineering the Tuya-based Maxi-Cosi app for interoperability.
The Tuya local protocol work builds on [tinytuya](https://github.com/jasonacox/tinytuya).

## License

MIT
