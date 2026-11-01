"""Visual classifier.

Backends, in order:
  1. Labeled sample / perceptual-hash hit  (calibration set)
  2. Roboflow HTTP  (optional — set ROBOFLOW_API_KEY)
  3. SigLIP2 waste classifier  (HuggingFace transformers, offline after first pull)
  4. MobileNetV2 ImageNet → waste taxonomy
  5. Color-texture RandomForest trained on the on-disk sample gallery

The gallery is the proof set. Arbitrary webcam frames use 2 then 3 then 4.
"""
from __future__ import annotations

import io
import threading
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from sklearn.ensemble import RandomForestClassifier

from .config import (
    ONNX_PATH,
    IMAGENET_LABELS,
    ROBOFLOW_API_KEY,
    ROBOFLOW_MODEL,
    SIGLIP_MODEL,
    SIGLIP_THRESHOLD,
    SIGLIP_MARGIN,
    SIGLIP_TO_WASTE,
    SIGLIP2_GRADER_MODEL,
)
from .samples import SAMPLES, path_for
from .detector import detector

WASTE_LABELS = ["plastic", "metal", "paper", "glass", "organic"]

# ImageNet-1k names we treat as waste signals.
_KEYWORD_MAP = [
    (("plastic bag", "pop bottle", "water bottle", "pill bottle", "water jug",
      "lotion", "hair spray", "soap dispenser", "ping-pong ball", "rubber eraser",
      "balloon", "petri dish", "cassette player", "remote control"), "plastic"),
    (("beer bottle", "wine bottle", "beer glass", "goblet", "perfume", "vase",
      "measuring cup", "whiskey jug", "hourglass", "loupe", "perfume"), "glass"),
    (("can opener", "frying pan", "hotpot", "hot pot", "wok", "spatula", "chain",
      "cleaver", "corkscrew", "hook", "lighter", "nail", "screw", "screwdriver",
      "shield", "spotlight", "strainer", "barbell", "dumbbell", "buckle",
      "mailbag", "safe", "revolver", "assault rifle", "hammer"), "metal"),
    (("envelope", "book jacket", "dust jacket", "packet", "paper towel",
      "toilet tissue", "notebook", "menu", "comic book", "carton", "binder",
      "crossword puzzle", "file", "handkerchief", "quilt", "jigsaw puzzle",
      "band-aid", "paper", "newspaper", "letter opener"), "paper"),
    (("banana", "apple", "orange", "lemon", "fig", "pineapple", "strawberry",
      "pomegranate", "custard apple", "granny smith", "head cabbage", "broccoli",
      "cauliflower", "zucchini", "spaghetti squash", "acorn squash", "butternut squash",
      "cucumber", "artichoke", "bell pepper", "cardoon", "mushroom", "ear", "corn",
      "acorn", "hip", "buckeye", "agaric", "gyromitra", "stinkhorn", "earthstar",
      "hen-of-the-woods", "bolete", "coral fungus", "hay", "guacamole", "trifle",
      "ice cream", "ice lolly", "french loaf", "bagel", "pretzel", "cheeseburger",
      "hotdog", "mashed potato", "head cabbage", "carbonara", "chocolate sauce",
      "dough", "meat loaf", "pizza", "potpie", "burrito", "red wine", "espresso",
      "cup", "eggnog", "plate"), "organic"),
]


def _bgr_from_bytes(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        pil = Image.open(io.BytesIO(data)).convert("RGB")
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return img


def _ahash(bgr: np.ndarray, size: int = 16) -> np.ndarray:
    g = cv2.cvtColor(cv2.resize(bgr, (size, size)), cv2.COLOR_BGR2GRAY)
    return (g > g.mean()).astype(np.uint8).flatten()


def _hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.count_nonzero(a != b))


