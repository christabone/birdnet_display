# Sourcing & Research Notes

**Date:** 2026-10-14
Background research behind [../parts-list.md](../parts-list.md) and the [design spec](../superpowers/specs/2026-10-14-outdoor-wifi-mic-design.md).

## Screen identification

- **Original (case designed for):** AliExpress item 1005007091586628 — iPistBit "5-Point DSI Touch Screen Driver-Free 4.3/5/7 Inch 800x480", 800×480 IPS, active area 108×64.8 mm, module 121.1×77.9 mm.
- Its manual ("5inch DSI Display User Manual V1.4") is essentially identical to the **Elecrow DSI05379I** manual, including the dimension drawing. Generic OEM board: blue PCB, "800X480 TN / 800X480 IPS / Capacitive Touch" silkscreen, side "Backlight" button.
- **Measured from the case** (`3d print files/main housing/Threaded inserts/Birdnet rpi case.3mf`, ray-cast):
  - Screen mounting holes ~Ø2.75 mm at **111.0 × 67.75 mm** centres
  - Front window ~111 × 68.25 mm (inside) / ~114.5 × 72 mm (outer face)
  - Shell cavity ~136 × 80 mm

| Item | Case (measured) | OEM board (Elecrow/iPistBit/Hosyond) | Waveshare 5inch DSI |
|---|---|---|---|
| PCB outline | cavity ~136 × 80 | 121.11 × 77.93 | 121 × 76 |
| Viewing area | window ~111 × 68 | 108 × 64.8 | 109 × 65.8 |
| Corner mounting holes | **111.0 × 67.75** | **111.11 × 67.93** | **113 × 68** ✗ |
| Pi standoff pattern | — | 58 × 49 | 58 × 49 |

**Buy options:**
- **Hosyond B0CXTFN8K9** (Amazon, ~$35, ships from Amazon) — same PCB in rear photos. ~90% confidence of identical mechanics.
- **iUoyoMon B0F1D5LNPD** (Amazon, ~$34) — backup, same PCB.
- Elecrow DSI05379I direct (~$35, ships from China) — the reference design; slower.
- **Waveshare 5inch DSI** — does **not** fit as-is: corner holes 113 mm vs 111 mm. Fixable by moving the stand's two hole columns out 1 mm each (x = ±55.5 → ±56.5) or slotting them.
- **Official Raspberry Pi Touch Display 2, 5"** (SC1975, 720×1280 portrait, 143.5 × 91.5 × 16 mm) — would need a case redesign.
- Listings ship a 16 cm **Pi 5** DSI cable; the case is for a Pi 4 (15-pin), so buy a Pi 4 cable if one isn't included.

## DigiKey findings

- DigiKey blocks automated access (Cloudflare 403). Listings were confirmed via search-indexed product pages; **prices and stock are from cached snapshots**.
- **XIAO boards:** C6 (113991254) in stock; C5 (100010048) out of stock, 4-week lead; C3 (113991054) in stock and includes an FPC antenna (fallback); S3 out of stock.
- **C6 antenna:** the board has a ceramic antenna plus U.FL with an RF switch (GPIO3 enable, GPIO14 selects ceramic vs U.FL). The birdnetgo-esp32-rtsp-mic README states the firmware **selects the external antenna path by default on the C6**, so a U.FL antenna is needed.
- **Enclosures:**
  - Bud PN-1320-MB / -CMB (64×58×35 ext, 58×52×30 int, IP65/66, brackets): in stock.
  - Bud PN-1320-AMB (IP68): out of stock, 11-week lead.
  - Hammond 1555B2GY (65×65×40, IP68, ~$14.75): roomier fallback.
  - Hammond 1554B2GYCL: out of stock.
- **Acoustic vents:** DigiKey only has screw-in pressure vents (Amphenol VENT-PS1, Bud IPV, Stewart). Adhesive acoustic membranes (e.g., Gore GAW334) come via samples/distributors or Amazon/AliExpress stickers.
- **Hardware:** no matching M2.5 × D3.5 × L3 inserts (E-Z LOK TH-M25-SV is 4.4 mm OD), no M2.5 stainless button heads, no 1/4-20 heat-set insert product page, no 10 × 1.5 mm silicone O-ring. Buy from Amazon/McMaster.
- **Pi:** Pi 4B 4 GB listed, but price snapshots conflict ($60–100). SC0218 (black PSU) shows 0, so use SC0445 (white).

## Compatibility notes

1. **The USB-C plug won't fit through a PG7 gland** (~6.5 mm bore vs ~8×12 mm overmold). Cut the cable, pass it through the gland, and solder 5 V/GND to the XIAO pads. Flash the firmware over USB first; later updates use OTA.
2. **Fit in the PN-1320 (58×52×30 int):**
   - The boards fit easily.
   - The PG7 gland and nut use ~8–10 mm depth and ~15–17 mm of wall; keep it ≥20 mm from the mic port.
   - A plugged USB-C would barely fit, which is another reason to solder.
3. **Voltage drop:** the L-com 5 m cable is 28 AWG (~2.1 Ω round trip), giving ~0.6 V drop at 300 mA peaks (~4.4 V at the XIAO). Acceptable. For longer runs, splice in 18–20 AWG outdoor cable.
4. **The SPH0645 is bottom-port:** the sound hole is through the breakout PCB. Mount the back face flat to the box wall, with the O-ring around the hole and the membrane on the outside.
5. **Desiccant dropped:** the vent is vapor-permeable, so desiccant would saturate.
6. **Thermal (Pi):** BirdNET-Go is a steady, moderate load. Keep the Armor Lite, set the fan via `dtoverlay=gpio-fan,gpiopin=14,temp=70000`, and log temps for 24 h; unplug the fan if it never nears 70 °C.

## Mic firmware facts relied on

From [Sukecz/birdnetgo-esp32-rtsp-mic](https://github.com/Sukecz/birdnetgo-esp32-rtsp-mic) v1.26 (reference clone at `../ref/birdnetgo-esp32-rtsp-mic`):

- First boot / failed saved Wi-Fi: WiFiManager portal **`ESP32-RTSP-Mic-AP`** at 192.168.4.1. `setConfigPortalTimeout(180)`, then it restarts and retries. Credentials go to `/wifisave` (`s`, `p`).
- mDNS hostname `esp32mic-xxxxxx.local`; advertises `_http._tcp` on port 80.
- JSON API: `GET /api/status`, `/api/audio_status`, `/api/thermal`; `POST /api/set` (`key=…&value=…`), `POST /api/action/reboot`. POSTs need header `X-ESP32MIC-CSRF: 1`.
- `mic_format=1` for the SPH0645 (MSB / left-justified).
- RTSP: `rtsp://<host>:8554/audio1`.
