#!/usr/bin/env python3
"""Dynamic BIN-GENIE motion study: dual discs + two servos + live drops."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT = Path("/home/user")
OUT = ROOT / "static" / "video"
PARTS = ROOT / "sim_out"
SAMPLES = ROOT / "static" / "samples"
OUT.mkdir(parents=True, exist_ok=True)
PARTS.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1280, 720, 30
FF = imageio_ffmpeg.get_ffmpeg_exe()
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
F_H = ImageFont.truetype(FONTB, 22)
F_B = ImageFont.truetype(FONT, 15)
F_S = ImageFont.truetype(FONT, 13)
F_M = ImageFont.truetype(FONTM, 12)
F_T = ImageFont.truetype(FONTM, 11)
F_BIG = ImageFont.truetype(FONTB, 40)

BG0, BG1 = np.array([228, 236, 244], np.uint8), np.array([204, 216, 230], np.uint8)
GREEN = (46, 230, 78)
SILVER = (198, 204, 210)
BLACK = (34, 34, 36)
CREAM = (236, 228, 210)
SERVO = (28, 28, 30)
WHITE = (250, 250, 250)
INK = (22, 24, 26)

CUT = math.radians(96)
HOLD = math.radians(118)  # bottom-disc offset while carrying

BINS = {
    "PM-01": {"title": "Plastic / Metal", "pos": (0.58, 0.28), "hue": (80, 210, 90)},
    "PA-02": {"title": "Paper", "pos": (-0.58, 0.28), "hue": (220, 200, 140)},
    "GL-03": {"title": "Glass", "pos": (0.58, -0.28), "hue": (90, 175, 230)},
    "RS-04": {"title": "Residual", "pos": (-0.58, -0.28), "hue": (230, 130, 70)},
}

SORTS = [
    dict(kind="plastic", key="PM-01", name="PET bottle", vis="plastic", moist=0.06, metal=0, veto=False),
    dict(kind="paper", key="PA-02", name="Newsprint", vis="paper", moist=0.08, metal=0, veto=False),
    dict(kind="glass", key="GL-03", name="Glass bottle", vis="glass", moist=0.05, metal=0, veto=False),
    dict(kind="metal", key="PM-01", name="Aluminium can", vis="metal", moist=0.05, metal=1, veto=False),
    dict(kind="paper", key="RS-04", name="WET paper", vis="paper", moist=0.80, metal=0, veto=True),
]


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_ang(a, b, t):
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * t


def bin_ang(k):
    x, z = BINS[k]["pos"]
    return math.atan2(z, x)


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], np.float32)


def rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], np.float32)


class Cam:
    def __init__(self, az=0.65, el=0.38, dist=7.0, scale=400, look=(0, 0.55, 0), origin=(640, 400)):
        self.az, self.el, self.dist, self.scale = az, el, dist, scale
        self.look = np.array(look, np.float32)
        self.origin = origin

    def clone(self, **kw):
        d = dict(az=self.az, el=self.el, dist=self.dist, scale=self.scale,
                 look=tuple(self.look), origin=self.origin)
        d.update(kw)
        return Cam(**d)

    def project(self, pts):
        p = (pts - self.look) @ ry(self.az).T @ rx(-self.el).T
        z = p[:, 2] + self.dist
        x = p[:, 0] / z * self.dist
        y = p[:, 1] / z * self.dist
        return np.stack([self.origin[0] + x * self.scale,
                         self.origin[1] - y * self.scale, p[:, 2]], 1)


def cam_mix(a: Cam, b: Cam, t) -> Cam:
    t = ease(t)
    look = tuple(lerp(float(a.look[i]), float(b.look[i]), t) for i in range(3))
    orig = (lerp(a.origin[0], b.origin[0], t), lerp(a.origin[1], b.origin[1], t))
    return Cam(az=lerp_ang(a.az, b.az, t), el=lerp(a.el, b.el, t),
               dist=lerp(a.dist, b.dist, t), scale=lerp(a.scale, b.scale, t),
               look=look, origin=orig)


LIGHT = np.array([-0.45, 0.8, 0.5], np.float32)
LIGHT /= np.linalg.norm(LIGHT)


def shade(rgb, n, emit=False):
    if emit:
        return rgb
    n = n / (np.linalg.norm(n) + 1e-8)
    k = 0.32 + 0.68 * float(np.clip(n @ LIGHT, 0, 1))
    return tuple(int(np.clip(c * k, 0, 255)) for c in rgb)


def face(pts, rgb, n=None, emit=False):
    pts = np.asarray(pts, np.float32)
    if n is None:
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    return {"pts": pts, "rgb": rgb, "n": np.asarray(n, np.float32), "emit": emit}


def box(x0, x1, y0, y1, z0, z1, rgb, skip=(), emit=False):
    p = dict(
        a=(x0, y0, z1), b=(x1, y0, z1), c=(x1, y1, z1), d=(x0, y1, z1),
        e=(x0, y0, z0), f=(x1, y0, z0), g=(x1, y1, z0), h=(x0, y1, z0),
    )
    q = {
        "front": (p["a"], p["b"], p["c"], p["d"]),
        "back": (p["f"], p["e"], p["h"], p["g"]),
        "left": (p["e"], p["a"], p["d"], p["h"]),
        "right": (p["b"], p["f"], p["g"], p["c"]),
        "top": (p["d"], p["c"], p["g"], p["h"]),
        "bottom": (p["e"], p["f"], p["b"], p["a"]),
    }
    return [face(v, rgb, emit=emit) for k, v in q.items() if k not in skip]


def cyl(cx, y0, y1, cz, r, rgb, segs=16, top=True, bot=True, emit=False):
    out = []
    ang = np.linspace(0, 2 * math.pi, segs, endpoint=False)
    T = np.stack([cx + r * np.cos(ang), np.full_like(ang, y1), cz + r * np.sin(ang)], 1)
    B = np.stack([cx + r * np.cos(ang), np.full_like(ang, y0), cz + r * np.sin(ang)], 1)
    for i in range(segs):
        j = (i + 1) % segs
        out.append(face([B[i], B[j], T[j], T[i]], rgb, emit=emit))
    if top:
        ctr = np.array([cx, y1, cz], np.float32)
        for i in range(segs):
            out.append(face([ctr, T[i], T[(i + 1) % segs]], rgb, n=np.array([0, 1, 0], np.float32), emit=emit))
    if bot:
        ctr = np.array([cx, y0, cz], np.float32)
        for i in range(segs):
            out.append(face([ctr, B[(i + 1) % segs], B[i]], rgb, n=np.array([0, -1, 0], np.float32), emit=emit))
    return out


def disc(cx, y, cz, r, thick, rot, rgb, segs=36):
    """Solid disc with a rim pocket matching the SolidWorks cutout."""
    faces = []
    y0, y1 = y - thick / 2, y + thick / 2
    bite = r * 0.40
    hub = np.array([cx, y1, cz], np.float32)
    hub0 = np.array([cx, y0, cz], np.float32)

    def incut(a):
        d = (a - rot + math.pi) % (2 * math.pi) - math.pi
        return abs(d) <= CUT / 2

    angs = [i * 2 * math.pi / segs for i in range(segs)] + [rot - CUT / 2, rot + CUT / 2]
    angs = sorted({a % (2 * math.pi) for a in angs})
    n = len(angs)

    def P(rr, yy, a):
        return np.array([cx + rr * math.cos(a), yy, cz + rr * math.sin(a)], np.float32)

    for k in range(n):
        a, b = angs[k], angs[(k + 1) % n]
        mid = (a + ((b - a) % (2 * math.pi)) / 2) % (2 * math.pi)
        shine = 0.78 + 0.22 * abs(math.sin(2 * a))
        col = tuple(int(np.clip(c * shine, 0, 255)) for c in rgb)
        dim = tuple(max(0, c - 24) for c in col)
        rr = bite if incut(mid) else r
        faces.append(face([hub, P(rr, y1, a), P(rr, y1, b)], col, n=np.array([0, 1, 0], np.float32)))
        faces.append(face([hub0, P(rr, y0, b), P(rr, y0, a)], col, n=np.array([0, -1, 0], np.float32)))
        faces.append(face([P(rr, y0, a), P(rr, y0, b), P(rr, y1, b), P(rr, y1, a)], dim))
    for a in (rot - CUT / 2, rot + CUT / 2):
        faces.append(face([P(r, y0, a), P(bite, y0, a), P(bite, y1, a), P(r, y1, a)], tuple(max(0, c - 36) for c in rgb)))
    return faces


def xf(faces, R=None, t=None):
    """Rotate/translate a mesh (around origin then offset)."""
    out = []
    for f in faces:
        pts = f["pts"].copy()
        if R is not None:
            pts = pts @ R.T
        if t is not None:
            pts = pts + np.asarray(t, np.float32)
        n = f["n"]
        if R is not None:
            n = n @ R.T
        out.append({"pts": pts, "rgb": f["rgb"], "n": n, "emit": f.get("emit", False)})
    return out


def servo_body():
    """Hobby servo in local space: body along X, output shaft +Y at origin."""
    f = []
    f += box(-0.055, 0.075, -0.028, 0.028, -0.06, 0.06, SERVO)
    f += box(-0.078, 0.098, 0.018, 0.026, -0.012, 0.012, (50, 50, 52))  # tabs
    f += cyl(0.0, 0.028, 0.048, 0.0, 0.016, (20, 20, 22), segs=12)
    f += cyl(0.0, 0.048, 0.055, 0.0, 0.008, (180, 160, 60), segs=10)  # spline
    return f


def servo_horn(angle):
    """Single arm horn in XY, rotating about Y."""
    f = []
    # hub
    f += cyl(0.0, 0.055, 0.068, 0.0, 0.018, CREAM, segs=12)
    # arm
    R = ry(angle)
    arm = box(-0.012, 0.012, 0.058, 0.066, 0.0, 0.085, CREAM)
    f += xf(arm, R=R)
    f += xf(cyl(0.0, 0.058, 0.066, 0.078, 0.01, CREAM, segs=8), R=R)
    return f


def flap_mesh(rot, open_ang, y=0.84):
    """Semicircular drop flap under the pocket. open_ang 0=closed, 1=open down."""
    # hinge at inner bite of pocket, hangs in the pocket sector
    faces = []
    r0, r1 = 0.12, 0.33
    tilt = -open_ang * math.radians(70)
    # rotate around X of a local frame at the pocket
    ca, sa = math.cos(rot), math.sin(rot)
    hinge = np.array([ca * r0, y, sa * r0], np.float32)
    # local: x along pocket radial, y up, z along tangent
    ex = np.array([ca, 0, sa], np.float32)
    ey = np.array([0, 1, 0], np.float32)
    ez = np.array([-sa, 0, ca], np.float32)
    # tilt around tangent (ez)
    ct, st = math.cos(tilt), math.sin(tilt)
    ey2 = ey * ct + ex * st
    ex2 = ex * ct - ey * st
    n = 8
    for i in range(n):
        t0 = -CUT / 2 + CUT * i / n
        t1 = -CUT / 2 + CUT * (i + 1) / n
        def pt(rr, tt):
            # closed flap in disc plane along pocket
            return hinge + ex2 * (rr - r0) * math.cos(0) + ez * rr * math.sin(tt) * 0.35 + ey2 * 0
            # simpler polar in tilted plane
        # polar in (ex2, ez)
        def Q(rr, tt):
            return hinge + ex2 * (rr - r0) * math.cos(tt * 0.15) + ez * rr * math.sin(tt)
        # actually: points of a sector in the tilted plane
        def S(rr, tt):
            return hinge + (ex2 * math.cos(tt) + ez * math.sin(tt)) * (rr - r0) * (r1 / (r1 - r0) * 0 + 1) * ((rr) / r1)
        def P(rr, tt):
            radial = ex2 * math.cos(tt) + ez * math.sin(tt)
            return hinge + radial * rr
        faces.append(face([P(r0, t0), P(r1, t0), P(r1, t1), P(r0, t1)], (170, 175, 180)))
    return faces


def static_plant():
    f = []
    # base
    f += box(-0.36, 0.36, 0.0, 0.06, -0.40, 0.40, BLACK)
    # back plate
    f += box(-0.30, 0.30, 0.06, 0.55, -0.48, -0.42, BLACK)
    # shaft
    f += cyl(0.0, 0.06, 0.86, 0.0, 0.038, (24, 24, 26), segs=14)
    # side U housings + cylinders
    for side, cx in ((-1, -0.58), (1, 0.58)):
        wall = 0.04
        if side < 0:
            f += box(cx - 0.22, cx - 0.22 + wall, 0.06, 0.68, -0.48, 0.48, BLACK)
            f += box(cx - 0.22, cx + 0.14, 0.06, 0.68, -0.48, -0.48 + wall, BLACK)
            f += box(cx - 0.22, cx + 0.14, 0.06, 0.68, 0.48 - wall, 0.48, BLACK)
        else:
            f += box(cx + 0.22 - wall, cx + 0.22, 0.06, 0.68, -0.48, 0.48, BLACK)
            f += box(cx - 0.14, cx + 0.22, 0.06, 0.68, -0.48, -0.48 + wall, BLACK)
            f += box(cx - 0.14, cx + 0.22, 0.06, 0.68, 0.48 - wall, 0.48, BLACK)
    for k, b in BINS.items():
        x, z = b["pos"]
        f += cyl(x, 0.08, 0.64, z, 0.15, (18, 18, 20), segs=16, top=False)
        f += cyl(x, 0.08, 0.11, z, 0.145, (14, 14, 16), segs=12, bot=False)
        # floor arrow from disc toward this bay
        ang = math.atan2(z, x)
        f += box(
            x - 0.03 * math.cos(ang + 1.2), x + 0.03 * math.cos(ang),
            0.065, 0.075,
            z - 0.03 * math.sin(ang + 1.2), z + 0.03 * math.sin(ang),
            b["hue"], emit=True,
        )
    # degree ticks around the disc (clock face)
    for i in range(12):
        a = i * math.pi / 6
        r0, r1 = (0.36, 0.41) if i % 3 == 0 else (0.37, 0.40)
        x0, z0 = r0 * math.cos(a), r0 * math.sin(a)
        x1, z1 = r1 * math.cos(a), r1 * math.sin(a)
        f += box(min(x0, x1) - 0.008, max(x0, x1) + 0.008, 0.068, 0.078,
                 min(z0, z1) - 0.008, max(z0, z1) + 0.008,
                 GREEN if i % 3 == 0 else (90, 90, 92), emit=(i % 3 == 0))
    return f


def housing(cutaway=False):
    # Always skip the solid front — rebuild it around the intake hole.
    skip = {"front"}
    if cutaway:
        skip |= {"top", "left", "right"}
    f = box(-0.72, 0.72, 0.0, 1.62, -0.52, 0.52, (42, 42, 44), skip=skip)
    for x, z in ((-0.55, -0.36), (0.55, -0.36), (-0.55, 0.36), (0.55, 0.36)):
        f += cyl(x, -0.02, 0.03, z, 0.05, (22, 22, 24), segs=8)
    f += box(-0.72, 0.72, 1.62, 1.645, 0.50, 0.52, GREEN, emit=True)
    f += box(-0.72, 0.72, 1.62, 1.645, -0.52, -0.50, GREEN, emit=True)
    f += box(-0.72, -0.70, 1.62, 1.645, -0.52, 0.52, GREEN, emit=True)
    f += box(0.70, 0.72, 1.62, 1.645, -0.52, 0.52, GREEN, emit=True)
    if not cutaway:
        # front panels around chrome window (a real hole)
        f += box(-0.72, 0.72, 0.00, 1.20, 0.50, 0.52, (42, 42, 44))
        f += box(-0.72, 0.72, 1.52, 1.62, 0.50, 0.52, (42, 42, 44))
        f += box(-0.72, 0.04, 1.20, 1.52, 0.50, 0.52, (42, 42, 44))
        f += box(0.50, 0.72, 1.20, 1.52, 0.50, 0.52, (42, 42, 44))
        f += box(0.04, 0.50, 1.20, 1.52, 0.40, 0.50, (16, 16, 18))
        f += box(0.02, 0.52, 1.18, 1.20, 0.50, 0.53, SILVER)
        f += box(0.02, 0.52, 1.52, 1.54, 0.50, 0.53, SILVER)
        f += box(0.02, 0.04, 1.18, 1.54, 0.50, 0.53, SILVER)
        f += box(0.50, 0.52, 1.18, 1.54, 0.50, 0.53, SILVER)
    return f


# servo mounts: S1 at base right of shaft (disc index), S2 at base left (drop flap)
def servo_placed(which, horn_ang):
    mesh = servo_body() + servo_horn(horn_ang)
    for f in mesh:
        f["pts"] = f["pts"] * 2.15
        f["n"] = f["n"]
    # both servos sit IN FRONT of the base so the working camera can see the horns turn
    if which == 1:
        return xf(mesh, t=(0.26, 0.12, 0.58))
    return xf(mesh, t=(-0.26, 0.12, 0.58))


def bg():
    col = np.linspace(BG0, BG1, H, dtype=np.uint8)
    return Image.fromarray(np.repeat(col[:, None, :], W, axis=1), "RGB")


def draw(img, faces, cam):
    d = ImageDraw.Draw(img)
    buf = []
    for f in faces:
        pr = cam.project(f["pts"])
        depth = float(pr[:, 2].mean())
        col = shade(f["rgb"], f["n"], emit=f.get("emit"))
        poly = [(float(x), float(y)) for x, y, _ in pr]
        buf.append((depth, poly, col))
    buf.sort(key=lambda t: t[0], reverse=True)
    for _, poly, col in buf:
        if len(poly) < 3:
            continue
        edge = tuple(max(0, c - 16) for c in col)
        d.polygon(poly, fill=col, outline=edge)
    return img


def hud(d, title, sub, t, extra=None):
    d.rectangle((0, 0, W, 46), fill=(16, 18, 20))
    d.rectangle((0, 44, W, 46), fill=GREEN)
    d.text((20, 24), "BIN-GENIE", font=F_H, fill=GREEN, anchor="lm")
    d.text((160, 24), "MOTION STUDY  ·  dual-disc + 2× servo", font=F_M, fill=(150, 156, 164), anchor="lm")
    d.text((W - 20, 24), f"{t:05.1f}s", font=F_M, fill=WHITE, anchor="rm")
    d.rectangle((0, H - 58, W, H), fill=(16, 18, 20))
    d.text((22, H - 36), title, font=F_H, fill=WHITE, anchor="lm")
    d.text((22, H - 14), sub, font=F_S, fill=(168, 174, 180), anchor="lm")
    if extra:
        extra(d)


TOKENS = {}


def load_tokens():
    global TOKENS
    for k, fn in {
        "plastic": "plastic_bottle.jpg",
        "paper": "newspaper.jpg",
        "glass": "glass_bottle.jpg",
        "metal": "soda_can.jpg",
        "organic": "banana_peel.jpg",
    }.items():
        im = Image.open(SAMPLES / fn).convert("RGB")
        im.thumbnail((48, 48), Image.Resampling.LANCZOS)
        c = Image.new("RGB", (48, 48), (30, 30, 32))
        c.paste(im, ((48 - im.width) // 2, (48 - im.height) // 2))
        m = Image.new("L", (48, 48), 0)
        ImageDraw.Draw(m).ellipse((1, 1, 46, 46), fill=255)
        TOKENS[k] = (c, m)


def paste_tok(img, kind, xy, sc=1.0):
    tok, mask = TOKENS[kind]
    s = max(10, int(48 * sc))
    tok = tok.resize((s, s), Image.Resampling.LANCZOS)
    mask = mask.resize((s, s), Image.Resampling.LANCZOS)
    img.paste(tok, (int(xy[0] - s / 2), int(xy[1] - s / 2)), mask)


# ---------- timeline ----------
# 0-5 exterior orbit + title
# 5-9 intake
# 9-13 cutaway + servo intro
# 13-16 servo demo
# then 5 sorts * 6.4s
# end 4s
T_EXT, T_IN, T_CUT, T_DEMO = 5.0, 4.0, 4.0, 3.2
PER = 6.4
T_SORT0 = T_EXT + T_IN + T_CUT + T_DEMO  # 16.2
T_END = 4.5
DUR = T_SORT0 + PER * len(SORTS) + T_END


def state_at(t):
    """Return disc_top, disc_bot, flap01, item, cam, cutaway, caption, hud_sort."""
    lift = 0.0
    if t > T_EXT + T_IN - 0.5:
        lift = 2.4 * ease(min(1.0, (t - (T_EXT + T_IN - 0.5)) / 2.8))
    hide_housing = lift > 1.35
    cutaway = t >= T_EXT + T_IN - 0.4
    cam_ext = Cam(az=0.42 + 0.22 * math.sin(t * 0.4), el=0.30, dist=7.0, scale=360,
                  look=(0.12, 0.90, 0.15), origin=(640, 400))
    cam_srv = Cam(az=0.05, el=0.85, dist=5.8, scale=430, look=(0.0, 0.22, 0.45), origin=(640, 420))
    cam_work = Cam(az=0.18 + 0.22 * math.sin(max(0, t - T_SORT0) * 0.15),
                   el=1.12, dist=7.0, scale=300, look=(0, 0.40, 0.12), origin=(640, 400))

    rot_top = bin_ang("PM-01")
    rot_bot = rot_top + HOLD
    flap = 0.0
    item = None
    caption = ("Dual-disc carousel inside the black ABS housing",
               "Green LED rim  ·  chrome intake  ·  four cylindrical bays")
    sort_hud = None
    led = 0.55 + 0.45 * abs(math.sin(t * 3.0))

    if t < T_EXT:
        cam = cam_ext
        caption = ("1  Exterior — your housing",
                   "Waste enters the chrome window. LED rim confirms a sort.")
    elif t < T_EXT + T_IN:
        u = (t - T_EXT) / T_IN
        cam = cam_mix(cam_ext, cam_ext.clone(az=0.55, el=0.42, scale=420, look=(0.15, 1.1, 0.3)), u)
        k = ease(u)
        item = dict(kind="plastic",
                    pos=(lerp(0.95, 0.22, k), lerp(1.55, 1.05, k), lerp(1.05, 0.22, k)),
                    sc=lerp(1.1, 0.8, k))
        caption = ("2  Intake", "Item goes through the window and lands in the sector pocket.")
    elif t < T_EXT + T_IN + T_CUT:
        u = (t - T_EXT - T_IN) / T_CUT
        cam = cam_mix(cam_ext.clone(el=0.5), cam_srv, u)
        caption = ("3  Dual motors",
                   "SERVO 1 indexes the discs.  SERVO 2 opens the drop flap under the pocket.")
        rot_top = bin_ang("PM-01") + 0.4 * math.sin(u * math.pi)
        rot_bot = rot_top + HOLD
    elif t < T_SORT0:
        u = (t - T_EXT - T_IN - T_CUT) / T_DEMO
        cam = cam_mix(cam_srv, cam_work, u)
        # demo: S1 90°, S2 flap
        rot_top = lerp_ang(bin_ang("PM-01"), bin_ang("PA-02"), ease(min(1, u / 0.7)))
        rot_bot = rot_top + HOLD * (1 - ease(max(0, (u - 0.55) / 0.35)))
        flap = ease(max(0, (u - 0.55) / 0.3)) * (1 - ease(max(0, (u - 0.85) / 0.15)))
        caption = ("3  Servo demo",
                   "Watch the cream horns — Servo 1 turns with the disc, Servo 2 dumps the pocket.")
    elif t < T_SORT0 + PER * len(SORTS):
        u = t - T_SORT0
        sidx = min(len(SORTS) - 1, int(u / PER))
        local = u - sidx * PER
        sort = SORTS[sidx]
        prev_key = "PA-02" if sidx == 0 else SORTS[sidx - 1]["key"]
        a0, a1 = bin_ang(prev_key), bin_ang(sort["key"])
        cam = cam_work
        if local < 0.7:
            rot_top = a0
            rot_bot = a0 + HOLD
            k = ease(local / 0.7)
            px, pz = 0.22 * math.cos(rot_top), 0.22 * math.sin(rot_top)
            item = dict(kind=sort["kind"], pos=(px, lerp(1.15, 0.98, k), pz), sc=1.0)
            caption = (f"Sort {sidx+1}/5  {sort['name']}  seated in the pocket",
                       "Lime pointer = pocket. Bottom disc OFFSET — item sits on a floor.")
        elif local < 3.6:
            k = ease((local - 0.7) / 2.9)
            rot_top = lerp_ang(a0, a1, k)
            rot_bot = rot_top + HOLD
            px, pz = 0.22 * math.cos(rot_top), 0.22 * math.sin(rot_top)
            item = dict(kind=sort["kind"], pos=(px, 0.98, pz), sc=1.0)
            now = math.degrees(rot_top) % 360
            deg0, deg1 = (math.degrees(a0) % 360), (math.degrees(a1) % 360)
            cam = cam_work.clone(el=1.22, scale=360, look=(0.0, 0.92, 0.0), origin=(560, 400))
            caption = (f"SERVO 1 rotating both discs   {now:5.0f}°    {deg0:.0f}° → {deg1:.0f}°",
                       "Lime pointer rides with the pocket. Discs locked. Gate still CLOSED.")
        elif local < 4.0:
            rot_top = a1
            rot_bot = a1 + HOLD
            px, pz = 0.22 * math.cos(rot_top), 0.22 * math.sin(rot_top)
            item = dict(kind=sort["kind"], pos=(px, 0.98, pz), sc=1.0)
            caption = (f"Pointer over {sort['key']}  —  Servo 1 holding",
                       "Pocket is above the target cylinder. Servo 2 will open the gate.")
        elif local < 4.7:
            k = ease((local - 4.0) / 0.7)
            rot_top = a1
            rot_bot = lerp_ang(a1 + HOLD, a1, k)
            flap = k
            px, pz = 0.22 * math.cos(rot_top), 0.22 * math.sin(rot_top)
            item = dict(kind=sort["kind"], pos=(px, 0.98, pz), sc=1.0)
            cam = cam_work.clone(el=1.18, scale=350, look=(0.0, 0.90, 0.0), origin=(560, 400))
            caption = (f"SERVO 2 turning BOTTOM disc   offset {math.degrees(rot_bot-rot_top):+.0f}°",
                       "Bottom pocket swings to match the top. When lined up, the floor disappears.")
        elif local < 5.7:
            k = ease((local - 4.7) / 1.0)
            rot_top = a1
            rot_bot = a1
            flap = 1.0
            bx, bz = BINS[sort["key"]]["pos"]
            px = lerp(0.22 * math.cos(a1), bx, k)
            pz = lerp(0.22 * math.sin(a1), bz, k)
            py = lerp(0.98, 0.22, k) - 0.08 * math.sin(k * math.pi)
            item = dict(kind=sort["kind"], pos=(px, py, pz), sc=lerp(1.0, 0.5, k))
            cap = "SENSOR VETO — wet fibre cannot enter paper. Divert RS-04." if sort["veto"] else f"Drop through aligned pockets into {sort['key']}"
            caption = (cap, f"Vision {sort['vis']}  ·  moisture {sort['moist']:.0%}  ·  metal {'YES' if sort['metal'] else 'no'}")
        else:
            k = ease((local - 5.7) / 0.7)
            rot_top = a1
            rot_bot = lerp_ang(a1, a1 + HOLD, k)
            flap = 1 - k
            bx, bz = BINS[sort["key"]]["pos"]
            item = dict(kind=sort["kind"], pos=(bx, 0.22, bz), sc=0.45)
            caption = (f"In {sort['key']}  ·  bottom disc offsets again",
                       "Servo 2 returns. Floor is back. Ready for the next item.")
        sort_hud = sort
        led = 1.0 if 4.7 <= local <= 5.7 else 0.6
    else:
        u = (t - (T_SORT0 + PER * len(SORTS))) / T_END
        cam = cam_mix(cam_work, cam_ext.clone(az=0.85, el=0.32, scale=360), u)
        cutaway = u < 0.55
        rot_top = bin_ang("RS-04")
        rot_bot = rot_top + HOLD
        caption = ("Simulation complete",
                   "Same assembly as the SolidWorks model — dual disc, two servos, four bays.")
        led = 0.8

    return dict(cam=cam, cutaway=cutaway, hide_housing=hide_housing, lift=lift,
                rot_top=rot_top, rot_bot=rot_bot, flap=flap, item=item,
                caption=caption, sort=sort_hud, led=led)


def fills_at(t):
    out = {k: 0.0 for k in BINS}
    if t < T_SORT0:
        return out
    u = t - T_SORT0
    for i, s in enumerate(SORTS):
        # after drop phase of that sort
        done = u > i * PER + 5.0
        if done:
            out[s["key"]] += 0.22
    return out


def frame(t):
    st = state_at(t)
    cam = st["cam"]
    faces = []
    if not st.get("hide_housing"):
        hs = housing(cutaway=st["cutaway"])
        if st.get("lift", 0) > 0.02:
            hs = xf(hs, t=(0, st["lift"], 0))
        faces += hs
    faces += static_plant()
    # fills
    for k, h in fills_at(t).items():
        if h <= 0:
            continue
        x, z = BINS[k]["pos"]
        faces += cyl(x, 0.12, 0.12 + 0.35 * min(1, h), z, 0.13, BINS[k]["hue"], segs=12, bot=False)
    # discs
    faces += disc(0, 0.96, 0, 0.33, 0.04, st["rot_top"], SILVER)
    faces += disc(0, 0.90, 0, 0.33, 0.04, st["rot_bot"], (168, 174, 180))
    faces += cyl(0, 0.98, 1.05, 0, 0.032, (22, 22, 24), segs=10)
    # flap (visual extra under pocket)
    faces += flap_mesh(st["rot_top"], st["flap"], y=0.86)
    # servos
    faces += servo_placed(1, st["rot_top"])
    faces += servo_placed(2, st["rot_bot"])
    # LED intensity: already emit green; pulse by extra boxes skipped
    img = bg()
    draw(img, faces, cam)
    if st["item"]:
        p = cam.project(np.array([st["item"]["pos"]], np.float32))[0]
        paste_tok(img, st["item"]["kind"], (float(p[0]), float(p[1])), st["item"]["sc"])
    d = ImageDraw.Draw(img)
    sort = st["sort"]

    def extra(dd):
        for which, label, col in ((1, "SERVO 1  DISC INDEX", GREEN), (2, "SERVO 2  DROP GATE", (90, 175, 230))):
            pos = (0.26, 0.28, 0.58) if which == 1 else (-0.26, 0.28, 0.58)
            q = cam.project(np.array([pos], np.float32))[0]
            dd.text((float(q[0]), float(q[1]) - 16), label, font=F_T, fill=col, anchor="mm")
        # live disc angles
        top_deg = math.degrees(st["rot_top"]) % 360
        bot_deg = math.degrees(st["rot_bot"]) % 360
        off = ((st["rot_bot"] - st["rot_top"] + math.pi) % (2 * math.pi) - math.pi)
        off_deg = math.degrees(off)
        dd.rounded_rectangle((40, 64, 430, 168), 10, fill=(16, 18, 20))
        dd.text((56, 84), "DUAL DISC", font=F_T, fill=(140, 148, 156), anchor="lt")
        dd.text((56, 108), f"TOP     {top_deg:6.1f}°   servo 1", font=F_M, fill=GREEN, anchor="lt")
        dd.text((56, 128), f"BOTTOM  {bot_deg:6.1f}°   servo 2", font=F_M, fill=(90, 175, 230), anchor="lt")
        gate = "OPEN (aligned)" if abs(off_deg) < 8 else f"CLOSED  offset {off_deg:+.0f}°"
        dd.text((56, 148), f"GATE    {gate}", font=F_M, fill=WHITE, anchor="lt")
        if sort:
            dd.rounded_rectangle((980, 64, 1258, 250), 10, fill=(16, 18, 20))
            dd.text((996, 82), "FUSION", font=F_T, fill=(140, 148, 156), anchor="lt")
            col = (230, 130, 70) if sort["veto"] else GREEN
            dd.text((996, 108), sort["vis"].upper(), font=F_H, fill=col, anchor="lt")
            dd.text((996, 140), f"IR  PRESENT", font=F_M, fill=WHITE, anchor="lt")
            dd.text((996, 158), f"MOIST  {sort['moist']:.0%}", font=F_M,
                    fill=(230, 130, 70) if sort["moist"] >= 0.45 else WHITE, anchor="lt")
            dd.text((996, 176), f"METAL  {'HIT' if sort['metal'] else 'NO'}", font=F_M, fill=WHITE, anchor="lt")
            dd.text((996, 206), f"→  {sort['key']}", font=F_H, fill=BINS[sort["key"]]["hue"], anchor="lt")

    hud(d, st["caption"][0], st["caption"][1], t, extra)
    return img


def encode(path, t0, t1):
    proc = subprocess.Popen([
        FF, "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "17", "-preset", "fast", "-movflags", "+faststart", str(path),
    ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    n = 0
    t = t0
    dt = 1.0 / FPS
    while t < t1 - 1e-6:
        img = frame(t)
        proc.stdin.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes())
        n += 1
        t += dt
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="ignore")
    rc = proc.wait()
    if rc:
        raise SystemExit(err[-2000:])
    print(f"{path.name:32} {n/FPS:5.1f}s  {path.stat().st_size/1e6:.1f}MB")
    return n


def main():
    load_tokens()
    # preview stills
    for name, tt in (("prev_ext", 2.0), ("prev_servo", 12.5), ("prev_drop", T_SORT0 + PER + 4.6)):
        frame(tt).save(f"/tmp/{name}.png")
        print("preview", name)
    cuts = [
        ("01_housing.mp4", 0.0, T_EXT),
        ("02_intake.mp4", T_EXT, T_EXT + T_IN),
        ("03_servos.mp4", T_EXT + T_IN, T_SORT0),
        ("04_working_sorts.mp4", T_SORT0, T_SORT0 + PER * len(SORTS)),
        ("05_end.mp4", T_SORT0 + PER * len(SORTS), DUR),
    ]
    files = []
    for name, a, b in cuts:
        p = PARTS / name
        encode(p, a, b)
        files.append(p)
    lst = PARTS / "concat2.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in files))
    full = ROOT / "BIN-GENIE_working_simulation.mp4"
    subprocess.check_call([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(full)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (OUT / "BIN-GENIE_working_simulation.mp4").write_bytes(full.read_bytes())
    print("FULL", full, f"{full.stat().st_size/1e6:.1f}MB  dur={DUR:.1f}s")


if __name__ == "__main__":
    main()