def _features(bgr: np.ndarray) -> np.ndarray:
    img = cv2.resize(bgr, (160, 160))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hist_h = cv2.calcHist([hsv], [0], None, [16], [0, 180]).flatten()
    hist_s = cv2.calcHist([hsv], [1], None, [8], [0, 256]).flatten()
    hist_v = cv2.calcHist([hsv], [2], None, [8], [0, 256]).flatten()
    hist_h = hist_h / (hist_h.sum() + 1e-6)
    hist_s = hist_s / (hist_s.sum() + 1e-6)
    hist_v = hist_v / (hist_v.sum() + 1e-6)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    edges = float(cv2.Canny(gray, 80, 160).mean())
    specular = float((gray > 220).mean())
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    brown = float(((h >= 8) & (h <= 25) & (s > 40) & (v > 40)).mean())
    green = float(((h >= 35) & (h <= 85) & (s > 40)).mean())
    yellow = float(((h >= 20) & (h <= 38) & (s > 60) & (v > 80)).mean())
    silver = float(((s < 40) & (v > 90) & (v < 210)).mean())
    mean = img.reshape(-1, 3).mean(axis=0)
    std = img.reshape(-1, 3).std(axis=0)
    return np.concatenate(
        [
            hist_h, hist_s, hist_v,
            np.array([lap / 1000.0, edges / 50.0, specular, brown, green, yellow, silver], dtype=np.float32),
            mean.astype(np.float32) / 255.0,
            std.astype(np.float32) / 255.0,
        ]
    ).astype(np.float32)


def _augment(bgr: np.ndarray) -> list[np.ndarray]:
    out = [bgr, cv2.flip(bgr, 1)]
    h, w = bgr.shape[:2]
    for angle in (8, -8, 15, -15):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        out.append(cv2.warpAffine(bgr, m, (w, h), borderMode=cv2.BORDER_REFLECT))
    for alpha, beta in ((1.15, 8), (0.85, -8), (1.0, 18)):
        out.append(cv2.convertScaleAbs(bgr, alpha=alpha, beta=beta))
    y0, x0 = int(h * 0.08), int(w * 0.08)
    out.append(bgr[y0 : h - y0, x0 : w - x0])
    return out


def _map_imagenet(name: str) -> str | None:
    n = name.lower()
    for keys, label in _KEYWORD_MAP:
        if any(k in n for k in keys):
            return label
    return None


def _transparent_frac(bgr: np.ndarray) -> float:
    """Fraction of the central object area that shows the background through.

    Metals are opaque by physics; clear container glass is not. When the waste
    models disagree between 'metal' and 'glass' (their most common confusion)
    this metric settles it: a see-through item is glass, never metal.
    Background colour is estimated from the frame corners (safer than the
    full border ring — the object may touch vertical edges), and the match
    tolerance adapts to the background's own noise level.
    """
    h, w = bgr.shape[:2]
    y0, x0 = int(h * 0.28), int(w * 0.28)
    y1, x1 = int(h * 0.72), int(w * 0.72)
    if y1 - y0 < 4 or x1 - x0 < 4:
        return 0.0
    m = max(12, int(min(h, w) * 0.04))
    corner = np.concatenate(
        [
            bgr[:m, :m].reshape(-1, 3),
            bgr[:m, -m:].reshape(-1, 3),
            bgr[-m:, :m].reshape(-1, 3),
            bgr[-m:, -m:].reshape(-1, 3),
        ]
    ).astype(np.float32)
    bg = np.median(corner, axis=0)
    tol = max(20.0, 2.5 * float(corner.std(axis=0).max()))
    center = bgr[y0:y1, x0:x1].astype(np.float32)
    close = np.abs(center - bg).max(axis=2) <= tol
    return float(close.mean())


def _center_crop(bgr: np.ndarray, ratio: float = 0.7) -> np.ndarray:
    h, w = bgr.shape[:2]
    ch, cw = int(h * ratio), int(w * ratio)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    return bgr[y0 : y0 + ch, x0 : x0 + cw]


# Zero-shot prompts for the optical grader (metal-vs-glass tie-break only).
_METAL_PROMPTS = [
    "a photo of a shiny opaque metal can",
    "an opaque metallic tin",
    "a crumpled aluminium can",
]
_GLASS_PROMPTS = [
    "a photo of a transparent glass jar",
    "see-through clear glass",
    "a clear transparent glass container",
]


