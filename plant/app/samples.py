from .config import SAMPLES_DIR

SAMPLES = [
    {
        "id": "plastic_bottle",
        "file": "plastic_bottle.jpg",
        "label": "plastic",
        "name": "PET water bottle",
        "note": "Clear PET, common MRF stream.",
    },
    {
        "id": "plastic_bag",
        "file": "plastic_bag.jpg",
        "label": "plastic",
        "name": "Polythene bag",
        "note": "Film plastic — still routed with hard plastic in this 4-bin layout.",
    },
    {
        "id": "soda_can",
        "file": "soda_can.jpg",
        "label": "metal",
        "name": "Aluminium can",
        "note": "Non-ferrous; inductive coil still flags it.",
    },
    {
        "id": "tin_can",
        "file": "tin_can.jpg",
        "label": "metal",
        "name": "Steel food tin",
        "note": "Ferrous. Metal sensor should go high.",
    },
    {
        "id": "newspaper",
        "file": "newspaper.jpg",
        "label": "paper",
        "name": "Newsprint",
        "note": "Dry fibre. Moisture override will reject it.",
    },
    {
        "id": "cardboard",
        "file": "cardboard.jpg",
        "label": "paper",
        "name": "Corrugated cardboard",
        "note": "Flattened OCC.",
    },
    {
        "id": "glass_bottle",
        "file": "glass_bottle.jpg",
        "label": "glass",
        "name": "Green glass bottle",
        "note": "Cullet stream. Keep ceramics out.",
    },
    {
        "id": "glass_jar",
        "file": "glass_jar.jpg",
        "label": "glass",
        "name": "Glass jar",
        "note": "Clear container glass.",
    },
    {
        "id": "banana_peel",
        "file": "banana_peel.jpg",
        "label": "organic",
        "name": "Banana peel",
        "note": "Wet organic. Moisture sensor expected high.",
    },
    {
        "id": "food_waste",
        "file": "food_waste.jpg",
        "label": "organic",
        "name": "Food scraps",
        "note": "Kitchen waste. Residual / compost bay.",
    },
]


def by_id(sample_id: str) -> dict | None:
    for s in SAMPLES:
        if s["id"] == sample_id:
            return s
    return None


def path_for(sample: dict):
    return SAMPLES_DIR / sample["file"]
