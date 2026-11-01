#!/usr/bin/env python3
"""Extra simulation chapters: CAD plates, electronics, LED/fill."""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

sys.path.insert(0, "/home/user/scripts")
import render_live_motion as M

ROOT = Path("/home/user")
CAD = ROOT / "static" / "cad"
PARTS = ROOT / "sim_out"
W, H, FPS = 1280, 720, 30
FF = imageio_ffmpeg.get_ffmpeg_exe()
GREEN, WHITE = M.GREEN, M.WHITE
F_H, F_S, F_M, F_T, F_BIG = M.F_H, M.F_S, M.F_M, M.F_T, M.F_BIG


def kenburns(path, t, dur, zoom0=1.02, zoom1=1.14):
    im = Image.open(path).convert("RGB")
    k = M.ease(t / max(dur, 0.001))
    zoom = M.lerp(zoom0, zoom1, k)
    scale = max(W / im.width, H / im.height) * zoom
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    x = max(0, min(nw - W, int((nw - W) * k * 0.55)))
    y = max(0, min(nh - H, int((nh - H) * (1 - k) * 0.4)))
    return im.crop((x, y, x + W, y + H))


def bar(d, title, sub, part):
    d.rectangle((0, 0, W, 46), fill=(16, 18, 20))
    d.rectangle((0, 44, W, 46), fill=GREEN)
    d.text((20, 24), "BIN-GENIE", font=F_H, fill=GREEN, anchor="lm")
    d.text((160, 24), "MOTION STUDY  ·  extended", font=F_M, fill=(150, 156, 164), anchor="lm")
    d.text((W - 20, 24), part, font=F_M, fill=WHITE, anchor="rm")
    d.rectangle((0, H - 58, W, H), fill=(16, 18, 20))
    d.text((22, H - 36), title, font=F_H, fill=WHITE, anchor="lm")
    d.text((22, H - 14), sub, font=F_S, fill=(168, 174, 180), anchor="lm")


def encode_frames(path, frames):
    proc = subprocess.Popen([
        FF, "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "17", "-preset", "fast", "-movflags", "+faststart", str(path),
    ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    n = 0
    for img in frames:
        proc.stdin.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes())
        n += 1
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="ignore")
    rc = proc.wait()
    if rc:
        raise SystemExit(err[-2000:])
    print(f"  {path.name:28} {n/FPS:5.1f}s  {path.stat().st_size/1e6:.1f}MB")


# ---------- 00 CAD plates ----------
def part_cad():
    shots = [
        (CAD / "exterior_clean.png", 3.6,
         "0  Your SolidWorks housing",
         "Black ABS  ·  green LED rim  ·  chrome intake window"),
        (CAD / "carousel_clean.png", 3.6,
         "0  Dual-disc carousel (your part)",
         "Two stacked discs, same sector pocket, shaft + back plate"),
        (CAD / "exploded_clean.png", 4.2,
         "0  Four cylindrical bays",
         "Left: PA-02 paper + RS-04 residual    Right: GL-03 glass + PM-01 plastic/metal"),
    ]
    labels_exploded = [
        (230, 250, "PA-02  Paper"),
        (230, 430, "RS-04  Residual"),
        (640, 118, "Dual carousel + pocket"),
        (1040, 240, "GL-03  Glass"),
        (1040, 470, "PM-01  Plastic / Metal"),
    ]

    def gen():
        for path, dur, title, sub in shots:
            n = int(dur * FPS)
            for i in range(n):
                t = i / FPS
                img = kenburns(path, t, dur)
                d = ImageDraw.Draw(img)
                bar(d, title, sub, "CAD")
                if "exploded" in path.name and t > 0.8:
                    for x, y, s in labels_exploded:
                        d.text((x, y), s, font=F_S, fill=(18, 20, 22), anchor="mm")
                yield img

    encode_frames(PARTS / "00_cad_design.mp4", gen())


# ---------- electronics 3D ----------
PCB = (28, 110, 62)
GOLD = (210, 170, 70)
RED = (220, 50, 50)
IR = (255, 70, 70)
CAMB = (18, 18, 20)
BLUE = (70, 140, 220)


