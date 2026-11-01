#!/usr/bin/env python3
"""Render a silent, captioned BIN-GENIE plant simulation (MP4)."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import imageio_ffmpeg

ROOT = Path("/home/user")
SAMPLES = ROOT / "static" / "samples"
OUT = ROOT / "static" / "video" / "bingenie_simulation.mp4"
OUT.parent.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1280, 720, 30
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

# RGB
BG = (8, 17, 13)
PANEL = (16, 28, 22)
LINE = (30, 58, 44)
LIME = (198, 242, 90)
LIME_DIM = (143, 184, 58)
TEAL = (62, 224, 197)
COPPER = (224, 138, 74)
PAPER = (231, 215, 167)
GLASS = (126, 203, 255)
INK = (231, 243, 234)
MUTED = (127, 154, 136)
ROSE = (255, 107, 93)

BAYS = {
    "plastic_metal": {"id": "PM-01", "title": "Plastic / Metal", "hue": LIME, "deg": 0},
    "paper": {"id": "PA-02", "title": "Paper", "hue": PAPER, "deg": 90},
    "glass": {"id": "GL-03", "title": "Glass", "hue": GLASS, "deg": 180},
    "residual": {"id": "RS-04", "title": "Residual", "hue": COPPER, "deg": 270},
}

CX, CY, R_BAY, R_DISC = 390, 372, 188, 78


def font(path, size):
    return ImageFont.truetype(path, size)


F_K = font(FONTM, 13)
F_H1 = font(FONTB, 54)
F_H2 = font(FONTB, 22)
F_H3 = font(FONTB, 16)
F_B = font(FONT, 14)
F_S = font(FONT, 12)
F_M = font(FONTM, 13)
F_M2 = font(FONTM, 12)
F_CAP = font(FONT, 18)
F_TINY = font(FONTM, 11)


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_angle(a, b, t):
    d = (b - a + 180) % 360 - 180
    return (a + d * t) % 360


def bay_xy(deg, r=R_BAY):
    rad = math.radians(deg)
    return CX + math.sin(rad) * r, CY - math.cos(rad) * r


def load_thumb(path, size=220):
    im = Image.open(path).convert("RGB")
    im.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), (12, 20, 16))
    x = (size - im.width) // 2
    y = (size - im.height) // 2
    canvas.paste(im, (x, y))
    return canvas


THUMBS = {
    "plastic_bottle": load_thumb(SAMPLES / "plastic_bottle.jpg"),
    "newspaper": load_thumb(SAMPLES / "newspaper.jpg"),
    "glass_bottle": load_thumb(SAMPLES / "glass_bottle.jpg"),
    "soda_can": load_thumb(SAMPLES / "soda_can.jpg"),
    "banana_peel": load_thumb(SAMPLES / "banana_peel.jpg"),
    "cardboard": load_thumb(SAMPLES / "cardboard.jpg"),
}


SORTS = [
    {
        "id": "plastic_bottle",
        "name": "PET water bottle",
        "vision": "plastic",
        "conf": 0.97,
        "ir": 1,
        "moist": 0.06,
        "metal": 0,
        "bin": "plastic_metal",
        "veto": False,
        "caption": "PET bottle on the tray. Vision says plastic.",
        "caption2": "Sensors agree. Disc 0° — commit PM-01.",
    },
    {
        "id": "newspaper",
        "name": "Newsprint",
        "vision": "paper",
        "conf": 0.96,
        "ir": 1,
        "moist": 0.08,
        "metal": 0,
        "bin": "paper",
        "veto": False,
        "caption": "Dry fibre. Vision says paper.",
        "caption2": "Moisture 8% — under the 45% veto. PA-02.",
    },
    {
        "id": "glass_bottle",
        "name": "Green glass bottle",
        "vision": "glass",
        "conf": 0.94,
        "ir": 1,
        "moist": 0.05,
        "metal": 0,
        "bin": "glass",
        "veto": False,
        "caption": "Container glass. Cullet stream.",
        "caption2": "No metal, no moisture veto. GL-03.",
    },
    {
        "id": "soda_can",
        "name": "Aluminium can",
        "vision": "metal",
        "conf": 0.95,
        "ir": 1,
        "moist": 0.05,
        "metal": 1,
        "bin": "plastic_metal",
        "veto": False,
        "caption": "Vision says metal. Inductive coil HIGH.",
        "caption2": "Coil confirms non-ferrous can. PM-01.",
    },
    {
        "id": "banana_peel",
        "name": "Banana peel",
        "vision": "organic",
        "conf": 0.93,
        "ir": 1,
        "moist": 0.74,
        "metal": 0,
        "bin": "residual",
        "veto": False,
        "caption": "Wet organic. Moisture 74%.",
        "caption2": "Never enters dry recycling. RS-04.",
    },
    {
        "id": "newspaper",
        "name": "Newsprint — WET",
        "vision": "paper",
        "conf": 0.91,
        "ir": 1,
        "moist": 0.80,
        "metal": 0,
        "bin": "residual",
        "veto": True,
        "caption": "Camera still says paper. Moisture forced to 80%.",
        "caption2": "SENSOR VETO — wet fibre contaminates PA-02. Divert RS-04.",
    },
]


def rr(draw, box, r, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def text(draw, xy, s, f, fill=INK, anchor="lt"):
    draw.text(xy, s, font=f, fill=fill, anchor=anchor)


def draw_header(draw, t_global):
    rr(draw, (0, 0, W, 56), 0, fill=(10, 20, 16))
    draw.line((0, 56, W, 56), fill=LINE, width=1)
    text(draw, (24, 28), "BIN-GENIE", F_H3, LIME, "lm")
    text(draw, (150, 28), "PLANT SIMULATION", F_M, MUTED, "lm")
    blink = 0.5 + 0.5 * math.sin(t_global * 4)
    c = tuple(int(LIME[i] * blink + MUTED[i] * (1 - blink)) for i in range(3))
    draw.ellipse((W - 268, 22, W - 256, 34), fill=c)
    text(draw, (W - 248, 28), "SIMULATED HARDWARE", F_TINY, MUTED, "lm")
    text(draw, (W - 24, 28), "NO PHYSICAL BIN", F_TINY, LIME_DIM, "rm")


def draw_caption(draw, line1, line2=""):
    rr(draw, (0, H - 64, W, H), 0, fill=(10, 20, 16))
    draw.line((0, H - 64, W, H - 64), fill=LINE, width=1)
    text(draw, (28, H - 40), line1, F_CAP, INK, "lm")
    if line2:
        text(draw, (28, H - 18), line2, F_S, MUTED, "lm")


def draw_plant(draw, img, disc_deg, flap, fills, hot=None, item=None, item_xy=None):
    # floor
    rr(draw, (18, 72, 762, H - 80), 18, fill=(11, 22, 17), outline=LINE, width=1)
    # ring
    bbox = (CX - 210, CY - 210, CX + 210, CY + 210)
    draw.ellipse(bbox, fill=(9, 18, 14), outline=LINE, width=2)
    inner = (CX - 198, CY - 198, CX + 198, CY + 198)
    draw.ellipse(inner, outline=(22, 48, 36), width=1)

    for key, b in BAYS.items():
        x, y = bay_xy(b["deg"])
        w, h = 86, 52
        box = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
        outline = b["hue"] if hot == key else LINE
        fill = (18, 32, 24) if hot == key else (12, 22, 17)
        rr(draw, box, 8, fill=fill, outline=outline, width=2)
        text(draw, (x, y - 8), b["id"], F_TINY, b["hue"], "mm")
        text(draw, (x, y + 8), b["title"].split("/")[0].strip(), F_S, INK, "mm")
        # fill pip
        fx1, fy1 = x - 28, y + 18
        fx2, fy2 = x + 28, y + 22
        draw.rectangle((fx1, fy1, fx2, fy2), fill=(22, 40, 32))
        fw = 56 * max(0, min(1, fills.get(key, 0.08)))
        draw.rectangle((fx1, fy1, fx1 + fw, fy2), fill=b["hue"])

    # disc
    dd = math.radians(disc_deg)
    disc_box = (CX - R_DISC, CY - R_DISC, CX + R_DISC, CY + R_DISC)
    draw.ellipse(disc_box, fill=(14, 26, 20), outline=LIME, width=2)
    draw.ellipse((CX - 10, CY - 10, CX + 10, CY + 10), fill=LIME)
    px = CX + math.sin(dd) * 62
    py = CY - math.cos(dd) * 62
    draw.line((CX, CY, px, py), fill=LIME, width=4)
    # flap
    if flap:
        fx = CX + math.sin(dd) * 86
        fy = CY - math.cos(dd) * 86
        draw.line((px, py, fx, fy), fill=TEAL, width=5)
    text(draw, (CX, CY + 28), "DISC", F_TINY, MUTED, "mm")

    if item is not None and item_xy is not None:
        thumb = THUMBS[item].resize((54, 54), Image.Resampling.LANCZOS)
        mask = Image.new("L", (54, 54), 0)
        ImageDraw.Draw(mask).ellipse((2, 2, 52, 52), fill=255)
        ix, iy = int(item_xy[0] - 27), int(item_xy[1] - 27)
        img.paste(thumb, (ix, iy), mask)


def draw_hud(draw, img, sort, phase, local_t, sensors_t, conf_t):
    x0, y0, x1, y1 = 780, 72, 1262, H - 80
    rr(draw, (x0, y0, x1, y1), 16, fill=PANEL, outline=LINE, width=1)
    text(draw, (x0 + 18, y0 + 18), "TRAY  /  FUSION", F_TINY, MUTED, "lt")

    # photo
    photo = THUMBS[sort["id"]].resize((200, 200), Image.Resampling.LANCZOS)
    px, py = x0 + 22, y0 + 44
    img.paste(photo, (px, py))
    draw.rectangle((px - 1, py - 1, px + 200, py + 200), outline=LINE)
    if phase in ("scan", "sense", "fuse"):
        scan_y = py + int(200 * ((local_t * 1.6) % 1.0))
        draw.line((px, scan_y, px + 200, scan_y), fill=LIME, width=2)

    # vision
    vx = x0 + 236
    text(draw, (vx, y0 + 50), "VISION", F_TINY, MUTED, "lt")
    vis = sort["vision"] if phase != "idle" else "—"
    text(draw, (vx, y0 + 74), vis.upper(), F_H2, LIME if vis != "—" else MUTED, "lt")
    if phase != "idle":
        bar_w = int(200 * conf_t * sort["conf"])
        draw.rectangle((vx, y0 + 104, vx + 200, y0 + 110), fill=(22, 40, 32))
        draw.rectangle((vx, y0 + 104, vx + bar_w, y0 + 110), fill=LIME)
        text(draw, (vx, y0 + 118), f"{sort['conf'] * conf_t:.2f}  labeled-sample", F_TINY, MUTED, "lt")

    # sensors
    sy = y0 + 260
    text(draw, (x0 + 22, sy), "SENSORS", F_TINY, MUTED, "lt")
    ir_on = sort["ir"] if sensors_t > 0.2 else 0
    moist = sort["moist"] * ease(max(0, (sensors_t - 0.25) / 0.5)) if sensors_t else 0
    metal = sort["metal"] if sensors_t > 0.55 else 0

    def sensor_row(y, lab, val, hot=False):
        rr(draw, (x0 + 22, y, x1 - 22, y + 36), 8, fill=(11, 20, 16), outline=LIME if hot else LINE, width=1)
        text(draw, (x0 + 36, y + 18), lab, F_TINY, MUTED, "lm")
        text(draw, (x1 - 36, y + 18), val, F_M, LIME if hot else INK, "rm")

    sensor_row(sy + 22, "IR TRAY", "PRESENT" if ir_on else "CLEAR", hot=bool(ir_on))
    sensor_row(sy + 64, "MOISTURE", f"{moist:.0%}", hot=moist >= 0.45)
    sensor_row(sy + 106, "INDUCTIVE", "METAL HIT" if metal else "NO METAL", hot=bool(metal))

    # fusion
    fy = sy + 156
    text(draw, (x0 + 22, fy), "FUSED BAY", F_TINY, MUTED, "lt")
    if phase in ("fuse", "actuate", "drop", "hold"):
        b = BAYS[sort["bin"]]
        col = COPPER if sort["veto"] else b["hue"]
        label = f"{b['id']}  {b['title']}"
        if sort["veto"]:
            label = "VETO  →  " + label
        text(draw, (x0 + 22, fy + 28), label, F_H3, col, "lt")
    else:
        text(draw, (x0 + 22, fy + 28), "awaiting vote", F_B, MUTED, "lt")


def make_base():
    return Image.new("RGB", (W, H), BG)


def render_title(t, dur):
    img = make_base()
    d = ImageDraw.Draw(img)
    a = ease(min(1, t / 0.8))
    def fade(c, a=a):
        return tuple(int(c[i] * a + BG[i] * (1 - a)) for i in range(3))
    text(d, (W / 2, 250), "BIN-GENIE", F_H1, fade(LIME), "mm")
    text(d, (W / 2, 318), "PLANT SIMULATION", F_H2, fade(INK), "mm")
    text(d, (W / 2, 360), "Vision  ·  IR  ·  Moisture  ·  Metal   →   4-bay disc sorter", F_B, fade(MUTED), "mm")
    text(d, (W / 2, 430), "Hardware is simulated. Protocol is the real ESP32 contract.", F_S, fade(LIME_DIM), "mm")
    text(d, (W / 2, 458), "No physical bin required for this evidence.", F_S, fade(MUTED), "mm")
    draw_caption(d, "BIN-GENIE  ·  simulation video for evaluation", "Same chain the live dashboard runs.")
    return img


def render_overview(t, fills):
    img = make_base()
    d = ImageDraw.Draw(img)
    draw_header(d, t)
    draw_plant(d, img, disc_deg=0, flap=False, fills=fills, hot=None)
    # right copy
    rr(d, (780, 72, 1262, H - 80), 16, fill=PANEL, outline=LINE, width=1)
    lines = [
        ("PM-01", "Plastic / metal", LIME),
        ("PA-02", "Paper  (dry fibre only)", PAPER),
        ("GL-03", "Glass containers", GLASS),
        ("RS-04", "Residual / organic", COPPER),
    ]
    text(d, (804, 100), "FOUR BAYS  ·  ONE DISC", F_H3, INK, "lt")
    y = 150
    for i, (a, b, c) in enumerate(lines):
        text(d, (804, y), a, F_M, c, "lt")
        text(d, (880, y), b, F_B, INK, "lt")
        y += 36
    text(d, (804, 340), "Vision proposes a class.", F_B, MUTED, "lt")
    text(d, (804, 368), "Sensors may veto it.", F_B, MUTED, "lt")
    text(d, (804, 396), "Actuator commits SORT <bay>.", F_B, MUTED, "lt")
    draw_caption(d, "Rotating disc at 0° / 90° / 180° / 270°.", "Flap opens 18° after the disc settles.")
    return img


def render_sort(sort, local, disc_from, disc_to, fills, fills_after, t_global):
    """local 0..1 over ~8s scene."""
    img = make_base()
    d = ImageDraw.Draw(img)
    draw_header(d, t_global)

    # phases
    # 0-0.10 idle/approach
    # 0.10-0.28 scan
    # 0.28-0.48 sense
    # 0.48-0.58 fuse
    # 0.58-0.78 actuate (disc)
    # 0.78-0.92 drop
    # 0.92-1 hold
    if local < 0.10:
        phase = "idle"
    elif local < 0.28:
        phase = "scan"
    elif local < 0.48:
        phase = "sense"
    elif local < 0.58:
        phase = "fuse"
    elif local < 0.78:
        phase = "actuate"
    elif local < 0.92:
        phase = "drop"
    else:
        phase = "hold"

    conf_t = ease((local - 0.10) / 0.18) if local >= 0.10 else 0
    sensors_t = ease((local - 0.28) / 0.18) if local >= 0.28 else 0

    if local < 0.58:
        disc = disc_from
        flap = False
        fills_now = fills
        hot = None
    elif local < 0.78:
        disc = lerp_angle(disc_from, disc_to, ease((local - 0.58) / 0.20))
        flap = local > 0.72
        fills_now = fills
        hot = sort["bin"] if local > 0.70 else None
    else:
        disc = disc_to
        flap = local < 0.90
        hot = sort["bin"]
        k = ease((local - 0.78) / 0.14)
        fills_now = {kk: lerp(fills[kk], fills_after[kk], k) for kk in fills}

    # item position
    tray = (CX, CY)
    bx, by = bay_xy(disc_to, r=R_BAY - 10)
    if local < 0.08:
        item_xy = (CX, CY + 40 - 40 * ease(local / 0.08))
        show_item = True
    elif local < 0.78:
        item_xy = tray
        show_item = True
    elif local < 0.92:
        k = ease((local - 0.78) / 0.14)
        item_xy = (lerp(tray[0], bx, k), lerp(tray[1], by, k))
        show_item = True
    else:
        item_xy = (bx, by)
        show_item = local < 0.96

    draw_plant(
        d, img, disc, flap, fills_now, hot=hot,
        item=sort["id"] if show_item else None,
        item_xy=item_xy if show_item else None,
    )
    draw_hud(d, img, sort, phase, local, sensors_t, conf_t)

    cap1, cap2 = sort["caption"], ""
    if phase in ("sense",):
        cap2 = f"IR {'present' if sort['ir'] else 'clear'}  ·  moisture {sort['moist']:.0%}  ·  metal {'yes' if sort['metal'] else 'no'}"
    elif phase in ("fuse", "actuate", "drop", "hold"):
        cap1 = sort["caption2"] if sort["veto"] else sort["caption"]
        cap2 = sort["caption2"]
        if sort["veto"] and phase != "sense":
            cap1 = sort["caption"]
            cap2 = sort["caption2"]
    draw_caption(d, cap1, cap2)
    return img


def render_end(t, fills, counts):
    img = make_base()
    d = ImageDraw.Draw(img)
    draw_header(d, t + 40)
    text(d, (W / 2, 150), "SIMULATION COMPLETE", F_H2, LIME, "mm")
    text(d, (W / 2, 190), "Six items through vision → sensors → fusion → disc.", F_B, MUTED, "mm")
    x = 180
    for key, b in BAYS.items():
        rr(d, (x, 250, x + 220, 430), 14, fill=PANEL, outline=b["hue"], width=2)
        text(d, (x + 110, 290), b["id"], F_H2, b["hue"], "mm")
        text(d, (x + 110, 330), b["title"], F_S, INK, "mm")
        text(d, (x + 110, 372), f"{counts[key]} item(s)", F_H3, INK, "mm")
        text(d, (x + 110, 400), f"fill {fills[key]*100:.0f}%", F_TINY, MUTED, "mm")
        x += 240
    text(d, (W / 2, 490), "Proof beat: wet newsprint was vetoed out of PA-02 into RS-04.", F_B, COPPER, "mm")
    text(d, (W / 2, 530), "Dashboard + ESP32 firmware speak this same SORT protocol.", F_S, MUTED, "mm")
    draw_caption(d, "Use this clip as simulation evidence.", "Live dashboard can still be screen-recorded for the viva.")
    return img


def to_bgr(img: Image.Image) -> bytes:
    arr = np.array(img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR).tobytes()


def main():
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-",
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "19", "-preset", "fast", "-movflags", "+faststart",
        str(OUT),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    fills = {k: 0.08 for k in BAYS}
    counts = {k: 0 for k in BAYS}
    disc = 0.0
    t_global = 0.0
    n = 0

    def push(img, frames):
        nonlocal n, t_global
        raw = to_bgr(img)
        for _ in range(frames):
            proc.stdin.write(raw)
            n += 1
        t_global += frames / FPS

    # title 3.6s
    title_frames = int(3.6 * FPS)
    for i in range(title_frames):
        push(render_title(i / FPS, 3.6), 1)

    # overview 3.0s
    ov = int(3.0 * FPS)
    for i in range(ov):
        push(render_overview(i / FPS, fills), 1)

    # sorts
    for sort in SORTS:
        dur = 8.0 if not sort["veto"] else 9.0
        frames = int(dur * FPS)
        disc_to = BAYS[sort["bin"]]["deg"]
        fills_after = dict(fills)
        fills_after[sort["bin"]] = min(1.0, fills_after[sort["bin"]] + 0.11)
        for i in range(frames):
            local = i / (frames - 1)
            img = render_sort(sort, local, disc, disc_to, fills, fills_after, t_global + i / FPS)
            raw = to_bgr(img)
            proc.stdin.write(raw)
            n += 1
        t_global += dur
        disc = disc_to
        fills = fills_after
        counts[sort["bin"]] += 1

    # end 5s
    end_frames = int(5.0 * FPS)
    end_img = render_end(0, fills, counts)
    raw = to_bgr(end_img)
    for _ in range(end_frames):
        proc.stdin.write(raw)
        n += 1

    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="ignore")
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg failed {rc}\n{err[-2000:]}")
    print(f"wrote {OUT}  frames={n}  dur={n/FPS:.1f}s  size={OUT.stat().st_size/1e6:.1f}MB")


if __name__ == "__main__":
    main()
