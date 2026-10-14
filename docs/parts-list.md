# Parts List — BirdNET Display + Outdoor Wi-Fi Mic

**Last updated:** 2026-10-14
**Design spec:** [superpowers/specs/2026-10-14-outdoor-wifi-mic-design.md](superpowers/specs/2026-10-14-outdoor-wifi-mic-design.md)
**Sourcing notes:** [research/sourcing-notes.md](research/sourcing-notes.md)

> Prices are approximate, taken from cached listing snapshots. DigiKey blocks automated access, so check each live page for price and stock before checkout.

## DigiKey Cart (as built, DigiKey Canada, 2026-10-14)

Prices in CAD. Subtotal **$256.49**, shipping free (FedEx International Priority).

| Qty | DigiKey PN | Mfr PN | Item | Unit | Ext |
|---:|---|---|---|---:|---:|
| 2 | 1597-113991054-ND | 113991054 | Seeed XIAO ESP32-C3 | 8.38 | 16.76 |
| 2 | 1528-1908-ND | 3421 | Adafruit SPH0645LM4H breakout | 10.41 | 20.82 |
| 2 | 377-1878-ND | PN-1320-MB | Bud PN-1320-MB gray box | 12.61 | 25.22 |
| 2 | 2291-50.007PA/SW/G-ND | 50.007PA/SW/G | Jacob PG7 gland + locknut | 2.14 | 4.28 |
| 1 | 1528-1877AD-ND | 1877 | 26 AWG silicone wire, red | 1.42 | 1.42 |
| 1 | 1528-1880-ND | 1880 | 26 AWG silicone wire, green | 1.42 | 1.42 |
| 1 | 1528-1882AD-ND | 1882 | 26 AWG silicone wire, white | 1.42 | 1.42 |
| 1 | 1528-392-ND | 392 | 0.1" male header, 10-pack | 7.41 | 7.41 |
| 1 | 2648-SC0194(9)-ND | SC0194(9) | Raspberry Pi 4B 4 GB | 149.79 | 149.79 |
| 1 | 2648-SC0445-ND | SC0445 | Raspberry Pi 15 W USB-C PSU | 11.98 | 11.98 |
| 1 | 1597-114992661-ND | 114992661 | Seeed Armor Lite heatsink + PWM fan | 15.97 | 15.97 |

> Before checkout: compare the Pi 4 price at Canadian resellers (PiShop.ca, BuyaPi.ca, CanaKit). Amazon items should come from **amazon.ca**.

## DigiKey — Mic Unit

| Qty | Part | Mfr PN | DigiKey PN | Approx | Notes |
|---:|---|---|---|---|---|
| 2 | Seeed XIAO ESP32-C3 (includes U.FL antenna) | 113991054 | (see page) | ~$5 ea | 1 spare. Switched from C6 (0 in stock 2026-10-14). Firmware-supported; Wi-Fi 4 is fine for one audio stream |
| 2 | Adafruit SPH0645LM4H I2S MEMS mic breakout | 3421 | 1528-1908-ND | ~$7 ea | 1 spare; the bare chip is going obsolete. Header strip ships loose |
| 2 | Bud PN-1320-MB enclosure, gray, with brackets | PN-1320-MB | 377-1878-ND | ~$7.90 ea | 64×58×35 ext / 58×52×30 int, IP65/66. 1 for drilling practice |
| 2 | Jacob PG7 nylon cable gland + locknut, IP68 | 50.007PA/SW/G | — | <$1 ea | 3–6.5 mm cable |
| 1 | Adafruit 26 AWG silicone wire, 2 m, red | 1877 | — | $0.95 | |
| 1 | Adafruit 26 AWG silicone wire, 2 m, black | 1880 | — | $0.95 | |
| 1 | Adafruit 26 AWG silicone wire, 2 m, 3rd color | 1882 | — | $0.95 | |
| 1 | Adafruit 0.1" male header strip, 10-pack | 392 | 1528-392-ND | $4.95 | For the XIAO |