def electronics_faces(t, ir_on, horn1, horn2):
    f = []
    f += M.static_plant()
    f += M.disc(0, 0.96, 0, 0.33, 0.04, horn1, M.SILVER)
    f += M.disc(0, 0.90, 0, 0.33, 0.04, horn2, (168, 174, 180))
    f += M.cyl(0, 0.98, 1.05, 0, 0.032, (22, 22, 24), segs=10)
    f += M.servo_placed(1, horn1)
    f += M.servo_placed(2, horn2)
    # ESP32 on the back plate
    f += M.box(-0.11, 0.11, 0.22, 0.24, -0.41, -0.18, PCB, emit=True)
    f += M.box(-0.04, 0.04, 0.24, 0.27, -0.36, -0.24, (40, 40, 44))  # USB/chip
    f += M.box(-0.09, -0.06, 0.24, 0.255, -0.38, -0.34, GOLD, emit=True)
    f += M.box(0.06, 0.09, 0.24, 0.255, -0.38, -0.34, GOLD, emit=True)
    # camera over the pocket
    f += M.box(0.18, 0.32, 1.18, 1.30, 0.38, 0.50, CAMB)
    f += M.cyl(0.25, 1.20, 1.28, 0.50, 0.035, (40, 80, 120), segs=12, emit=True)
    f += M.cyl(0.30, 1.28, 1.32, 0.44, 0.012, RED if (int(t * 6) % 2 == 0) else (80, 20, 20), segs=8, emit=True)
    # IR pair across the pocket
    f += M.box(-0.36, -0.30, 1.00, 1.08, 0.10, 0.16, (30, 30, 32))
    f += M.box(0.30, 0.36, 1.00, 1.08, 0.10, 0.16, (30, 30, 32))
    if ir_on:
        f += M.box(-0.30, 0.30, 1.035, 1.045, 0.125, 0.135, IR, emit=True)
    # moisture probes near residual
    x, z = M.BINS["RS-04"]["pos"]
    f += M.cyl(x - 0.04, 0.64, 0.78, z, 0.012, SILVER := (180, 180, 185), segs=8)
    f += M.cyl(x + 0.04, 0.64, 0.78, z, 0.012, SILVER, segs=8)
    # metal coil (ring) near PM-01
    mx, mz = M.BINS["PM-01"]["pos"]
    f += M.cyl(mx, 0.66, 0.70, mz, 0.17, GOLD, segs=16, top=False, bot=False, emit=True)
    f += M.cyl(mx, 0.66, 0.70, mz, 0.14, (40, 40, 20), segs=16, top=False, bot=False)
    # jumper wires ESP32 → servos (thin boxes)
    f += M.box(-0.02, 0.02, 0.10, 0.14, 0.20, 0.58, RED)
    f += M.box(-0.06, -0.02, 0.10, 0.14, -0.20, 0.20, (30, 80, 200))
    f += M.box(0.02, 0.06, 0.10, 0.14, -0.20, 0.20, (220, 180, 40))
    return f


def part_electronics():
    dur = 12.0
    n = int(dur * FPS)
    cam0 = M.Cam(az=0.2, el=1.05, dist=6.8, scale=310, look=(0, 0.45, 0.1), origin=(640, 400))
    cam1 = M.Cam(az=-0.15, el=0.7, dist=5.6, scale=420, look=(0.0, 0.28, -0.1), origin=(640, 410))
    cam2 = M.Cam(az=0.35, el=0.95, dist=6.4, scale=340, look=(0.2, 0.9, 0.3), origin=(640, 400))

    def gen():
        for i in range(n):
            t = i / FPS
            u = t / dur
            if u < 0.35:
                cam = M.cam_mix(cam0, cam1, u / 0.35)
            else:
                cam = M.cam_mix(cam1, cam2, (u - 0.35) / 0.65)
            horn1 = 0.4 * math.sin(t * 1.6)
            horn2 = 0.9 + 0.35 * math.sin(t * 1.1 + 0.7)
            ir_on = (t % 1.2) < 0.7
            faces = electronics_faces(t, ir_on, horn1, horn2)
            img = M.bg()
            M.draw(img, faces, cam)
            d = ImageDraw.Draw(img)
            bar(d, "Electronics on the same plant",
                "ESP32  ·  tray camera  ·  IR break-beam  ·  moisture probes  ·  inductive coil  ·  2× servo",
                "ELEC")
            # floating labels
            tags = [
                ((0.0, 0.30, -0.28), "ESP32", GREEN),
                ((0.25, 1.32, 0.48), "CAMERA", (90, 175, 230)),
                ((0.0, 1.08, 0.13), "IR BEAM" if ir_on else "IR CLEAR", IR if ir_on else (140, 140, 140)),
                ((-0.58, 0.82, -0.28), "MOISTURE", (230, 160, 70)),
                ((0.58, 0.78, 0.28), "METAL COIL", GOLD),
                ((0.26, 0.28, 0.58), "SERVO 1", GREEN),
                ((-0.26, 0.28, 0.58), "SERVO 2", (90, 175, 230)),
            ]
            for pos, lab, col in tags:
                q = cam.project(np.array([pos], np.float32))[0]
                d.text((float(q[0]), float(q[1])), lab, font=F_T, fill=col, anchor="mm")
            # signal strip
            d.rounded_rectangle((40, 64, 820, 108), 8, fill=(16, 18, 20))
            d.text((50, 86), "CAMERA + IR + MOIST + METAL   →   ESP32   →   SERVO 1 / SERVO 2",
                   font=F_M, fill=WHITE, anchor="lm")
            yield img

    encode_frames(PARTS / "00b_electronics.mp4", gen())


