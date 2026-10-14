# Outdoor Wi-Fi Mic, On-Device Mic Setup, and Remote Help — Design

**Date:** 2026-10-14
**Status:** Approved 2026-10-14
**Builds on:** this repo (BirdNET Display) + [birdnetgo-esp32-rtsp-mic](https://github.com/Sukecz/birdnetgo-esp32-rtsp-mic) firmware v1.26
**Parts list:** [../../parts-list.md](../../parts-list.md) · **Sourcing notes:** [../../research/sourcing-notes.md](../../research/sourcing-notes.md)

## 1. Goal

A gift build for Chris's parents: the BirdNET Display (indoors) plus a weatherproof Wi-Fi microphone mounted out in the yard. The parents are not technical, so:

- **Out of the box:** plug in the display, join their Wi-Fi on the touchscreen, plug in the mic outside, tap **Add microphone**. Nothing else.
- **No phones, laptops, pasting, or accounts** for the parents, ever.
- **Chris can remote in** for troubleshooting without asking them to do anything.

### Decisions made

| Topic | Decision |
|---|---|
| Mic transport | Mic joins the parents' **home Wi-Fi** (not a Pi-hosted AP). Range beyond Bluetooth. |
| Mic power | 5 V USB adapter at an outdoor outlet under a "while-in-use" cover; long outdoor cable to the mic. |
| Mic placement | **Fully exposed** on a post / fence / tree. |
| Enclosure | **Hybrid:** bought IP65/IP67 box + printed ASA tray, rain hood, and mount. Must stay small (deck-of-cards box). |
| Mic first-time Wi-Fi | **Display provisions the mic** ("Add microphone") — Pi hops onto the mic's setup AP and hands over home Wi-Fi credentials. |
| Mic settings on touchscreen | Status, gain, noise (high-pass) filter, restart, remove/replace. Everything else stays on the mic's own web UI. |
| Remote help | **WireGuard** client on the Pi → Chris's home WireGuard server via his auto-updating DNS name. Fully pre-loaded on Chris's bench. |
| Parts sourcing | DigiKey where possible; screen from the fastest source that matches the case's mechanical fit. |

### Out of scope (YAGNI)

- Battery/solar mic power, remote screen viewing (VNC/Pi Connect), multiple mics, firmware modifications, a "listen" audio test on the display.

## 2. Hardware — Outdoor Mic Unit

### Electronics
- Seeed **XIAO ESP32-C3** (switched from the C6, which was out of stock 2026-10-14; C6/C5 also work) running birdnetgo-esp32-rtsp-mic v1.26+, flashed via the web flasher.
- Adafruit SPH0645LM4H I2S breakout, wired per firmware README (BCLK→D3, WS→D1, SD→D2, 3V3, GND, SEL→GND). Firmware **Mic format = MSB / left-justified** (`mic_format=1`).
- The C3's included 2.4 GHz FPC U.FL antenna, stuck inside the box (plastic is RF-transparent). Use a sealed external antenna only if RSSI at the mount point is worse than about −75 dBm.

### Enclosure (hybrid)
- **Box:** **Bud PN-1320-MB** — polycarbonate, opaque gray lid, mounting brackets, IP65/66, **64 × 58 × 35 mm external / 58 × 52 × 30 mm internal**. (IP68 PN-1320-AMB is the same footprint if it comes back in stock; Hammond 1555B2GY 65 × 65 × 40 mm IP68 is the roomier fallback.)
- **Bottom face (pointing down):**
  - Mic port: about 3–4 mm hole, covered outside by an **adhesive IP67 acoustic vent membrane**. Ships with a **fine stainless/nylon bug mesh** glued over the port; Chris's dad applies the membrane later (`docs/guides/adding-the-mic-membrane.md`).
  - Power entry: **PG7 nylon cable gland** (Jacob 50.007PA/SW/G); cable gets a drip loop before entry. Keep the gland at least 20 mm from the mic port.
  - A USB-C plug will not pass through a PG7 gland, so the cable's USB-C end is cut off, fed through the gland, and the 5 V / GND conductors are **soldered to the XIAO 5V/GND pads**. Firmware is flashed over USB before final assembly; later updates use OTA.
- **Printed parts (ASA):**
  1. **Inner tray** — holds the XIAO and presses the mic breakout's port against the bottom hole through a **silicone O-ring** (or closed-cell EPDM ring) so sound goes to the mic, not into the box. The membrane is the water barrier; the O-ring is the acoustic seal.
  2. **Rain hood** — **tool-free slide-on/snap-fit** (so the membrane can be added later without disassembly), slides over the box, about 15 mm overhang on all sides and skirted below the bottom face so wind-driven rain can't hit the vent directly. Leaves an open air path to the mic port.
  3. **Mount bracket** — screws to the box's mounting lugs; hose-clamp/strap slots (post/tree), screw holes (fence), and a 1/4-20 heat-set insert.
- **Overall size target:** about 75 × 70 × 50 mm with hood and mount.
- **No desiccant:** the acoustic vent is vapor-permeable, so desiccant would saturate within weeks. Moisture control is via downward-facing vent/gland, drip loop, hood, and the XIAO's slight self-heating. Optional: conformal coat on the XIAO only (never on the mic or its port).
- Muted print color (gray/brown/green).
- CAD: model around the purchased box's measured internal dims; publish `.step` + `.3mf` under `3d print files/outdoor mic housing/`, mirroring the existing folder layout.

### Power
- **GFCI-protected** outdoor outlet + **extra-duty (deep)** weatherproof "while-in-use" cover that closes over the plugged-in charger + any UL/CSA-listed USB charger (≥1 A; no outdoor-rated USB chargers exist) + **1–2 m** USB-A cable (the mic mounts near the outlet), USB-C end cut off and soldered as above, with a drip loop below the box. Voltage drop is negligible at this length. If the mount moves farther than about 5 m from the outlet, splice in outdoor/UV-rated 18–20 AWG 2-conductor cable.

## 3. Software — Display App

### Current state (what changes)
- The mic IP is hardcoded as `10.42.0.50` in `birdnet_display.py` `/audio_status` and in `rtsp_monitor.py`. This only works with the author's Pi-hosted AP (`ap_setup.sh`). On home Wi-Fi the mic gets a DHCP address.

### New module: `mic_manager.py`
One place that knows how to find and talk to the mic.

- `discover() -> MicInfo | None` — mDNS browse for `_http._tcp` services named `esp32mic-*` (via `zeroconf`); verify by `GET /api/status`. Fallback: probe the last known IP from `mic_config.json`.
- `get_status()` — wraps `GET /api/status` (streaming, `wifi_rssi`, stream URLs, `fw_version`) and `GET /api/thermal`.
- `set_gain(value)`, `set_highpass(enabled, cutoff_hz)` — `POST /api/set` with header `X-ESP32MIC-CSRF: 1` and `key=...&value=...` body.
- `restart()` — `POST /api/action/reboot` (same CSRF header).
- `forget()` — clears `mic_config.json`.
- Persists `{hostname, mac, last_ip, added_at}` in `mic_config.json` (next to `pinned_species.json`; add to `.gitignore`).

### New module: `mic_provisioner.py` ("Add microphone")
Runs as a background job; exposes progress for the UI to poll. Steps:

1. **Find mic setup AP** — `nmcli dev wifi list ifname wlan0`, look for SSID `ESP32-RTSP-Mic-AP`. If absent, tell the user to unplug/replug the mic and retry scanning for up to about 2 minutes.
2. **Read home Wi-Fi creds** from the active NetworkManager connection on `wlan0` (`nmcli -s -g 802-11-wireless.ssid,802-11-wireless-security.psk connection show <name>`). Requires the existing polkit/netdev setup from `install.sh`.
3. **Join the setup AP** on `wlan0` (open network), via a temporary NM connection profile.
4. **Hand over credentials** — `POST http://192.168.4.1/wifisave` with `s=<ssid>&p=<psk>` (WiFiManager standard endpoint).
5. **Return to home Wi-Fi** — `nmcli con up <home>`; delete the temporary profile.
6. **Discover the mic** on the home LAN via `mic_manager.discover()` (retry for about 90 s while it reboots/joins).
7. **Point BirdNET-Go at the mic** (see below), save `mic_config.json`, report success.

**Invariants:**
- Any failure, exception, or timeout after step 3 **always** runs step 5 first, then reports the error.
- A watchdog also restores home Wi-Fi if the job dies (for example `systemd-run --on-active=180 nmcli con up <home>` armed before step 3 and cancelled after step 5).
- The WiFiManager portal on the mic times out after **180 s** and the mic restarts, so steps 3–4 must complete inside that window. Step 1 restarts the clock if the AP disappears.
- UI shows: "Setting up the microphone — the display will be offline for about a minute."

### Keeping BirdNET-Go pointed at the mic
- Preferred: configure BirdNET-Go's RTSP source as `rtsp://<hostname>.local:8554/audio1` **if** the BirdNET-Go runtime (Docker container by default) resolves mDNS. Then IP changes never matter.
- Otherwise: on discovery, if the IP changed, update the RTSP URL in BirdNET-Go's config (settings API if available, else `config.yaml` → `realtime.rtsp.urls`) and restart the `birdnet-go` service.
- **To verify during implementation:** BirdNET-Go's settings API and config path for the install method used by `install.sh`, and mDNS resolution inside its container.

### Existing code changes
- `/audio_status` → use `mic_manager.get_status()` against the discovered mic; same response shape `{connected, rssi}` so the existing UI keeps working.
- `rtsp_monitor.py` → read the mic address from `mic_config.json` instead of the hardcoded IP.
- `requirements.txt` → add `zeroconf`.
- `install.sh` → new optional steps (see §4) and copy the new modules.

### New Flask routes
| Route | Method | Purpose |
|---|---|---|
| `/api/mic/status` | GET | Status block (connected, RSSI, streaming, temperature, hostname, firmware) |
| `/api/mic/settings` | POST | `{gain}` or `{highpass_enabled, highpass_cutoff}` |
| `/api/mic/restart` | POST | Restart mic |
| `/api/mic/forget` | POST | Remove/replace mic |
| `/api/mic/provision` | POST | Start "Add microphone" job |
| `/api/mic/provision/status` | GET | Job progress (step, message, done, error) |
| `/api/remote_help/status` | GET | `{connected, last_handshake_seconds}` from `wg show wg0 latest-handshakes` |

### UI (`static/index.html`)
- Settings modal gets a **Microphone** button, opening a new `#micModal` built like the existing Wi-Fi/Pinned modals.
- `#micModal`: status block; **Sensitivity** slider (gain); **Reduce wind/traffic noise** toggle (high-pass); **Restart mic**; **Remove / replace mic**; **Add microphone** with step-by-step progress.
- The existing corner mic icon becomes tappable → opens `#micModal`.
- Settings modal shows a small **Remote help** dot (green = handshake < 3 min).

## 4. Remote Help (WireGuard)

**Principle:** parents do nothing. Chris configures and tests everything on his own network before gifting.

- **Bench script `setup_remote_help.sh`** (run once by Chris, on the Pi):
  1. Installs `wireguard-tools`; generates the Pi's keypair on the Pi (private key never leaves it, never committed).
  2. Prompts Chris for: DDNS endpoint `host:port`, server public key, the Pi's VPN address, the VPN subnet.
  3. Writes `/etc/wireguard/wg0.conf`:
     - `AllowedIPs` = VPN subnet only (split tunnel).
     - `PersistentKeepalive = 25`.
  4. Enables `wg-quick@wg0`.
  5. Installs a `reresolve-dns` systemd timer (every 5 min) so the tunnel follows DDNS changes.
  6. Prints the `[Peer]` block for Chris to add to his server.
  7. Warns if the local LAN subnet overlaps the VPN subnet.
- **Access:** `ssh <user>@<pi-vpn-ip>`; mic web UI via `ssh -L 8081:<mic-ip>:80 <user>@<pi-vpn-ip>` → `http://localhost:8081`.
- **At the parents' house:** after they join Wi-Fi on the touchscreen, the tunnel comes up on its own. Wi-Fi changes later go through the existing on-screen Wi-Fi screen; the tunnel recovers automatically.
- SSH hardening: key-only auth, password login disabled (Chris's key pre-installed on the bench).

## 5. Error Handling Summary

| Situation | Behavior |
|---|---|
| Mic offline / unreachable | Corner icon gray + existing disconnected overlay; mic modal shows "Not connected" with Restart hidden and "Add microphone" offered. |
| Mic IP changed | Rediscovered via mDNS on next status poll; BirdNET-Go updated if needed. |
| Provisioning fails mid-way | Home Wi-Fi restored first (and watchdog backstop); plain-language error + Retry. |
| Mic setup AP not found | "Unplug the microphone's power for 5 seconds, then plug it back in" + auto-rescan. |
| Wrong/changed home Wi-Fi password on mic | Mic falls back to its setup AP by itself; "Add microphone" re-provisions. |
| Tunnel down | Remote-help dot gray; no user-facing error (it's for Chris). |
| Mic overheating | Firmware thermal latch; status block shows temperature/warning. |

## 6. Testing

- **Unit (pytest):** `mic_manager` and `mic_provisioner` with the mic HTTP API and `nmcli`/`subprocess` faked. Cover the happy path, each step's failure, timeout, and the "always restore home Wi-Fi" invariant.
- **Bench integration (Chris's desk):**
  1. Flash the XIAO and wire the mic.
  2. "Add microphone" from the touchscreen.
  3. Confirm BirdNET-Go receives the stream and detects test bird audio.
  4. Change gain/filter from the touchscreen and verify on the mic's web UI.
  5. Pull mic power → display shows offline → plug back in → recovers.
  6. Change the mic's DHCP lease → rediscovery works.
- **Thermal:** fan wired to GPIO with `dtoverlay=gpio-fan,gpiopin=14,temp=70000` (off below 70 °C). Log `vcgencmd measure_temp` / `get_throttled` for 24 h under BirdNET-Go + kiosk; if it never nears 70 °C, the fan may be unplugged (passive).
- **Remote help:** verify SSH and the mic UI tunnel from **off** Chris's network (phone hotspot); reboot the Pi and verify the tunnel returns unattended.
- **Enclosure:** hose/spray test from all sides including upward spray; 24 h outdoors then open and inspect for moisture; compare audio quality (gain/noise) with and without the hood.

## 7. Open Items

- Screen: Hosyond 5" DSI 800x480 (Amazon B0CXTFN8K9; backup iUoyoMon B0F1D5LNPD) — same OEM board as the case's AliExpress screen. Verify corner holes 111.1 × 67.9 mm with calipers and that a Pi 4 (15-pin) DSI cable is included before mounting.
- Measure the received Bud PN-1320-MB (internal dims, lug positions) before final CAD.
- Verify BirdNET-Go RTSP configuration mechanism (§3).