## DigiKey — Display Unit

| Qty | Part | Mfr PN | DigiKey PN | Approx | Notes |
|---:|---|---|---|---|---|
| 1 | Raspberry Pi 4 Model B, 4 GB | SC0194(9) | 1690-RASPBERRYPI4B-4GB-ND | **check** | Pi prices rose in 2025–26; snapshots conflict |
| 1 | Raspberry Pi 15 W USB-C power supply, US, white | SC0445 | 2648-SC0445-ND | $8 | Black SC0218 shows 0 stock |
| 1 | Seeed Armor Lite heatsink with PWM fan, Pi 4 | 114992661 | 1597-114992661-ND | ~$9.90 | Same design as the case's GeeekPi. Fan is thermostat-controlled (off below 70 °C) |

## Amazon

| Qty | Part | Notes |
|---:|---|---|
| 1 | **Hosyond 5" DSI 800×480 IPS capacitive touchscreen** — ASIN [B0CXTFN8K9](https://www.amazon.com/dp/B0CXTFN8K9) | ~$35. Same OEM board as the case's AliExpress screen. Backup: iUoyoMon [B0F1D5LNPD](https://www.amazon.com/dp/B0F1D5LNPD). **Not** Waveshare (holes 2 mm wider) |
| 1 | 15-pin DSI FFC ribbon cable for Raspberry Pi 4, ~15–20 cm | Screen ships with a Pi 5 cable |
| 1 | High-endurance microSD, 32–64 GB: Samsung PRO Endurance, SanDisk High Endurance, or Kingston High Endurance | ~$10–20. Buy "shipped and sold by Amazon" to avoid fakes. (DigiKey Kingston was ~$112 CAD) |
| 1 | Waterproof acoustic membrane vent stickers, ePTFE, ~6–10 mm | Search "waterproof acoustic membrane vent sticker". Not on DigiKey |
| 1 | M2.5 heat-set inserts, M2.5 × D3.5 × L3 | 4 for display, 6 for mic |
| 1 | M2.5 button-head screw kit (4 / 6 / 8 mm) | Display: 4× 4 mm, 4× 8 mm; mic: 2× 4 mm |
| 1 | M2.5 countersunk screws (4 / 6 / 8 mm) | Display: 2× 4 mm, 2× 8 mm; mic: 4× 6 mm |
| 1 | M2 × 6 mm button-head screws | Need 2 |
| 1 | 1/4-20 heat-set insert (CNC Kitchen short style or similar) | Optional, for camera-thread mounting |
| 1 | Metric silicone O-ring assortment | Need ~10 mm ID × 1.5 mm (mic-to-port acoustic seal) |

## Hardware Store

| Qty | Part | Notes |
|---:|---|---|
| 1 | **Extra-duty (deep)** weatherproof "while-in-use" bubble outlet cover | Must close fully over the plugged-in charger; cord exits the bottom. Also confirm the outlet is **GFCI-protected** (TEST/RESET) |
| 2 | Stainless hose clamps, sized for the post/tree | Mic mount |

## Already Have

- ASA filament (all printed parts), TPU (backup), soldering iron
- Spare USB-A to USB-C cable, 1–2 m (mic power; USB-C end gets cut and soldered through the gland)
- Spare **UL/CSA-listed** USB charger, ≥1 A (mic draws ~0.3 A). No outdoor-rated USB chargers exist; the in-use cover provides the wet-location protection

## Deliberately Not Buying

- **Silica gel / desiccant** — the acoustic vent is vapor-permeable, so desiccant would saturate within weeks.
- **Conformal coating** — optional later, XIAO only, never on the mic.

## On Arrival — Checks

- [ ] Screen corner-hole spacing ≈ **111.1 × 67.9 mm** (calipers, ±0.3 mm) before mounting
- [ ] Screen PCB outline ≈ 121.1 × 77.9 mm; "Backlight" button top-left
- [ ] Pi 4 (15-pin) DSI cable present
- [ ] Armor Lite hole layout matches the Pi/screen mounting
- [ ] Measure Bud PN-1320-MB internal dims and lug positions → feed into the CAD

