#!/usr/bin/env python3
"""BIN-GENIE working demo matching the process-flow infographic:
STM32H743, OV2640, HC-SR04, moisture, inductive, NEMA17+DRV8825,
limit-switch homing, 4-compartment carousel 0/90/180/270.
"""
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
SAMPLES = ROOT / "static" / "samples"
W, H, FPS = 1280, 720, 30
FF = imageio_ffmpeg.get_ffmpeg_exe()

GREEN = (46, 180, 70)
YELLOW = (230, 190, 40)
ORANGE = (230, 120, 40)
RED = (210, 50, 50)
WHITE, BLACK = (250, 250, 250), (28, 28, 30)
SILVER = (190, 196, 202)
NAVY = (16, 28, 48)
PCB = (20, 90, 50)
PURPLE = (90, 50, 130)
BLUE = (40, 90, 180)
GOLD = (210, 170, 70)

F_H, F_S, F_M, F_T, F_BIG = M.F_H, M.F_S, M.F_M, M.F_T, M.F_BIG
F_H2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)

BINS = [
    dict(deg=0,   key="BIO", title="Biodegradable (Organic)", hue=GREEN,  short="0°  ORGANIC"),
    dict(deg=90,  key="DRY", title="Dry / Recyclable",        hue=YELLOW, short="90°  DRY"),
    dict(deg=180, key="EW",  title="E-waste",                 hue=ORANGE, short="180° E-WASTE"),
    dict(deg=270, key="RES", title="Residual",                hue=RED,    short="270° RESIDUAL"),
]
R_BIN = 0.42

STEPS = [
    "1  Waste detection   HC-SR04",
    "2  Image capture     OV2640",
    "3  TinyML on STM32",
    "4  Moisture + inductive",
    "5  Final decision",
    "6  NEMA17 via DRV8825",
    "7  Drop into bay",
    "8  Return HOME (limit)",
    "9  Wait for next",
]

CYCLES = [
    dict(kind="organic", name="Banana peel", vis="Organic", conf=0.93, moist=0.72, metal=0, target=0,  token="banana_peel.jpg"),
    dict(kind="dry",     name="PET bottle",  vis="Dry / Recyclable", conf=0.91, moist=0.08, metal=0, target=90, token="plastic_bottle.jpg"),
    dict(kind="ewaste",  name="PCB scrap",   vis="E-waste", conf=0.88, moist=0.05, metal=1, target=180, token="ewaste_pcb.jpg"),
    dict(kind="unknown", name="Unknown item", vis="Unknown", conf=0.31, moist=0.12, metal=0, target=270, token="food_waste.jpg"),
]

TOK = {}


