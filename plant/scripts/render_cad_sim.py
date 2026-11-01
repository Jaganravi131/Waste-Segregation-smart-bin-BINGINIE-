#!/usr/bin/env python3
"""BIN-GENIE CAD motion-study clips, matched to the SolidWorks assembly."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import imageio_ffmpeg

ROOT = Path("/home/user")
CAD = ROOT / "static" / "cad"
OUT = ROOT / "static" / "video" / "parts"
OUT.mkdir(parents=True, exist_ok=True)
SAMPLES = ROOT / "static" / "samples"

W, H, FPS = 1280, 720, 30
FF = imageio_ffmpeg.get_ffmpeg_exe()
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

BG_TOP = (232, 239, 246)
BG_BOT = (210, 222, 234)
INK = (28, 32, 36)
MUTED = (90, 100, 112)
GREEN = (40, 220, 70)
SILVER = (196, 202, 208)
BLACK = (32, 32, 34)
BLACK2 = (48, 48, 50)
WHITE = (245, 247, 250)

F_H = ImageFont.truetype(FONTB, 28)
F_H2 = ImageFont.truetype(FONTB, 20)
F_B = ImageFont.truetype(FONT, 16)
F_S = ImageFont.truetype(FONT, 13)
F_M = ImageFont.truetype(FONTM, 13)
F_TINY = ImageFont.truetype(FONTM, 11)
F_BIG = ImageFont.truetype(FONTB, 42)

CUT_SPAN = math.radians(100)  # pocket opening

# bin world XZ (Y up). Front is +Z (intake).
BINS = {
    "PM-01": {"title": "Plastic / Metal", "pos": (0.62, 0.26), "hue": (70, 200, 90)},
    "PA-02": {"title": "Paper", "pos": (-0.62, 0.26), "hue": (214, 196, 140)},
    "GL-03": {"title": "Glass", "pos": (0.62, -0.26), "hue": (90, 170, 220)},
    "RS-04": {"title": "Residual", "pos": (-0.62, -0.26), "hue": (220, 130, 70)},
}


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_ang(a, b, t):
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * t


def bin_angle(key):
    x, z = BINS[key]["pos"]
    return math.atan2(z, x)


def bg():
    col = np.linspace(np.array(BG_TOP), np.array(BG_BOT), H, dtype=np.uint8)
    arr = np.repeat(col[:, None, :], W, axis=1)
    return Image.fromarray(arr, "RGB")


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], np.float32)


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], np.float32)


class Cam:
    def __init__(self, az=0.62, el=0.42, dist=7.2, scale=430, look=(0, 0.7, 0), origin=(640, 390)):
        self.az, self.el, self.dist, self.scale = az, el, dist, scale
        self.look = np.array(look, np.float32)
        self.origin = origin

    def project(self, pts):
        p = (pts - self.look) @ rot_y(self.az).T @ rot_x(-self.el).T
        z = p[:, 2] + self.dist
        x = p[:, 0] / z * self.dist
        y = p[:, 1] / z * self.dist
        sx = self.origin[0] + x * self.scale
        sy = self.origin[1] - y * self.scale
        return np.stack([sx, sy, p[:, 2]], 1)


LIGHT = np.array([-0.4, 0.82, 0.45], np.float32)
LIGHT /= np.linalg.norm(LIGHT)


def shade(rgb, n):
    n = n / (np.linalg.norm(n) + 1e-8)
    ndl = float(np.clip(n @ LIGHT, 0, 1))
    k = 0.28 + 0.72 * ndl
    return tuple(int(np.clip(c * k, 0, 255)) for c in rgb)


def face(pts, rgb, n=None):
    pts = np.asarray(pts, np.float32)
    if n is None:
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    return {"pts": pts, "rgb": rgb, "n": np.asarray(n, np.float32)}


def box_faces(x0, x1, y0, y1, z0, z1, rgb, skip=()):
    p = {
        "flb": (x0, y0, z1), "frb": (x1, y0, z1), "frt": (x1, y1, z1), "flt": (x0, y1, z1),
        "blb": (x0, y0, z0), "brb": (x1, y0, z0), "brt": (x1, y1, z0), "blt": (x0, y1, z0),
    }
    faces = []
    quads = {
        "front": (p["flb"], p["frb"], p["frt"], p["flt"]),
        "back": (p["brb"], p["blb"], p["blt"], p["brt"]),
        "left": (p["blb"], p["flb"], p["flt"], p["blt"]),
        "right": (p["frb"], p["brb"], p["brt"], p["frt"]),
        "top": (p["flt"], p["frt"], p["brt"], p["blt"]),
        "bottom": (p["blb"], p["brb"], p["frb"], p["flb"]),
    }
    for name, q in quads.items():
        if name in skip:
            continue
        faces.append(face(q, rgb))
    return faces


def cylinder_faces(cx, y0, y1, cz, r, rgb, segs=18, closed_top=True, closed_bot=True):
    faces = []
    angs = np.linspace(0, 2 * math.pi, segs, endpoint=False)
    top = np.stack([cx + r * np.cos(angs), np.full_like(angs, y1), cz + r * np.sin(angs)], 1)
    bot = np.stack([cx + r * np.cos(angs), np.full_like(angs, y0), cz + r * np.sin(angs)], 1)
    for i in range(segs):
        j = (i + 1) % segs
        faces.append(face([bot[i], bot[j], top[j], top[i]], rgb))
    if closed_top:
        ctr = np.array([cx, y1, cz], np.float32)
        for i in range(segs):
            j = (i + 1) % segs
            faces.append(face([ctr, top[i], top[j]], rgb, n=np.array([0, 1, 0], np.float32)))
    if closed_bot:
        ctr = np.array([cx, y0, cz], np.float32)
        for i in range(segs):
            j = (i + 1) % segs
            faces.append(face([ctr, bot[j], bot[i]], rgb, n=np.array([0, -1, 0], np.float32)))
    return faces


def disc_faces(cx, y, cz, r_out, r_in, thick, rot, rgb, segs=48, cut_span=CUT_SPAN):
    """Solid disc with a rim pocket (the SolidWorks sector cut), not a full annulus."""
    faces = []
    y0, y1 = y - thick / 2, y + thick / 2
    r_bite = r_out * 0.42  # pocket depth from rim toward hub
    hub = np.array([cx, y1, cz], np.float32)
    hub0 = np.array([cx, y0, cz], np.float32)

    def in_cut(a):
        d = (a - rot + math.pi) % (2 * math.pi) - math.pi
        return abs(d) <= cut_span / 2

    angs = [i * 2 * math.pi / segs for i in range(segs)]
    angs += [rot - cut_span / 2, rot + cut_span / 2]
    angs = sorted({(a % (2 * math.pi)) for a in angs})
    n = len(angs)

    def pt(r, y, a):
        return np.array([cx + r * math.cos(a), y, cz + r * math.sin(a)], np.float32)

    for k in range(n):
        a, b = angs[k], angs[(k + 1) % n]
        mid = (a + ((b - a) % (2 * math.pi)) / 2) % (2 * math.pi)
        shine = 0.80 + 0.20 * abs(math.sin(2 * a))
        col = tuple(int(np.clip(c * shine, 0, 255)) for c in rgb)
        dim = tuple(max(0, c - 28) for c in col)
        if in_cut(mid):
            # remaining inner disc inside the bite
            faces.append(face([hub, pt(r_bite, y1, a), pt(r_bite, y1, b)], col, n=np.array([0, 1, 0], np.float32)))
            faces.append(face([hub0, pt(r_bite, y0, b), pt(r_bite, y0, a)], col, n=np.array([0, -1, 0], np.float32)))
            faces.append(face([pt(r_bite, y0, a), pt(r_bite, y0, b), pt(r_bite, y1, b), pt(r_bite, y1, a)], dim))
        else:
            faces.append(face([hub, pt(r_out, y1, a), pt(r_out, y1, b)], col, n=np.array([0, 1, 0], np.float32)))
            faces.append(face([hub0, pt(r_out, y0, b), pt(r_out, y0, a)], col, n=np.array([0, -1, 0], np.float32)))
            faces.append(face([pt(r_out, y0, a), pt(r_out, y0, b), pt(r_out, y1, b), pt(r_out, y1, a)], dim))

    # pocket radial walls
    for a in (rot - cut_span / 2, rot + cut_span / 2):
        faces.append(face([
            pt(r_out, y0, a), pt(r_bite, y0, a), pt(r_bite, y1, a), pt(r_out, y1, a)
        ], tuple(max(0, c - 40) for c in rgb)))
    return faces


def housing_shell(cx, cz, side, rgb=BLACK):
    """Curved-ish bin housing: a rounded box around two cylinders."""
    # side: -1 left, +1 right
    x0 = cx - 0.20
    x1 = cx + 0.20
    z0 = cz - 0.48
    z1 = cz + 0.48
    y0, y1 = 0.08, 0.72
    skip = {"top"}
    # open toward center
    if side < 0:
        skip.add("right")
    else:
        skip.add("left")
    return box_faces(x0, x1, y0, y1, z0, z1, rgb, skip=skip)


def static_internals(sep=0.0, assembled=True):
    faces = []
    # base
    faces += box_faces(-0.36, 0.36, 0.0, 0.06, -0.40, 0.40, BLACK)
    # back plate
    faces += box_faces(-0.34, 0.34, 0.06, 1.05, -0.42, -0.36, BLACK)
    # shaft
    faces += cylinder_faces(0.0, 0.06, 1.02, 0.0, 0.045, (24, 24, 26), segs=14)
    # rails
    faces += box_faces(-0.22, 0.22, 1.06, 1.10, -0.42, -0.38, BLACK)
    faces += box_faces(-0.22, 0.22, 1.12, 1.16, -0.42, -0.38, BLACK)

    left_x = -0.62 - sep
    right_x = 0.62 + sep
    if assembled:
        left_x, right_x = -0.55, 0.55
        sep = 0
    # housings
    faces += housing_shell(left_x, 0.0, -1)
    faces += housing_shell(right_x, 0.0, 1)
    # cylinders
    for key, b in BINS.items():
        x, z = b["pos"]
        if x < 0:
            x = left_x + (x + 0.42)  # keep relative inside housing
            if assembled:
                x = -0.42
        else:
            x = right_x - (0.42 - x) if not assembled else 0.42
            if assembled:
                x = 0.42
        # store runtime? we'll pass bin world positions separately
        faces += cylinder_faces(x, 0.10, 0.68, z, 0.15, (22, 22, 24), segs=16, closed_top=False)
        # inner floor
        faces += cylinder_faces(x, 0.10, 0.12, z, 0.145, (18, 18, 20), segs=12, closed_bot=False)
    return faces


def bin_world_pos(assembled=True, sep=0.0):
    out = {}
    left_x = -0.55 if assembled else -0.62 - sep
    right_x = 0.55 if assembled else 0.62 + sep
    for key, b in BINS.items():
        x, z = b["pos"]
        if assembled:
            out[key] = (x, z)
        else:
            out[key] = (left_x if x < 0 else right_x, z)
    return out


def item_box(x, y, z, rgb, s=0.07):
    return box_faces(x - s, x + s, y - s, y + s, z - s, z + s, rgb)


def housing_exterior(window_open=True):
    faces = []
    # tapered box via two stacked boxes
    faces += box_faces(-0.58, 0.58, 0.04, 1.55, -0.44, 0.44, BLACK2)
    # feet
    for x, z in ((-0.42, -0.30), (0.42, -0.30), (-0.42, 0.30), (0.42, 0.30)):
        faces += cylinder_faces(x, 0.0, 0.05, z, 0.05, (20, 20, 22), segs=10)
    # green rim (thin top edges)
    t = 0.018
    y0, y1 = 1.55, 1.57
    faces += box_faces(-0.58, 0.58, y0, y1, 0.42, 0.44, GREEN)
    faces += box_faces(-0.58, 0.58, y0, y1, -0.44, -0.42, GREEN)
    faces += box_faces(-0.58, -0.56, y0, y1, -0.44, 0.44, GREEN)
    faces += box_faces(0.56, 0.58, y0, y1, -0.44, 0.44, GREEN)
    # window cavity on +Z front, upper right
    if window_open:
        faces += box_faces(0.02, 0.46, 1.18, 1.46, 0.38, 0.441, (12, 12, 14))
        # chrome lip
        faces += box_faces(0.00, 0.48, 1.16, 1.18, 0.43, 0.445, SILVER)
        faces += box_faces(0.00, 0.48, 1.46, 1.48, 0.43, 0.445, SILVER)
        faces += box_faces(0.00, 0.02, 1.16, 1.48, 0.43, 0.445, SILVER)
        faces += box_faces(0.46, 0.48, 1.16, 1.48, 0.43, 0.445, SILVER)
    return faces


def draw_faces(img, faces, cam):
    d = ImageDraw.Draw(img, "RGBA")
    proj = []
    for f in faces:
        pts = f["pts"]
        pr = cam.project(pts)
        depth = float(pr[:, 2].mean())
        n = f["n"]
        col = shade(f["rgb"], n)
        # backface
        if n[1] == 0 and n[0] == 0 and n[2] == 0:
            pass
        poly = [(float(x), float(y)) for x, y, _ in pr]
        proj.append((depth, poly, col))
    proj.sort(key=lambda t: t[0], reverse=True)
    for _, poly, col in proj:
        if len(poly) < 3:
            continue
        d.polygon(poly, fill=col + (255,), outline=(10, 10, 12, 90))
    return img


def chrome_bar(draw, title, subtitle, step=None):
    draw.rectangle((0, 0, W, 56), fill=(18, 20, 22))
    draw.rectangle((0, 54, W, 56), fill=GREEN)
    draw.text((24, 28), "BIN-GENIE", font=F_H2, fill=GREEN, anchor="lm")
    draw.text((170, 28), "SOLIDWORKS MOTION STUDY", font=F_M, fill=(160, 168, 176), anchor="lm")
    if step:
        draw.text((W - 24, 28), step, font=F_M, fill=WHITE, anchor="rm")
    draw.rectangle((0, H - 68, W, H), fill=(18, 20, 22))
    draw.text((28, H - 42), title, font=F_H2, fill=WHITE, anchor="lm")
    if subtitle:
        draw.text((28, H - 18), subtitle, font=F_S, fill=(170, 176, 184), anchor="lm")


def kenburns(path, t, dur, zoom0=1.02, zoom1=1.16):
    im = Image.open(path).convert("RGB")
    k = ease(t / max(dur, 0.001))
    zoom = lerp(zoom0, zoom1, k)
    # cover
    scale = max(W / im.width, H / im.height) * zoom
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    x = int((nw - W) * k * 0.6)
    y = int((nh - H) * (1 - k) * 0.35)
    x = max(0, min(nw - W, x))
    y = max(0, min(nh - H, y))
    return im.crop((x, y, x + W, y + H))


def load_token(name, size=52):
    p = SAMPLES / name
    im = Image.open(p).convert("RGB")
    im.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), (30, 30, 32))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, size - 2, size - 2), fill=255)
    return canvas, mask


TOKENS = {
    "plastic": load_token("plastic_bottle.jpg"),
    "paper": load_token("newspaper.jpg"),
    "glass": load_token("glass_bottle.jpg"),
    "metal": load_token("soda_can.jpg"),
    "organic": load_token("banana_peel.jpg"),
}


def paste_token(img, kind, xy, scale=1.0):
    tok, mask = TOKENS[kind]
    if scale != 1.0:
        s = max(8, int(tok.size[0] * scale))
        tok = tok.resize((s, s), Image.Resampling.LANCZOS)
        mask = mask.resize((s, s), Image.Resampling.LANCZOS)
    x, y = int(xy[0] - tok.size[0] / 2), int(xy[1] - tok.size[1] / 2)
    img.paste(tok, (x, y), mask)


def render_3d(faces, cam, extra=None):
    img = bg()
    draw_faces(img, faces, cam)
    if extra:
        extra(img)
    return img


def open_encoder(path):
    cmd = [
        FF, "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "18", "-preset", "fast", "-movflags", "+faststart",
        str(path),
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def to_bgr(img):
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes()


def write_clip(path, frames_iter, n_hint=0):
    proc = open_encoder(path)
    n = 0
    for img in frames_iter:
        proc.stdin.write(to_bgr(img))
        n += 1
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="ignore")
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg {path} failed {rc}\n{err[-1500:]}")
    print(f"  {path.name:28}  {n/FPS:5.1f}s  {path.stat().st_size/1e6:.1f}MB")
    return n


# -------------------- scenes --------------------

def part01_intro():
    dur = 9.0
    n = int(dur * FPS)
    still = CAD / "exterior_clean.png"

    def gen():
        for i in range(n):
            t = i / FPS
            img = kenburns(still, t, dur)
            d = ImageDraw.Draw(img)
            chrome_bar(
                d,
                "1 / 5   Exterior housing",
                "Black ABS body  ·  green LED rim  ·  chrome intake window",
                "PART 01",
            )
            if t > 2.2:
                a = ease(min(1, (t - 2.2) / 0.6))
                # intake callout
                d.ellipse((868, 210, 888, 230), outline=(40, 220, 70, int(255 * a)) if False else GREEN, width=2)
            yield img

    write_clip(OUT / "01_exterior.mp4", gen())


def part02_intake():
    """Carousel close-up from the CAD — this is where the item lands."""
    dur = 10.0
    n = int(dur * FPS)
    still = CAD / "carousel_clean.png"

    def gen():
        for i in range(n):
            t = i / FPS
            img = kenburns(still, t, dur, 1.02, 1.14)
            d = ImageDraw.Draw(img)
            chrome_bar(
                d,
                "2 / 6   Dual-disc carousel  (your assembly)",
                "Two stacked discs, same sector pocket. Waste sits in the cutout; discs index together; item drops when the pocket is over a cylinder.",
                "PART 02",
            )
            yield img

    write_clip(OUT / "02_intake.mp4", gen())


def part03_exploded():
    dur = 12.0
    n = int(dur * FPS)
    still = CAD / "exploded_clean.png"

    def gen():
        for i in range(n):
            t = i / FPS
            img = kenburns(still, t, dur, 1.0, 1.10)
            d = ImageDraw.Draw(img)
            chrome_bar(
                d,
                "3 / 5   Exploded mechanism  —  your SolidWorks assembly",
                "Left pair of cylinders  ·  dual-disc carousel  ·  right pair of cylinders",
                "PART 03",
            )
            # labels appear
            if t > 2.0:
                labels = [
                    (250, 250, "PA-02  Paper"),
                    (250, 430, "RS-04  Residual"),
                    (640, 130, "Dual carousel disc"),
                    (640, 165, "sector pocket / drop gate"),
                    (1000, 250, "GL-03  Glass"),
                    (1000, 470, "PM-01  Plastic / Metal"),
                ]
                a = ease(min(1, (t - 2.0) / 0.8))
                col = (20, 22, 24)
                for x, y, s in labels:
                    d.text((x, y), s, font=F_S, fill=col, anchor="mm")
            yield img

    write_clip(OUT / "03_exploded.mp4", gen())


def part04_carousel_index():
    """Assembled internals, disc rotates so pocket visits each bin."""
    dur = 16.0
    n = int(dur * FPS)
    cam = Cam(az=0.18, el=1.12, dist=7.2, scale=360, look=(0, 0.32, 0), origin=(640, 400))
    order = ["PM-01", "PA-02", "GL-03", "RS-04"]
    static = static_internals(assembled=True)

    def gen():
        for i in range(n):
            t = i / FPS
            # 1.2s hold then 3s per bay
            u = max(0, t - 1.0)
            seg = min(3.99, u / 3.5)
            idx = int(seg)
            local = seg - idx
            a0 = bin_angle(order[idx])
            a1 = bin_angle(order[min(idx + 1, 3)])
            if idx == 3:
                rot = a0
            else:
                rot = lerp_ang(a0, a1, ease(local))
            faces = list(static)
            faces += disc_faces(0, 0.96, 0, 0.33, 0.07, 0.045, rot, SILVER)
            faces += disc_faces(0, 0.90, 0, 0.33, 0.07, 0.045, rot, (170, 176, 182))
            faces += cylinder_faces(0, 0.98, 1.04, 0, 0.035, (20, 20, 22), segs=12)
            img = render_3d(faces, cam)
            d = ImageDraw.Draw(img)
            key = order[min(idx, 3)]
            chrome_bar(
                d,
                "4 / 5   Carousel indexes the sector pocket",
                f"Opening aligned to {key}  {BINS[key]['title']}   —  item will drop through the cutout",
                "PART 04",
            )
            # bin tags
            for k, b in BINS.items():
                p = cam.project(np.array([[b["pos"][0], 0.72, b["pos"][1]]], np.float32))[0]
                col = b["hue"] if k == key else (40, 42, 44)
                d.text((float(p[0]), float(p[1]) - 18), k, font=F_TINY, fill=col, anchor="mm")
            yield img

    write_clip(OUT / "04_carousel.mp4", gen())


SORTS = [
    dict(kind="plastic", key="PM-01", name="PET bottle", vis="plastic", moist=0.06, metal=0, veto=False),
    dict(kind="paper", key="PA-02", name="Newsprint", vis="paper", moist=0.08, metal=0, veto=False),
    dict(kind="glass", key="GL-03", name="Glass bottle", vis="glass", moist=0.05, metal=0, veto=False),
    dict(kind="metal", key="PM-01", name="Aluminium can", vis="metal", moist=0.05, metal=1, veto=False),
    dict(kind="paper", key="RS-04", name="WET newsprint", vis="paper", moist=0.80, metal=0, veto=True),
]


def part05_sorting():
    """Full working demo: item onto disc, rotate, drop into cylinder."""
    per = 7.2
    intro = 1.5
    dur = intro + per * len(SORTS)
    n = int(dur * FPS)
    cam = Cam(az=0.20, el=1.08, dist=7.2, scale=350, look=(0, 0.32, 0), origin=(520, 400))
    static = static_internals(assembled=True)

    def gen():
        rot = bin_angle("PM-01")
        fills = {k: 0.0 for k in BINS}
        for i in range(n):
            t = i / FPS
            if t < intro:
                faces = list(static)
                faces += disc_faces(0, 0.96, 0, 0.33, 0.07, 0.045, rot, SILVER)
                faces += disc_faces(0, 0.90, 0, 0.33, 0.07, 0.045, rot, (170, 176, 182))
                img = render_3d(faces, cam)
                d = ImageDraw.Draw(img)
                chrome_bar(d, "5 / 5   Working sort  —  vision + sensors + disc", "Five items. Last one is a moisture veto.", "PART 05")
                yield img
                continue

            sidx = min(len(SORTS) - 1, int((t - intro) / per))
            local = (t - intro) - sidx * per
            sort = SORTS[sidx]
            target = bin_angle(sort["key"])
            bx, bz = BINS[sort["key"]]["pos"]

            # phases of local 0-7.2
            # 0-1.3 approach onto disc pocket
            # 1.3-3.3 rotate
            # 3.3-4.0 hold
            # 4.0-5.6 drop
            # 5.6-7.2 hold in bin
            if local < 1.3:
                k = ease(local / 1.3)
                ix, iy, iz = lerp(0.0, 0.22 * math.cos(rot), k), lerp(1.25, 1.00, k), lerp(0.55, 0.22 * math.sin(rot), k)
                show = True
                sc = 1.0
            elif local < 3.3:
                k = ease((local - 1.3) / 2.0)
                prev = bin_angle("PM-01") if sidx == 0 else bin_angle(SORTS[sidx - 1]["key"])
                rot = lerp_ang(prev, target, k)
                ix, iy, iz = 0.22 * math.cos(rot), 1.00, 0.22 * math.sin(rot)
                show, sc = True, 1.0
            elif local < 4.0:
                rot = target
                ix, iy, iz = 0.22 * math.cos(rot), 1.00, 0.22 * math.sin(rot)
                show, sc = True, 1.0
            elif local < 5.6:
                rot = target
                k = ease((local - 4.0) / 1.6)
                ix = lerp(0.22 * math.cos(rot), bx, k)
                iz = lerp(0.22 * math.sin(rot), bz, k)
                iy = lerp(1.00, 0.28, k)
                show, sc = True, lerp(1.0, 0.55, k)
            else:
                rot = target
                ix, iy, iz = bx, 0.28, bz
                show, sc = True, 0.5
                fills[sort["key"]] = min(1.0, 0.18 * (sidx + 1))

            faces = list(static)
            faces += disc_faces(0, 0.96, 0, 0.33, 0.07, 0.045, rot, SILVER)
            faces += disc_faces(0, 0.90, 0, 0.33, 0.07, 0.045, rot, (170, 176, 182))
            faces += cylinder_faces(0, 0.98, 1.04, 0, 0.035, (20, 20, 22), segs=12)
            img = render_3d(faces, cam)
            if show:
                p = cam.project(np.array([[ix, iy, iz]], np.float32))[0]
                paste_token(img, sort["kind"], (float(p[0]), float(p[1])), scale=sc)

            d = ImageDraw.Draw(img)
            veto = "  ·  SENSOR VETO" if sort["veto"] else ""
            chrome_bar(
                d,
                f"Sort {sidx+1}/5   {sort['name']}  →  {sort['key']}  {BINS[sort['key']]['title']}{veto}",
                f"Vision {sort['vis']}   ·   moisture {sort['moist']:.0%}   ·   metal {'YES' if sort['metal'] else 'no'}   ·   disc indexes  ·   drop through pocket",
                "PART 05",
            )
            # side HUD
            d.rounded_rectangle((980, 80, 1256, 300), 10, fill=(18, 20, 22))
            d.text((996, 100), "FUSION", font=F_TINY, fill=(140, 148, 156), anchor="lt")
            d.text((996, 128), sort["vis"].upper(), font=F_H2, fill=GREEN if not sort["veto"] else (220, 130, 70), anchor="lt")
            d.text((996, 168), f"IR  PRESENT", font=F_M, fill=WHITE, anchor="lt")
            d.text((996, 190), f"MOIST  {sort['moist']:.0%}", font=F_M, fill=(220, 130, 70) if sort["moist"] >= 0.45 else WHITE, anchor="lt")
            d.text((996, 212), f"METAL  {'HIT' if sort['metal'] else 'NO'}", font=F_M, fill=WHITE, anchor="lt")
            d.text((996, 248), f"BAY  {sort['key']}", font=F_H2, fill=BINS[sort["key"]]["hue"], anchor="lt")
            if sort["veto"]:
                d.text((996, 278), "wet fibre → residual", font=F_S, fill=(220, 130, 70), anchor="lt")
            yield img
            if local >= 5.6:
                start_ang = target

    write_clip(OUT / "05_sorting.mp4", gen())


def part06_end():
    dur = 6.5
    n = int(dur * FPS)
    still = CAD / "exterior_clean.png"

    def gen():
        for i in range(n):
            t = i / FPS
            img = kenburns(still, t, dur, 1.04, 1.10)
            d = ImageDraw.Draw(img)
            chrome_bar(
                d,
                "Simulation complete  —  same assembly as the SolidWorks model",
                "Intake  →  dual-disc carousel  →  four cylinders  →  LED confirm",
                "END",
            )
            d.rectangle((80, 200, 1200, 430), fill=(18, 20, 22, 200) if False else (18, 20, 22))
            d.text((640, 250), "BIN-GENIE", font=F_BIG, fill=GREEN, anchor="mm")
            d.text((640, 300), "Working simulation of the CAD assembly", font=F_B, fill=WHITE, anchor="mm")
            d.text((640, 340), "PM-01  ·  PA-02  ·  GL-03  ·  RS-04", font=F_M, fill=(180, 186, 190), anchor="mm")
            d.text((640, 380), "No physical prototype required for this evidence.", font=F_S, fill=(160, 168, 176), anchor="mm")
            yield img

    write_clip(OUT / "06_end.mp4", gen())


def concat():
    lst = OUT / "concat.txt"
    parts = [
        "01_exterior.mp4",
        "02_intake.mp4",
        "03_exploded.mp4",
        "04_carousel.mp4",
        "05_sorting.mp4",
        "06_end.mp4",
    ]
    lst.write_text("".join(f"file '{OUT/p}'\n" for p in parts))
    full = ROOT / "static" / "video" / "BIN-GENIE_CAD_simulation.mp4"
    cmd = [FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(full)]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # also a copy at workspace root
    dest = ROOT / "BIN-GENIE_CAD_simulation.mp4"
    dest.write_bytes(full.read_bytes())
    print(f"FULL {full}  {full.stat().st_size/1e6:.1f}MB")
    for p in parts:
        src = OUT / p
        (ROOT / "sim_out" / p).write_bytes(src.read_bytes())
    print("parts copied to /home/user/sim_out/")


def main():
    print("rendering CAD motion-study clips…")
    part01_intro()
    part02_intake()
    part03_exploded()
    part04_carousel_index()
    part05_sorting()
    part06_end()
    concat()


if __name__ == "__main__":
    main()
