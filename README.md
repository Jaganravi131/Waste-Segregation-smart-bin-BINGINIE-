# BIN-GENIE

AI-assisted smart waste bin. This repository has two parts:

| Path | What it is |
|---|---|
| `src/` | Product website (Vite + React + Tailwind) |
| `plant/` | Live classifier, sensor-fusion dashboard, hardware bridge |
| `firmware/` | ESP32 sketch speaking the same serial protocol as the dashboard simulator |
| `demo/` | Process-flow spec sheet + working simulation video |

Four bays (matches the mechanical carousel):

| Angle | Stream |
|---|---|
| 0° | Biodegradable (organic) |
| 90° | Dry / recyclable |
| 180° | E-waste |
| 270° | Residual / unknown |

Vision proposes a class. **HC-SR04, moisture, and inductive metal can veto it.** A stepper (NEMA17 via DRV8825 in the BOM, ESP32 serial in the current firmware) indexes the carousel, then returns **HOME** on the limit switch.

---

## Demo video

[`demo/BIN-GENIE_process_demo.mp4`](demo/BIN-GENIE_process_demo.mp4) — STM32/TinyML flow, parts callouts, homing, four live sorts.

Spec sheet: [`demo/process_flow.png`](demo/process_flow.png)

---

## Plant dashboard (no physical bin required)

```bash
cd plant
python3 -m pip install -r requirements.txt
python3 run.py
```

Open `http://127.0.0.1:8000`.

- **Plant** — four bays, disc, sensors, sort ticket  
- **Sort** — upload, webcam, or labelled gallery  
- **Log** — SQLite history + CSV  
- **Bay** — simulated serial (`SORT plastic_metal` / `SORT_OK …`). Plug in a board later; verbs do not change.  
- **Proof** — ten-item run with IST timestamps  

Optional Roboflow (do **not** commit a key; rotate any key that was ever in an old `detect.py`):

```bash
export ROBOFLOW_API_KEY=...
export ROBOFLOW_MODEL=garbage-classification-3/2
python3 run.py
```

Hardware later: flash `firmware/bin_genie_esp32/bin_genie_esp32.ino`, connect `COM3` or `/dev/ttyUSB0` on the Bay tab. Protocol: `firmware/PROTOCOL.md`.

---

## Website

```bash
npm install
npm run dev
```

Node 18+. Production: `npm run build`.

---

## Layout

```
plant/app/           FastAPI, classifier, fusion, SQLite, serial/sim
plant/static/        UI, calibration gallery, CAD stills
plant/templates/     control-room SPA
plant/models/        MobileNetV2 ONNX (offline vision fallback)
firmware/            ESP32 + line protocol
demo/                simulation + process-flow diagram
src/                 marketing site
```

Offline vision order: labelled sample → optional Roboflow → MobileNetV2 waste map → color-texture forest → sensor fusion.
