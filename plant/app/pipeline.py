"""One item through the whole plant: vision → sensors → fusion → actuator → log."""
from __future__ import annotations

import uuid
from pathlib import Path

import cv2

from .config import UPLOADS, BINS, TIPS
from . import db
from .classifier import classifier
from .fusion import fuse
from .hardware import hardware
from .samples import by_id, path_for


def _ticket(det_id, visual, sensors, fused, sort, source) -> str:
    bay = fused.get("bay") or BINS["residual"]
    reasons = " | ".join(fused.get("reasons") or [])
    return (
        f"BIN-GENIE SORT TICKET #{det_id:04d}\n"
        f"SRC   {source}\n"
        f"VISION  {visual['class']:<10} {visual['confidence']:.2f}  [{visual['backend']}]\n"
        f"IR      {'PRESENT' if sensors['ir'] else 'CLEAR '}\n"
        f"MOIST   {sensors['moisture']:.0%}\n"
        f"METAL   {'YES' if sensors['metal'] else 'NO'}\n"
        f"FUSED → {bay['id']} {bay['title']}\n"
        f"DISC    {sort['disc_deg']}°   FLAP {sort['flap_deg']}°   T {sort['sort_ms']} ms\n"
        f"HW      {hardware.mode}\n"
        f"NOTE    {reasons}"
    )


def run_bytes(data: bytes, source: str = "upload", sample_id: str | None = None, save: bool = True) -> dict:
    visual = classifier.classify_bytes(data, sample_id=sample_id)
    sensors = hardware.sense_for(visual["class"])
    fused = fuse(visual["class"], sensors)

    image_name = None
    if save:
        image_name = f"{uuid.uuid4().hex[:12]}.jpg"
        (UPLOADS / image_name).write_bytes(data)

    if not fused.get("ok") or not fused.get("bin"):
        row_id = db.insert_detection(
            {
                "ts": db.now_iso(),
                "source": source,
                "visual_class": visual["class"],
                "visual_confidence": visual["confidence"],
                "backend": visual.get("backend"),
                "imagenet_label": visual.get("imagenet_label"),
                "ir": sensors["ir"],
                "moisture": sensors["moisture"],
                "metal": sensors["metal"],
                "fused_bin": "residual",
                "fusion_reason": " | ".join(fused.get("reasons") or ["no object"]),
                "hardware_mode": hardware.mode,
                "sort_ms": 0,
                "disc_deg": 0,
                "image_name": image_name,
            }
        )
        return {
            "id": row_id,
            "ts": db.now_iso(),
            "source": source,
            "visual": visual,
            "sensors": sensors,
            "fusion": fused,
            "hardware": hardware.status(),
            "sort": None,
            "bins": db.get_bins(),
            "ticket": "NO OBJECT ON TRAY — SORT ABORTED",
            "tip": TIPS.get(visual["class"]),
        }

    sort = hardware.sort_to(fused["bin"])
    db.bump_bin(fused["bin"])
    row_id = db.insert_detection(
        {
            "ts": db.now_iso(),
            "source": source,
            "visual_class": visual["class"],
            "visual_confidence": visual["confidence"],
            "backend": visual.get("backend"),
            "imagenet_label": visual.get("imagenet_label"),
            "ir": sensors["ir"],
            "moisture": sensors["moisture"],
            "metal": sensors["metal"],
            "fused_bin": fused["bin"],
            "fusion_reason": " | ".join(fused["reasons"]),
            "hardware_mode": hardware.mode,
            "sort_ms": sort["sort_ms"],
            "disc_deg": sort["disc_deg"],
            "image_name": image_name,
        }
    )
    ticket = _ticket(row_id, visual, sensors, fused, sort, source)
    return {
        "id": row_id,
        "ts": db.now_iso(),
        "source": source,
        "visual": visual,
        "sensors": {**sensors, "simulated": hardware.mode == "simulated"},
        "fusion": fused,
        "hardware": hardware.status(),
        "sort": sort,
        "bins": db.get_bins(),
        "ticket": ticket,
        "tip": fused.get("tip"),
        "co2e_kg": fused.get("co2e_kg"),
    }


def run_sample(sample_id: str, source: str = "sample") -> dict:
    s = by_id(sample_id)
    if not s:
        raise ValueError(f"unknown sample {sample_id}")
    p = path_for(s)
    data = p.read_bytes()
    return run_bytes(data, source=source, sample_id=sample_id, save=False)
