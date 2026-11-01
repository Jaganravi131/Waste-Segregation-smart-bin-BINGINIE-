from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
MODELS = ROOT / "models"
SAMPLES_DIR = ROOT / "static" / "samples"
DB_PATH = DATA / "bingenie.db"
ONNX_PATH = MODELS / "mobilenetv2-12.onnx"
IMAGENET_LABELS = MODELS / "imagenet_classes.txt"

DATA.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)

ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "").strip()
ROBOFLOW_MODEL = os.getenv("ROBOFLOW_MODEL", "garbage-classification-3/2")

# Dedicated waste-texture SigLIP2 classifier (HuggingFace transformers).
# Any SiglipForImageClassification checkpoint works — override with SIGLIP_MODEL.
SIGLIP_MODEL = os.getenv("SIGLIP_MODEL", "prithivMLmods/Augmented-Waste-Classifier-SigLIP2")
# Accept SigLIP2 above this raw top-1 confidence; otherwise a top-1-vs-top-2
# margin of SIGLIP_MARGIN is still accepted (it is a waste-specialised head and
# always stronger than the fallbacks). Keep low so it never loses to RF.
SIGLIP_THRESHOLD = float(os.getenv("SIGLIP_THRESHOLD", "0.25"))
SIGLIP_MARGIN = float(os.getenv("SIGLIP_MARGIN", "0.10"))

# Base (non-fine-tuned) SigLIP2 used only as an optical tie-break grader for
# the metal-vs-glass confusion — zero-shot prompt similarity, decorrelated
# from both fine-tune heads.
SIGLIP2_GRADER_MODEL = os.getenv("SIGLIP2_GRADER_MODEL", "google/siglip2-base-patch16-224")

# Its 10 output classes → BIN-GENIE plant taxonomy. The disc has no e-waste
# bay today, so battery/clothes/shoes/trash land on RS-04 residual.
SIGLIP_TO_WASTE = {
    "battery": "residual",
    "biological": "organic",
    "cardboard": "paper",
    "clothes": "residual",
    "glass": "glass",
    "metal": "metal",
    "paper": "paper",
    "plastic": "plastic",
    "shoes": "residual",
    "trash": "residual",
}

BINS = {
    "plastic_metal": {
        "id": "PM-01",
        "title": "Plastic / Metal",
        "short": "P/M",
        "hue": "#c6f25a",
        "disc": 0,
        "accepts": ["plastic", "metal"],
    },
    "paper": {
        "id": "PA-02",
        "title": "Paper",
        "short": "PAP",
        "hue": "#e7d7a3",
        "disc": 90,
        "accepts": ["paper"],
    },
    "glass": {
        "id": "GL-03",
        "title": "Glass",
        "short": "GLS",
        "hue": "#7ecbff",
        "disc": 180,
        "accepts": ["glass"],
    },
    "residual": {
        "id": "RS-04",
        "title": "Residual",
        "short": "RES",
        "hue": "#e08a4a",
        "disc": 270,
        "accepts": ["organic", "residual"],
    },
}

VISUAL_TO_BIN = {
    "plastic": "plastic_metal",
    "metal": "plastic_metal",
    "paper": "paper",
    "glass": "glass",
    "organic": "residual",
    "residual": "residual",
}

TIPS = {
    "plastic": "Rinse, flatten, keep the cap on. No PVC, no chip packets with foil lining.",
    "metal": "Rinse food tins and drink cans. Steel and aluminium share this chute.",
    "paper": "Dry fibre only. No pizza boxes soaked in grease, no thermal receipts.",
    "glass": "Empty bottles and jars. No broken window pane, no ceramic, no bulbs.",
    "organic": "Food scraps and peels. This stream is wet — it never enters dry recycling.",
    "residual": "Anything the sensors cannot certify. Landfill / RDF, not the recycling bays.",
}

CO2E_KG = {
    "plastic": 1.5,
    "metal": 1.8,
    "paper": 0.9,
    "glass": 0.3,
    "organic": 0.2,
    "residual": 0.0,
}