## Copy-Paste Version

```
BIRDNET DISPLAY + OUTDOOR WI-FI MIC — PARTS LIST (2026-10-14)
Prices are approximate; check each live page before checkout.

=== DIGIKEY: MIC UNIT ===
2x  Seeed XIAO ESP32-C3 (includes U.FL antenna) .... Mfr PN 113991054                            ~$5 ea  (1 spare)
2x  Adafruit SPH0645LM4H I2S MEMS mic breakout ..... Mfr PN 3421        (DK 1528-1908-ND)       ~$7 ea     (1 spare)
2x  Bud PN-1320-MB enclosure, gray, w/ brackets .... Mfr PN PN-1320-MB  (DK 377-1878-ND)        ~$7.90 ea  (1 for drilling practice)
2x  Jacob PG7 nylon cable gland + locknut, IP68 .... Mfr PN 50.007PA/SW/G                        <$1 ea
1x  Adafruit 26 AWG silicone wire, 2 m (red) ....... Mfr PN 1877                                 $0.95
1x  Adafruit 26 AWG silicone wire, 2 m (black) ..... Mfr PN 1880                                 $0.95
1x  Adafruit 26 AWG silicone wire, 2 m (3rd color) . Mfr PN 1882                                 $0.95
1x  Adafruit 0.1" male header strip, 10-pack ....... Mfr PN 392         (DK 1528-392-ND)        $4.95

=== DIGIKEY: DISPLAY UNIT ===
1x  Raspberry Pi 4 Model B, 4 GB ................... Mfr PN SC0194(9)   (DK 1690-RASPBERRYPI4B-4GB-ND)  CHECK PRICE
1x  Raspberry Pi 15 W USB-C power supply, US, white  Mfr PN SC0445      (DK 2648-SC0445-ND)     $8
1x  Seeed Armor Lite heatsink w/ PWM fan, Pi 4 ..... Mfr PN 114992661   (DK 1597-114992661-ND)  ~$9.90

=== AMAZON ===
1x  Hosyond 5" DSI 800x480 IPS capacitive touchscreen   ASIN B0CXTFN8K9  ~$35
      (backup: iUoyoMon 5" DSI 800x480, ASIN B0F1D5LNPD)
1x  15-pin DSI FFC ribbon cable for Raspberry Pi 4, ~15-20 cm  (screen ships with a Pi 5 cable)
1x  High-endurance microSD 32-64 GB (Samsung PRO Endurance / SanDisk High Endurance / Kingston High Endurance)  (sold by Amazon, avoid fakes)
1x  Waterproof acoustic membrane vent stickers, ePTFE, ~6-10 mm  (search: "waterproof acoustic membrane vent sticker")
1x  M2.5 heat-set threaded inserts, M2.5 x D3.5 x L3  (need 4+ for display, 6 for mic)
1x  M2.5 button-head screw kit incl. 4 mm, 6 mm, 8 mm  (need 4x 4 mm, 4x 8 mm button-head)
1x  M2.5 countersunk screws, 4 mm / 6 mm / 8 mm  (need 2x 4 mm, 2x 8 mm display; 4x 6 mm mic)
1x  M2 x 6 mm button-head screws  (need 2)
1x  1/4-20 heat-set insert (CNC Kitchen short style or similar)  (need 1, optional)
1x  Metric silicone O-ring assortment  (need ~10 mm ID x 1.5 mm)

=== HARDWARE STORE ===
1x  Extra-duty (deep) weatherproof "while-in-use" bubble outlet cover  (must close over the charger; confirm outlet is GFCI)
2x  Stainless hose clamps, sized for the post/tree  (for the mic mount)

=== ALREADY HAVE ===
ASA filament (all printed parts), TPU (backup), soldering iron
Spare USB-A to USB-C cable, 1-2 m (mic power; gets cut)
Spare UL/CSA-listed USB charger, >=1 A (lives under the in-use cover)
```
