"""YOLO object localiser that feeds the vision cascade.

The SigLIP2 head classifies a *close-up* well but a desk webcam frame poorly
(item small in frame, desk background diluting the result). A COCO-trained
YOLOv8 fixes both: crop the detected item for the classifier, and surface a
COCO prior (e.g. `cell phone` / `remote` → e-waste residual) that the waste
taxonomy alone cannot express.
"""
from __future__ import annotations

import numpy as np

from .config import YOLO_ENABLE, YOLO_MODEL, YOLO_CONF

# COCO classes that map onto the BIN-GENIE taxonomy. Classes are weak priors:
# they never override a confident SigLIP2 verdict, they only annotate it and
# rescue a weak one.
COCO_TO_WASTE = {
    "bottle": "plastic",
    "wine glass": "glass",
    "cup": "plastic",
    "banana": "organic",
    "apple": "organic",
    "orange": "organic",
    "carrot": "organic",
    "broccoli": "organic",
    "sandwich": "organic",
    "hot dog": "organic",
    "donut": "organic",
    "cake": "organic",
    "book": "paper",
    "vase": "glass",
    "toothbrush": "plastic",
    "cell phone": "residual",
    "remote": "residual",
    "laptop": "residual",
    "keyboard": "residual",
    "mouse": "residual",
    "tv": "residual",
    "microwave": "residual",
    "oven": "residual",
    "toaster": "residual",
    "refrigerator": "residual",
    "clock": "residual",
    "scissors": "residual",
    "umbrella": "residual",
    "teddy bear": "residual",
    "hair drier": "residual",
}

# Background classes: not waste, never crop on these.
_IGNORE = {
    "person", "chair", "couch", "bed", "dining table", "potted plant",
    "tv stand", "toilet", "door", "window", "wall", "floor", "ceiling",
}


class Detector:
    def __init__(self):
        self.model = None
        if YOLO_ENABLE:
            self._load()

    def _load(self):
        try:
            from ultralytics import YOLO

            self.model = YOLO(YOLO_MODEL)
            print(f"[detector] YOLO localiser ready: {YOLO_MODEL}")
        except Exception as e:
            self.model = None
            print(
                f"[detector] YOLO unavailable ({e.__class__.__name__}: {e})"
                " — SigLIP2 runs on the full frame instead"
            )

    def locate(self, bgr: np.ndarray) -> tuple[np.ndarray | None, dict | None]:
        """Return (item crop, detection info) or (None, None) to use full frame."""
        if self.model is None:
            return None, None
        try:
            result = self.model(bgr, verbose=False)[0]
        except Exception:
            return None, None
        if result.boxes is None or len(result.boxes) == 0:
            return None, None
        names = self.model.names
        best = None
        for box in result.boxes:
            cls = names[int(box.cls)]
            conf = float(box.conf)
            if cls in _IGNORE or conf < YOLO_CONF:
                continue
            if best is None or conf > best[0]:
                best = (conf, cls, [int(v) for v in box.xyxy[0]])
        if best is None:
            return None, None
        conf, cls, (x1, y1, x2, y2) = best
        h, w = bgr.shape[:2]
        px = int((x2 - x1) * 0.12)
        py = int((y2 - y1) * 0.12)
        x1, y1 = max(0, x1 - px), max(0, y1 - py)
        x2, y2 = min(w, x2 + px), min(h, y2 + py)
        if x2 - x1 < 16 or y2 - y1 < 16:
            return None, None
        info = {
            "coco": cls,
            "coco_conf": round(conf, 3),
            "box": [x1, y1, x2, y2],
            "waste_prior": COCO_TO_WASTE.get(cls),
        }
        return bgr[y1:y2, x1:x2], info


detector = Detector()