def part_led_fill():
    """Orbit the filled plant, LED rim in bay colour, full-bay warning."""
    dur = 8.0
    n = int(dur * FPS)
    M.load_tokens()

    def gen():
        for i in range(n):
            t = i / FPS
            az = 0.15 + 0.9 * (t / dur)
            cam = M.Cam(az=az, el=1.05, dist=7.0, scale=300, look=(0, 0.38, 0.1), origin=(640, 400))
            faces = []
            faces += M.static_plant()
            faces += M.disc(0, 0.96, 0, 0.33, 0.04, M.bin_ang("RS-04"), M.SILVER)
            faces += M.disc(0, 0.90, 0, 0.33, 0.04, M.bin_ang("RS-04") + M.HOLD, (168, 174, 180))
            faces += M.servo_placed(1, M.bin_ang("RS-04"))
            faces += M.servo_placed(2, M.bin_ang("RS-04") + M.HOLD)
            fills = {"PM-01": 0.85, "PA-02": 0.45, "GL-03": 0.40, "RS-04": 0.55}
            for k, h in fills.items():
                x, z = M.BINS[k]["pos"]
                faces += M.cyl(x, 0.12, 0.12 + 0.42 * h, z, 0.13, M.BINS[k]["hue"], segs=12, bot=False)
            # LED rim in PM colour (full)
            pulse = 0.5 + 0.5 * abs(math.sin(t * 6))
            led = tuple(int(c * pulse) for c in M.BINS["PM-01"]["hue"])
            faces += M.box(-0.72, 0.72, 1.62, 1.645, 0.50, 0.52, led, emit=True)
            faces += M.box(-0.72, 0.72, 1.62, 1.645, -0.52, -0.50, led, emit=True)
            img = M.bg()
            M.draw(img, faces, cam)
            d = ImageDraw.Draw(img)
            bar(d, "PM-01 85%  —  LED rim turns bay colour  —  FULL warning",
                "Facility would stop indexing into a full cylinder and flag the dashboard.",
                "FILL")
            d.rounded_rectangle((40, 64, 420, 150), 8, fill=(16, 18, 20))
            d.text((56, 88), "PM-01  85%  FULL", font=F_H, fill=M.BINS["PM-01"]["hue"], anchor="lt")
            d.text((56, 120), "PA-02 45%   GL-03 40%   RS-04 55%", font=F_T, fill=WHITE, anchor="lt")
            yield img

    encode_frames(PARTS / "05b_led_fill.mp4", gen())


def concat():
    order = [
        "00_cad_design.mp4",
        "01_housing.mp4",
        "02_intake.mp4",
        "00b_electronics.mp4",
        "03_servos.mp4",
        "04_working_sorts.mp4",
        "05b_led_fill.mp4",
        "05_end.mp4",
    ]
    missing = [p for p in order if not (PARTS / p).exists()]
    if missing:
        raise SystemExit(f"missing {missing}")
    lst = PARTS / "concat_extended.txt"
    lst.write_text("".join(f"file '{PARTS/p}'\n" for p in order))
    full = ROOT / "BIN-GENIE_working_simulation.mp4"
    subprocess.check_call(
        [FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(full)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    (ROOT / "static" / "video" / "BIN-GENIE_working_simulation.mp4").write_bytes(full.read_bytes())
    print("FULL", full, f"{full.stat().st_size/1e6:.1f}MB")


if __name__ == "__main__":
    print("extra chapters…")
    part_cad()
    part_electronics()
    part_led_fill()
    concat()