def load_tok():
    for c in CYCLES:
        p = SAMPLES / c["token"]
        im = Image.open(p).convert("RGB")
        im.thumbnail((44, 44), Image.Resampling.LANCZOS)
        cnv = Image.new("RGB", (44, 44), (30, 30, 32))
        cnv.paste(im, ((44 - im.width) // 2, (44 - im.height) // 2))
        msk = Image.new("L", (44, 44), 0)
        ImageDraw.Draw(msk).ellipse((1, 1, 42, 42), fill=255)
        TOK[c["kind"]] = (cnv, msk)


def paste(img, kind, xy, sc=1.0):
    tok, msk = TOK[kind]
    s = max(10, int(44 * sc))
    img.paste(tok.resize((s, s), Image.Resampling.LANCZOS),
              (int(xy[0] - s / 2), int(xy[1] - s / 2)),
              msk.resize((s, s), Image.Resampling.LANCZOS))


def bar(d, title, sub, t, step_i=-1):
    d.rectangle((0, 0, W, 44), fill=NAVY)
    d.rectangle((0, 42, W, 44), fill=GREEN)
    d.text((18, 22), "BINGENIE", font=F_H, fill=GREEN, anchor="lm")
    d.text((150, 22), "STM32H743  ·  TinyML  ·  NEMA17 carousel", font=F_M, fill=(160, 170, 180), anchor="lm")
    d.text((W - 16, 22), f"{t:05.1f}s", font=F_M, fill=WHITE, anchor="rm")
    d.rectangle((0, H - 54, W, H), fill=NAVY)
    d.text((18, H - 34), title, font=F_H2, fill=WHITE, anchor="lm")
    d.text((18, H - 14), sub, font=F_S, fill=(170, 178, 186), anchor="lm")
    # step list
    d.rounded_rectangle((16, 56, 300, 290), 8, fill=(16, 22, 32))
    for i, s in enumerate(STEPS):
        col = GREEN if i == step_i else ((210, 210, 210) if i < step_i else (110, 118, 128))
        d.text((28, 74 + i * 24), s, font=F_T, fill=col, anchor="lt")


def kenburns(path, t, dur, zoom0=1.0, zoom1=1.12):
    im = Image.open(path).convert("RGB")
    k = M.ease(t / max(dur, 0.001))
    z = M.lerp(zoom0, zoom1, k)
    sc = max(W / im.width, H / im.height) * z
    nw, nh = int(im.width * sc), int(im.height * sc)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    x = max(0, min(nw - W, int((nw - W) * k * 0.5)))
    y = max(0, min(nh - H, int((nh - H) * (1 - k) * 0.45)))
    return im.crop((x, y, x + W, y + H))


# ----- meshes -----
def nema17(cx, y0, cz, spin):
    f = M.box(cx - 0.07, cx + 0.07, y0, y0 + 0.08, cz - 0.07, cz + 0.07, (40, 40, 42))
    f += M.cyl(cx, y0 + 0.08, y0 + 0.10, cz, 0.035, SILVER, segs=12)
    f += M.cyl(cx, y0 + 0.10, y0 + 0.22, cz, 0.012, SILVER, segs=8)
    # spinning mark on shaft
    a = spin
    f += M.box(cx + 0.01 * math.cos(a) - 0.006, cx + 0.01 * math.cos(a) + 0.006,
               y0 + 0.12, y0 + 0.20,
               cz + 0.01 * math.sin(a) - 0.006, cz + 0.01 * math.sin(a) + 0.006,
               GREEN, emit=True)
    return f


def hcsr04(x, y, z):
    f = M.box(x - 0.08, x + 0.08, y, y + 0.02, z - 0.04, z + 0.04, (30, 80, 160))
    f += M.cyl(x - 0.035, y + 0.02, y + 0.05, z, 0.022, SILVER, segs=10)
    f += M.cyl(x + 0.035, y + 0.02, y + 0.05, z, 0.022, SILVER, segs=10)
    return f


def ov2640(x, y, z):
    f = M.box(x - 0.05, x + 0.05, y, y + 0.015, z - 0.05, z + 0.03, PCB, emit=True)
    f += M.cyl(x, y + 0.015, y + 0.04, z + 0.01, 0.018, (30, 50, 80), segs=10)
    return f


def electronics():
    f = []
    # board
    f += M.box(0.72, 1.28, 0.00, 0.03, -0.38, 0.38, (36, 36, 40))
    # STM32
    f += M.box(0.78, 1.02, 0.03, 0.045, -0.28, 0.02, PCB, emit=True)
    f += M.box(0.86, 0.94, 0.045, 0.06, -0.18, -0.08, (40, 40, 44))
    # DRV8825
    f += M.box(1.06, 1.22, 0.03, 0.05, -0.22, 0.02, PURPLE, emit=True)
    # LM2596
    f += M.box(0.80, 1.00, 0.03, 0.055, 0.10, 0.28, BLUE, emit=True)
    # SMPS
    f += M.box(1.04, 1.26, 0.03, 0.12, 0.10, 0.32, SILVER)
    # moisture
    f += M.box(-0.22, -0.08, 0.78, 0.80, 0.52, 0.58, PCB, emit=True)
    f += M.box(-0.18, -0.16, 0.72, 0.78, 0.54, 0.56, SILVER)
    f += M.box(-0.14, -0.12, 0.72, 0.78, 0.54, 0.56, SILVER)
    # inductive LJ12
    f += M.cyl(0.22, 0.70, 0.86, 0.55, 0.025, GOLD, segs=10)
    f += M.cyl(0.22, 0.86, 0.90, 0.55, 0.02, (40, 40, 42), segs=8)
    # limit switch at home (+Z rim)
    f += M.box(-0.04, 0.04, 0.48, 0.56, 0.58, 0.66, (40, 40, 42))
    f += M.box(-0.01, 0.01, 0.54, 0.57, 0.66, 0.74, (200, 200, 200))  # lever
    # inlet funnel (fixed drop)
    f += M.box(-0.16, 0.16, 0.88, 0.92, 0.28, 0.50, (50, 50, 54))
    f += M.box(-0.12, 0.12, 0.70, 0.88, 0.34, 0.46, (60, 60, 64), skip=("top", "bottom"))
    f += hcsr04(0.0, 0.92, 0.40)
    f += ov2640(-0.16, 0.90, 0.32)
    return f


def carousel(angle_deg, fills):
    """Plate + 4 colored bins. angle_deg = commanded carousel (0 = BIO at drop)."""
    f = []
    f += M.cyl(0, 0.28, 0.34, 0, 0.62, (70, 74, 78), segs=28)
    f += M.cyl(0, 0.34, 0.46, 0, 0.10, (50, 52, 54), segs=12)
    f += M.cyl(0, 0.22, 0.28, 0, 0.08, SILVER, segs=10)
    rad = math.radians(angle_deg)
    for b in BINS:
        a = math.radians(b["deg"] - angle_deg)
        x, z = R_BIN * math.sin(a), R_BIN * math.cos(a)
        w = 0.15
        f += M.box(x - w, x + w, 0.34, 0.62, z - w, z + w, tuple(max(20, c - 40) for c in b["hue"]))
        # inner color
        f += M.box(x - w + 0.02, x + w - 0.02, 0.36, 0.60, z - w + 0.02, z + w - 0.02,
                   b["hue"], skip=("top",))
        h = fills.get(b["key"], 0)
        if h > 0.02:
            f += M.box(x - 0.11, x + 0.11, 0.36, 0.36 + 0.20 * h, z - 0.11, z + 0.11, b["hue"], emit=True)
    return f


def ping_cone(on):
    if not on:
        return []
    return M.cyl(0.0, 0.92, 1.05, 0.40, 0.04, (80, 180, 255), segs=10, top=False, bot=False, emit=True)


# ----- timeline -----
T_POSTER = 8.0
T_PARTS = 9.0
T_HOME = 6.0
PER = 11.0
T0 = T_POSTER + T_PARTS + T_HOME  # 23
T_END = 5.0
DUR = T0 + PER * len(CYCLES) + T_END


def state(t):
    carousel = 0.0
    item = None
    step = -1
    title, sub = "BIN-GENIE", ""
    fills = {b["key"]: 0.0 for b in BINS}
    ping = False
    flash = False
    limit = False
    cam = M.Cam(az=0.55, el=0.55, dist=6.8, scale=300, look=(0.35, 0.40, 0.05), origin=(720, 400))
    hud = None

    if t < T_POSTER:
        return dict(mode="poster", t=t, carousel=0, item=None, step=-1,
                    title="", sub="", fills=fills, ping=False, flash=False,
                    limit=False, cam=cam, hud=None)

    if t < T_POSTER + T_PARTS:
        u = (t - T_POSTER) / T_PARTS
        cam = M.Cam(az=0.3 + 1.2 * u, el=0.45 + 0.25 * math.sin(u * math.pi),
                    dist=6.5, scale=310, look=(0.4, 0.35, 0.0), origin=(720, 400))
        title = "C  Components on the plant"
        sub = "STM32H743  ·  OV2640  ·  HC-SR04  ·  moisture  ·  LJ12A3  ·  NEMA17  ·  DRV8825  ·  limit  ·  12V SMPS  ·  LM2596"
        return dict(mode="3d", t=t, carousel=0, item=None, step=-1,
                    title=title, sub=sub, fills=fills, ping=True, flash=False,
                    limit=False, cam=cam, hud=None)

    if t < T0:
        u = (t - T_POSTER - T_PARTS) / T_HOME
        cam = M.Cam(az=0.4, el=0.7, dist=6.6, scale=320, look=(0.15, 0.4, 0.1), origin=(700, 400))
        # homing: start at 200°, spin to 0
        carousel = M.lerp(200, 0, M.ease(u))
        limit = u > 0.85
        step = 8 if u > 0.5 else -1
        title = "Power ON  →  STM32 init  →  NEMA17 HOMING"
        sub = "DRV8825 steps the motor until the limit switch at 0° (BIO) closes."
        return dict(mode="3d", t=t, carousel=carousel, item=None, step=step,
                    title=title, sub=sub, fills=fills, ping=False, flash=False,
                    limit=limit, cam=cam, hud=None)

    if t < T0 + PER * len(CYCLES):
        u = t - T0
        i = min(len(CYCLES) - 1, int(u / PER))
        local = u - i * PER
        cyc = CYCLES[i]
        # fills from completed cycles
        for j, cj in enumerate(CYCLES):
            if u > j * PER + 8.0:
                fills[next(b["key"] for b in BINS if b["deg"] == cj["target"])] += 0.35
        tgt = cyc["target"]
        cam = M.Cam(az=0.35 + 0.15 * math.sin(local), el=0.85, dist=6.7, scale=300,
                    look=(0.1, 0.45, 0.15), origin=(700, 400))
        hud = cyc
        # 0-1.4 detect
        if local < 1.4:
            step, ping = 0, True
            k = M.ease(local / 1.4)
            item = dict(kind=cyc["kind"], pos=(0.0, M.lerp(1.25, 0.95, k), 0.42), sc=1.0)
            carousel = 0.0
            title = f"1  HC-SR04  —  object at inlet  ({cyc['name']})"
            sub = "Echo received. STM32 wakes the camera."
        elif local < 2.4:
            step, flash = 1, (local % 0.3) < 0.12
            item = dict(kind=cyc["kind"], pos=(0.0, 0.95, 0.42), sc=1.0)
            title = "2  OV2640 capture"
            sub = "STM32H743 triggers the module. Frame goes to TinyML."
        elif local < 3.5:
            step = 2
            item = dict(kind=cyc["kind"], pos=(0.0, 0.95, 0.42), sc=1.0)
            title = f"3  TinyML on STM32   {cyc['vis']}   conf {cyc['conf']:.2f}"
            sub = "Quantized CNN. Classes: Organic / Dry / E-waste / Others."
        elif local < 4.4:
            step = 3
            item = dict(kind=cyc["kind"], pos=(0.0, 0.95, 0.42), sc=1.0)
            title = f"4  Sensors   moisture {cyc['moist']:.0%}   inductive {'METAL' if cyc['metal'] else 'no'}"
            sub = "Moisture wet/dry + LJ12A3 metal. Confirm or veto the CNN."
        elif local < 5.1:
            step = 4
            item = dict(kind=cyc["kind"], pos=(0.0, 0.95, 0.42), sc=1.0)
            b = next(b for b in BINS if b["deg"] == tgt)
            extra = "  ·  LOW CONFIDENCE → residual (step 11)" if cyc["conf"] < 0.5 else ""
            title = f"5  Final decision  {b['short']}{extra}"
            sub = "STM32 fuses CNN + sensors. One of 0° / 90° / 180° / 270°."
        elif local < 7.3:
            step = 5
            k = M.ease((local - 5.1) / 2.2)
            carousel = M.lerp(0, tgt if tgt != 0 else 360, k) % 360 if tgt != 0 else 0.0
            if tgt == 0:
                carousel = 0.0
            else:
                carousel = tgt * k
            item = dict(kind=cyc["kind"], pos=(0.0, 0.95, 0.42), sc=1.0)
            title = f"6  DRV8825 → NEMA17    carousel {carousel:5.0f}°  →  {tgt}°"
            sub = "Step + Dir. Carousel index. Drop chute stays fixed; the bay comes to the opening."
        elif local < 8.5:
            step = 6
            carousel = tgt
            k = M.ease((local - 7.3) / 1.2)
            item = dict(kind=cyc["kind"], pos=(0.0, M.lerp(0.95, 0.42, k), M.lerp(0.42, R_BIN, k)), sc=M.lerp(1.0, 0.55, k))
            title = f"7  Drop into {next(b['title'] for b in BINS if b['deg']==tgt)}"
            sub = "Waste falls through the opening into the selected compartment."
        elif local < 10.2:
            step = 7
            k = M.ease((local - 8.5) / 1.7)
            carousel = M.lerp(tgt, 0 if tgt != 0 else 0, k)
            if tgt == 0:
                carousel = 0
            limit = k > 0.9
            bx = R_BIN * math.sin(math.radians(tgt - carousel))
            bz = R_BIN * math.cos(math.radians(tgt - carousel))
            item = dict(kind=cyc["kind"], pos=(bx, 0.42, bz), sc=0.5)
            title = "8  Return HOME  —  limit switch at 0°"
            sub = "NEMA17 reverses until the home lever closes. Ready."
        else:
            step = 8
            carousel = 0
            limit = True
            title = "9  Wait for next object"
            sub = "HC-SR04 listening. Cycle repeats."
        return dict(mode="3d", t=t, carousel=carousel, item=item, step=step,
                    title=title, sub=sub, fills=fills, ping=ping, flash=flash,
                    limit=limit, cam=cam, hud=hud)

    # end
    cam = M.Cam(az=0.6 + 0.4 * ((t - (T0 + PER * 4)) / T_END), el=0.5, dist=7.0, scale=280,
                look=(0.3, 0.4, 0), origin=(700, 400))
    for cj in CYCLES:
        fills[next(b["key"] for b in BINS if b["deg"] == cj["target"])] += 0.35
    return dict(mode="3d", t=t, carousel=0, item=None, step=8,
                title="Ready for next object  —  continuous 4-bin segregation",
                sub="No Raspberry Pi. STM32 + TinyML + NEMA17. Home every cycle.",
                fills=fills, ping=True, flash=False, limit=True, cam=cam, hud=None)


def frame(t):
    st = state(t)
    if st["mode"] == "poster":
        img = kenburns(CAD / "process_flow.png", st["t"], T_POSTER, 1.0, 1.08)
        d = ImageDraw.Draw(img)
        bar(d, "A / B / C / D  —  this is the spec the 3D demo follows",
            "STM32H743  ·  4-compartment carousel  ·  0° organic  90° dry  180° e-waste  270° residual",
            t, -1)
        return img

    faces = []
    faces += electronics()
    faces += carousel(st["carousel"], st["fills"])
    faces += nema17(0.0, 0.00, 0.0, math.radians(st["carousel"]) * 4)
    if st["ping"]:
        faces += ping_cone(True)
    img = M.bg()
    M.draw(img, faces, st["cam"])
    if st["item"]:
        p = st["cam"].project(np.array([st["item"]["pos"]], np.float32))[0]
        paste(img, st["item"]["kind"], (float(p[0]), float(p[1])), st["item"]["sc"])
    d = ImageDraw.Draw(img)
    bar(d, st["title"], st["sub"], t, st["step"])
    # component tags
    tags = [
        ((0.90, 0.10, -0.12), "STM32H743", GREEN),
        ((1.14, 0.08, -0.10), "DRV8825", (180, 140, 220)),
        ((0.90, 0.10, 0.20), "LM2596", (100, 160, 255)),
        ((1.15, 0.14, 0.22), "12V SMPS", SILVER),
        ((0.0, 0.14, 0.0), "NEMA17", WHITE),
        ((0.0, 0.98, 0.40), "HC-SR04", (100, 180, 255)),
        ((-0.16, 0.96, 0.32), "OV2640", GREEN),
        ((-0.15, 0.82, 0.55), "MOISTURE", YELLOW),
        ((0.22, 0.88, 0.55), "LJ12A3", GOLD),
        ((0.0, 0.58, 0.70), "LIMIT  HOME" + ("  CLOSED" if st["limit"] else ""), RED if st["limit"] else WHITE),
    ]
    for pos, lab, col in tags:
        q = st["cam"].project(np.array([pos], np.float32))[0]
        if 40 < q[0] < 1240 and 50 < q[1] < 660:
            d.text((float(q[0]), float(q[1])), lab, font=F_T, fill=col, anchor="mm")
    # angle HUD
    d.rounded_rectangle((980, 56, 1260, 200), 8, fill=(16, 22, 32))
    d.text((996, 76), "CAROUSEL", font=F_T, fill=(140, 150, 160), anchor="lt")
    d.text((996, 102), f"{st['carousel']:6.1f}°", font=F_H, fill=GREEN, anchor="lt")
    d.text((996, 130), "0° BIO   90° DRY", font=F_T, fill=WHITE, anchor="lt")
    d.text((996, 148), "180° EW  270° RES", font=F_T, fill=WHITE, anchor="lt")
    d.text((996, 174), "HOME 0°  " + ("LIMIT HIT" if st["limit"] else "open"), font=F_T,
           fill=RED if st["limit"] else (140, 150, 160), anchor="lt")
    if st["hud"]:
        h = st["hud"]
        d.rounded_rectangle((980, 210, 1260, 340), 8, fill=(16, 22, 32))
        d.text((996, 228), "TinyML + SENSORS", font=F_T, fill=(140, 150, 160), anchor="lt")
        d.text((996, 252), h["vis"], font=F_H2, fill=GREEN if h["conf"] > 0.5 else RED, anchor="lt")
        d.text((996, 278), f"conf {h['conf']:.2f}", font=F_M, fill=WHITE, anchor="lt")
        d.text((996, 298), f"moist {h['moist']:.0%}   metal {'YES' if h['metal'] else 'no'}", font=F_T, fill=WHITE, anchor="lt")
        d.text((996, 318), f"→  {h['target']}°", font=F_M, fill=YELLOW, anchor="lt")
    if st["flash"]:
        d.rectangle((0, 44, W, H - 54), fill=(255, 255, 255, 40))
    return img


def encode(path, t0, t1):
    proc = subprocess.Popen([
        FF, "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "17", "-preset", "fast", "-movflags", "+faststart", str(path),
    ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    n, t, dt = 0, t0, 1.0 / FPS
    while t < t1 - 1e-6:
        proc.stdin.write(cv2.cvtColor(np.array(frame(t)), cv2.COLOR_RGB2BGR).tobytes())
        n += 1
        t += dt
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="ignore")
    if proc.wait():
        raise SystemExit(err[-2000:])
    print(f"  {path.name:28} {n/FPS:5.1f}s  {path.stat().st_size/1e6:.1f}MB")


def main():
    load_tok()
    print("DUR", DUR, "T0", T0)
    frame(2.0).save("/tmp/flow_poster.png")
    frame(12.0).save("/tmp/flow_parts.png")
    frame(T0 + 6.0).save("/tmp/flow_spin.png")
    print("previews")
    cuts = [
        ("f00_poster.mp4", 0, T_POSTER),
        ("f01_parts.mp4", T_POSTER, T_POSTER + T_PARTS),
        ("f02_home.mp4", T_POSTER + T_PARTS, T0),
        ("f03_cycles.mp4", T0, T0 + PER * len(CYCLES)),
        ("f04_end.mp4", T0 + PER * len(CYCLES), DUR),
    ]
    files = []
    for name, a, b in cuts:
        p = PARTS / name
        encode(p, a, b)
        files.append(p)
    lst = PARTS / "concat_flow.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in files))
    full = ROOT / "BIN-GENIE_process_demo.mp4"
    subprocess.check_call([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(full)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("FULL", full, f"{full.stat().st_size/1e6:.1f}MB")


if __name__ == "__main__":
    main()
