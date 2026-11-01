# BIN-GENIE serial protocol  (115200 8N1)

Same verbs in the dashboard simulator and on the ESP32 firmware.
Lines are ASCII, newline-terminated, no JSON required.

## Host → device

```
PING
STATUS
SORT plastic_metal
SORT paper
SORT glass
SORT residual
RESET
LED plastic_metal ON
LED paper OFF
```

## Device → host

```
PONG firmware=1.0.0 mode=live
SENSORS ir=1 moist=0.12 metal=0
FILL plastic_metal=12 paper=8 glass=4 residual=21
SORT_OK bin=paper t_ms=1180 disc=90 flap=18
SORT_ERR reason=jam
EVENT item_present
```

## Pin map (ESP32 DevKit)

| Function              | GPIO | Notes                          |
|-----------------------|------|--------------------------------|
| Servo (flap)          | 18   | 500–2400 µs                    |
| Disc STEP             | 19   | A4988 / DRV8825                |
| Disc DIR              | 21   |                                |
| IR obstacle (active LOW) | 32 | Tray occupancy                |
| Moisture (analog)     | 34   | 0–4095 → 0–1.0                 |
| Metal detector        | 35   | HIGH = metal                   |
| LED PM-01             | 25   |                                |
| LED PA-02             | 26   |                                |
| LED GL-03             | 27   |                                |
| LED RS-04             | 14   |                                |

Disc angles: PM-01 = 0°, PA-02 = 90°, GL-03 = 180°, RS-04 = 270°.
Flap opens 18° after the disc settles, holds 400 ms, then closes.