class WasteClassifier:
    def __init__(self):
        self.session = None
        self.input_name = None
        self.imagenet = []
        self.rf = None
        self.sample_hashes: list[tuple[np.ndarray, dict]] = []
        self.siglip = None
        self.siglip_processor = None
        self.siglip_labels: list[str] = []
        self._siglip_lock = threading.Lock()
        self.grader = None
        self.grader_processor = None
        self.grader_text = None
        self._grader_lock = threading.Lock()
        self._load_onnx()
        self._load_siglip()
        self._load_grader()
        self._index_samples()
        self._train_rf()

    def _load_grader(self):
        """Base SigLIP2 (image-tower-only use) as a zero-shot metal/glass grader.

        Decorrelated from the two fine-tuned heads: where they consistently
        confuse clear glass with metal, the base model scoring against natural
        language prompts ('transparent glass' vs 'opaque metal') settles it.
        Failure is non-fatal — the tie-break is then skipped.
        """
        try:
            import torch
            from transformers import (
                AutoImageProcessor,
                AutoTokenizer,
                SiglipModel,
            )

            self.grader = SiglipModel.from_pretrained(
                SIGLIP2_GRADER_MODEL, torch_dtype=torch.float32
            ).eval()
            self.grader_processor = AutoImageProcessor.from_pretrained(
                SIGLIP2_GRADER_MODEL
            )
            tok = AutoTokenizer.from_pretrained(SIGLIP2_GRADER_MODEL)
            prompts = _METAL_PROMPTS + _GLASS_PROMPTS
            with torch.no_grad():
                enc = tok(prompts, padding=True, truncation=True, return_tensors="pt")
                out = self.grader.get_text_features(**enc)
            t = out.pooler_output if hasattr(out, "pooler_output") else out
            self.grader_text = torch.nn.functional.normalize(t, dim=-1)
            print(f"[classifier] SigLIP2 optical grader ready: {SIGLIP2_GRADER_MODEL}")
        except Exception as e:
            self.grader = None
            print(
                f"[classifier] SigLIP2 grader unavailable ({e.__class__.__name__}: {e})"
                " — metal/glass tie-break degrades to the transparency metric"
            )

    def _grade_glass_metal(self, bgr: np.ndarray) -> str:
        """'glass' | 'metal' | '' via zero-shot prompt similarity.

        Empty string = no grader, caller falls back to _transparent_frac().
        """
        if self.grader is None:
            return ""
        import torch

        pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        with self._grader_lock:
            with torch.no_grad():
                inputs = self.grader_processor(images=pil, return_tensors="pt")
                if "pixel_values" in inputs:
                    inputs = {"pixel_values": inputs["pixel_values"]}
                out = self.grader.get_image_features(**inputs)
            img = out.pooler_output if hasattr(out, "pooler_output") else out
            img = torch.nn.functional.normalize(img, dim=-1)
            sims = (img @ self.grader_text.T).squeeze(0).tolist()
        n_met, n_gls = len(_METAL_PROMPTS), len(_GLASS_PROMPTS)
        metal = max(sims[:n_met])
        glass = max(sims[n_met : n_met + n_gls])
        return "glass" if glass > metal else "metal"

    def _load_siglip(self):
        """Load the dedicated waste SigLIP2 model.

        First call downloads the weights (~350 MB) into the HF cache; later
        boots are fully offline. Failure never blocks the plant — the cascade
        simply drops back to Roboflow / MobileNetV2 / color-texture RF.
        """
        try:
            import torch
            from transformers import AutoImageProcessor, SiglipForImageClassification

            self.siglip = SiglipForImageClassification.from_pretrained(
                SIGLIP_MODEL, torch_dtype=torch.float32
            ).eval()
            self.siglip_processor = AutoImageProcessor.from_pretrained(SIGLIP_MODEL)
            id2label = getattr(self.siglip.config, "id2label", {})
            self.siglip_labels = [id2label[k] for k in sorted(id2label)]
            print(f"[classifier] SigLIP2 waste model ready: {SIGLIP_MODEL}")
        except Exception as e:
            self.siglip = None
            print(
                f"[classifier] SigLIP2 unavailable ({e.__class__.__name__}: {e})"
                " — RoboFlow / MobileNetV2 / color-texture RF stay in the cascade"
            )

    def _siglip_probs(self, bgr: np.ndarray) -> list[float]:
        """Single SigLIP2 forward pass → softmax vector (called with lock held)."""
        import torch

        pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        inputs = self.siglip_processor(images=pil, return_tensors="pt")
        with torch.no_grad():
            logits = self.siglip(**inputs).logits
        return torch.softmax(logits, dim=-1).squeeze(0).tolist()

    def _siglip(self, bgr: np.ndarray) -> dict | None:
        if self.siglip is None:
            return None
        import torch

        with self._siglip_lock:  # serialize CPU inference across request threads
            probs = self._siglip_probs(bgr)
            # Adaptive TTA: a desk photo with the item far from centre scores
            # weakly on the full frame; a second pass on the centre crop and
            # averaging both stabilises the result. Only paid when needed.
            best = probs.index(max(probs))
            if probs[best] < 0.85:
                crop = self._siglip_probs(_center_crop(bgr))
                probs = [(a + b) / 2.0 for a, b in zip(probs, crop)]
        idx = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)[:5]
        top = []
        for i in idx:
            label = self.siglip_labels[i] if i < len(self.siglip_labels) else str(i)
            top.append(
                {
                    "label": label,
                    "score": round(float(probs[i]), 4),
                    "waste": SIGLIP_TO_WASTE.get(label.lower()),
                }
            )
        best = top[0]
        return {
            "class": SIGLIP_TO_WASTE.get(best["label"].lower(), "residual"),
            "confidence": round(float(best["score"]), 3),
            "backend": f"siglip2:{SIGLIP_MODEL.rsplit('/', 1)[-1]}",
            "imagenet_label": best["label"],
            "top": top,
            "sample": None,
        }

    def _load_onnx(self):
        if not ONNX_PATH.exists():
            return
        import onnxruntime as ort

        self.session = ort.InferenceSession(
            str(ONNX_PATH), providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        if IMAGENET_LABELS.exists():
            self.imagenet = IMAGENET_LABELS.read_text().strip().splitlines()

    def _index_samples(self):
        for s in SAMPLES:
            p = path_for(s)
            if not p.exists():
                continue
            bgr = cv2.imread(str(p))
            if bgr is None:
                continue
            self.sample_hashes.append((_ahash(bgr), s))

    def _train_rf(self):
        X, y = [], []
        for s in SAMPLES:
            p = path_for(s)
            if not p.exists():
                continue
            bgr = cv2.imread(str(p))
            if bgr is None:
                continue
            for aug in _augment(bgr):
                if aug.size == 0:
                    continue
                X.append(_features(aug))
                y.append(s["label"])
        if not X:
            return
        self.rf = RandomForestClassifier(
            n_estimators=120, max_depth=12, random_state=7, n_jobs=1
        )
        self.rf.fit(np.stack(X), y)

    def _match_sample(self, bgr: np.ndarray) -> dict | None:
        h = _ahash(bgr)
        best, dist = None, 999
        for sh, sample in self.sample_hashes:
            d = _hamming(h, sh)
            if d < dist:
                dist, best = d, sample
        if best is not None and dist <= 18:
            return best
        return None

    def _mobilenet(self, bgr: np.ndarray) -> list[dict]:
        if self.session is None:
            return []
        rgb = cv2.cvtColor(cv2.resize(bgr, (224, 224)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], np.float32)
        std = np.array([0.229, 0.224, 0.225], np.float32)
        x = np.transpose((rgb - mean) / std, (2, 0, 1))[None]
        logits = self.session.run(None, {self.input_name: x})[0].ravel()
        e = np.exp(logits - logits.max())
        p = e / e.sum()
        idx = p.argsort()[-5:][::-1]
        top = []
        for i in idx:
            name = self.imagenet[i] if i < len(self.imagenet) else str(i)
            top.append(
                {
                    "label": name,
                    "score": float(p[i]),
                    "waste": _map_imagenet(name),
                }
            )
        return top

    def _rf(self, bgr: np.ndarray) -> tuple[str, float]:
        if self.rf is None:
            return "residual", 0.4
        proba = self.rf.predict_proba(_features(bgr).reshape(1, -1))[0]
        i = int(proba.argmax())
        return str(self.rf.classes_[i]), float(proba[i])

    def _roboflow(self, data: bytes) -> dict | None:
        if not ROBOFLOW_API_KEY:
            return None
        try:
            import json
            import urllib.request

            url = (
                f"https://detect.roboflow.com/{ROBOFLOW_MODEL}"
                f"?api_key={ROBOFLOW_API_KEY}&confidence=30"
            )
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=8) as resp:
                payload = json.loads(resp.read().decode())
            preds = payload.get("predictions") or []
            if not preds:
                return None
            preds = sorted(preds, key=lambda p: p.get("confidence", 0), reverse=True)
            raw = str(preds[0].get("class", "")).lower()
            conf = float(preds[0].get("confidence", 0))
            mapped = "residual"
            for key, label in (
                ("plastic", "plastic"),
                ("bottle", "plastic"),
                ("metal", "metal"),
                ("can", "metal"),
                ("paper", "paper"),
                ("cardboard", "paper"),
                ("glass", "glass"),
                ("organic", "organic"),
                ("food", "organic"),
                ("bio", "organic"),
            ):
                if key in raw:
                    mapped = label
                    break
            return {
                "class": mapped,
                "confidence": conf,
                "backend": f"roboflow:{ROBOFLOW_MODEL}",
                "imagenet_label": raw,
                "top": [{"label": p.get("class"), "score": p.get("confidence"), "waste": None} for p in preds[:5]],
            }
        except Exception:
            return None

    def classify_bgr(self, bgr: np.ndarray, data: bytes | None = None, sample_id: str | None = None) -> dict:
        if sample_id:
            from .samples import by_id

            s = by_id(sample_id)
            if s:
                top = self._mobilenet(bgr)
                return {
                    "class": s["label"],
                    "confidence": 0.97,
                    "backend": f"labeled-sample:{s['id']}",
                    "imagenet_label": top[0]["label"] if top else None,
                    "top": top,
                    "sample": s,
                }

        hit = self._match_sample(bgr)
        if hit:
            top = self._mobilenet(bgr)
            return {
                "class": hit["label"],
                "confidence": 0.95,
                "backend": f"phash:{hit['id']}",
                "imagenet_label": top[0]["label"] if top else None,
                "top": top,
                "sample": hit,
            }

        if data:
            rf = self._roboflow(data)
            if rf and rf["confidence"] >= 0.35:
                return rf

        # YOLO localiser first: classify the detected item crop, not the desk.
        crop, det = detector.locate(bgr)
        view = crop if crop is not None else bgr
        sig = self._siglip(view)
        if sig:
            top1 = sig["confidence"]
            runner = sig["top"][1]["score"] if len(sig["top"]) > 1 else 0.0
            # Waste-specialised head: accept on raw confidence OR a clear
            # top-1/top-2 margin. It must never lose to the color-texture RF.
            if top1 >= SIGLIP_THRESHOLD or (top1 - runner) >= SIGLIP_MARGIN:
                # Metal is opaque; clear glass is not. Both fine-tuned heads
                # confuse transparent glass with metal — settle it optically
                # with the zero-shot grader (transparency metric fallback).
                if sig["class"] == "metal":
                    verdict = self._grade_glass_metal(view)
                    if verdict != "glass" and _transparent_frac(bgr) >= 0.30:
                        verdict = "glass"
                    if verdict == "glass":
                        sig = {
                            **sig,
                            "class": "glass",
                            "confidence": round(max(0.5, top1), 3),
                            "backend": sig["backend"] + "+optical",
                        }
                if det is not None:
                    sig["yolo"] = det
                    prior = det.get("waste_prior")
                    # Weak COCO prior rescues only a weak SigLIP2 verdict
                    # (e.g. an e-waste gadget or a fruit the head never saw).
                    if prior and top1 < 0.5 and prior != sig["class"]:
                        sig = {
                            **sig,
                            "class": prior,
                            "confidence": round(top1 * 0.5 + det["coco_conf"] * 0.5, 3),
                            "backend": sig["backend"] + "+yolo",
                        }
                return sig

        top = self._mobilenet(bgr)
        mapped = next((t for t in top if t["waste"] and t["score"] >= 0.12), None)
        rf_class, rf_conf = self._rf(bgr)

        if mapped and mapped["score"] >= 0.22:
            return {
                "class": mapped["waste"],
                "confidence": round(float(mapped["score"]), 3),
                "backend": "mobilenetv2-imagenet",
                "imagenet_label": mapped["label"],
                "top": top,
                "sample": None,
            }

        return {
            "class": rf_class,
            "confidence": round(rf_conf, 3),
            "backend": "color-texture-rf",
            "imagenet_label": top[0]["label"] if top else None,
            "top": top,
            "sample": None,
        }

    def classify_bytes(self, data: bytes, sample_id: str | None = None) -> dict:
        return self.classify_bgr(_bgr_from_bytes(data), data=data, sample_id=sample_id)

    def classify_path(self, path: Path, sample_id: str | None = None) -> dict:
        data = Path(path).read_bytes()
        return self.classify_bytes(data, sample_id=sample_id)


classifier = WasteClassifier()
