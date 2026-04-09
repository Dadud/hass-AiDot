# AiDot LAN — Integration for Home Assistant

Integrates [AiDot smart lights](https://www.aidot.com) with Home Assistant via LAN P2P with cloud-seeded fallback.

## Features

- **Local P2P control** — commands go directly to the bulb over the local network when reachable
- **Cloud-seeded startup** — entities become available immediately instead of stuck in "unavailable"
- **Graceful degradation** — if P2P is blocked (VLAN/firewall), service calls update state optimistically and 30 s polling keeps things fresh
- **Multi-device** — all AiDot lights in your AiDot account are auto-discovered

## Supported devices

Tested with AiDot Smart RGBTW Bulb A21 (model `LK.light.A000108`). Any AiDot light that appears in the AiDot app should work.

## Requirements

- Home Assistant 2024.11+
- AiDot account credentials (same as the AiDot app)
- TCP port 10000 on each bulb must be reachable from Home Assistant

## Setup

1. Add this repository to HACS as a custom integration repository
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration** and search for **AiDot LAN**
4. Enter your AiDot username, password, and country code

## Network

AiDot bulbs listen on **TCP port 10000**. Home Assistant must be able to reach this port on each bulb's IP. If this is blocked by VLAN isolation, the integration falls back to cloud-seeded state with 30 s polling.
