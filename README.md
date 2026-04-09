# AiDot LAN — Home Assistant Integration

> **Fork of [AiDot-Development-Team/hass-AiDot](https://github.com/AiDot-Development-Team/hass-AiDot) (v1.1.1) with LAN/P2P reliability improvements and cloud-seeded fallback.**

[![HA Integration Type: hub](https://img.shields.io/badge/integration_type-hub-blue?style=flat-square)](https://developers.home-assistant.io/docs/quality_scale)
[![Quality Scale: Gold](https://img.shields.io/badge/quality_scale-gold-yellow?style=flat-square)](https://developers.home-assistant.io/docs/quality_scale)
[![Version: 1.2.0](https://img.shields.io/badge/version-1.2.0-green?style=flat-square)](https://github.com/YuvDwi/Steve)

## What this fork fixes

| Problem | Upstream v1.1.1 | This fork |
|---------|----------------|-----------|
| Entity shows `unavailable` when P2P is blocked by VLAN/firewall | ❌ Always | ✅ Cloud-seeded initial state |
| P2P status with no real data overwrites good cloud state | ❌ Silent data loss | ✅ Preserved — P2P data only accepted when `online` and `dimming` are non-null |
| No polling fallback when P2P push is silent | ❌ Event-only | ✅ 30 s polling fallback |
| Device offline → service call hard-fails | ❌ `ConnectionError` propagates | ✅ Optimistic local state update |

## Requirements

- Home Assistant 2024.11 or later
- AiDot account (same credentials as the AiDot app)
- AiDot devices on the same LAN as Home Assistant (or at least VLAN-accessible)

## Installation

### Option A — HACS (recommended)

1. Add this repository to HACS:
   **HACS → Integrations → ⋯ → Custom repositories → `https://github.com/YuvDwi/Steve` → Category: Integration**
2. Restart Home Assistant
3. Add **AiDot LAN** from **Settings → Devices & Services → Add Integration**

### Option B — Manual

Copy `custom_components/aidot_lan/` into your Home Assistant's `config/custom_components/` directory, then restart Home Assistant.

## How it works

```
┌─────────────────────────────────────────────────────────┐
│  Home Assistant  ←→  AiDot LAN integration (this fork)  │
│                          │                               │
│            ┌─────────────┴──────────────┐               │
│            ▼                            ▼               │
│   ┌─────────────────┐        ┌──────────────────────┐  │
│   │  Cloud API       │        │  Direct LAN P2P      │  │
│   │  (device list,   │        │  (real-time status,  │  │
│   │   auth, seed)    │        │   control)           │  │
│   └─────────────────┘        └──────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

1. On startup, the integration fetches device metadata from the **AiDot cloud API** and **seeds** each device coordinator with the last-reported cloud state.
2. The entity immediately becomes available instead of stuck in `unavailable`.
3. **LAN P2P** runs in the background — if reachable, it provides real-time status updates and handles control commands.
4. If P2P is blocked or the device is offline:
   - Service calls update entity state **optimistically** (no error in HA UI)
   - Polling every 30 s catches state changes when connectivity returns

## Supported features

| Feature | Details |
|---------|---------|
| On / Off | ✅ |
| Brightness | ✅ 0–255 |
| Color Temperature (CCT) | ✅ in Kelvin, per-device min/max |
| RGBW Colour | ✅ |
| Availability tracking | ✅ — P2P + polling fallback |
| Cloud-seeded startup | ✅ — no more `unavailable` on boot |
| Multiple devices | ✅ — auto-discovered from cloud |
| Device registry cleanup | ✅ — stale entries removed |
| Diagnostics | ✅ — `configuration → diagnostics` for each device |

## Network requirements

AiDot bulbs listen on **TCP port 10000** for P2P commands. Home Assistant must be able to reach that port on each bulb's IP address. This means:

- Bulbs and HA should be on the same subnet **or**
- Inter-VLAN routing must allow TCP 10000 from HA's network to the IoT VLAN

If port 10000 is unreachable, the integration degrades gracefully to cloud-seeded state + 30 s polling.

## Troubleshooting

### Entities show `unavailable` even with this fork

Check that Home Assistant can reach the bulbs on TCP port 10000:

```bash
nc -zv <bulb-ip> 10000
```

If this times out, the P2P path is blocked — check VLAN isolation, firewall rules, or AP/client isolation on your router.

### Token / authentication errors

Re-add the integration — tokens expire periodically and the integration handles refresh automatically on startup, but a full re-setup may be needed if credentials have changed.

## Known limitations

- **Cloud auth required at setup time** — credentials are used once to obtain a session token; subsequent operation is local.
- **No dedicated reauthentication flow** — if the token becomes invalid weeks later, re-add the integration.
- **IoT class listed as `local_polling`** — in practice the integration uses both push (P2P) and polling (30 s fallback).

## Filing issues

Report bugs at [github.com/YuvDwi/Steve](https://github.com/YuvDwi/Steve/issues).

## Credits

- Upstream: [AiDot-Development-Team/hass-AiDot](https://github.com/AiDot-Development-Team/hass-AiDot) — original Home Assistant integration
- `python-aidot` library: [s1eedz/python-aidot](https://github.com/s1eedz/python-aidot)
