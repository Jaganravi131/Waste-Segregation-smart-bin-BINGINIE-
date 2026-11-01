from .config import BINS, VISUAL_TO_BIN, TIPS, CO2E_KG


def fuse(visual_class: str, sensors: dict) -> dict:
    """Combine camera class with IR / moisture / inductive metal.

    This is the bit a viva panel actually wants to hear:
    vision is a prior, sensors are the veto.
    """
    reasons: list[str] = []
    ir = int(sensors.get("ir", 1))
    moisture = float(sensors.get("moisture", 0.0))
    metal = int(sensors.get("metal", 0))

    if not ir:
        reasons.append("IR beam is clear — no object on the tray. Sort aborted.")
        return {
            "bin": None,
            "reasons": reasons,
            "ok": False,
        }

    target = VISUAL_TO_BIN.get(visual_class, "residual")

    if metal:
        if target != "plastic_metal":
            reasons.append(
                "Inductive coil HIGH — vision said "
                f"{visual_class}, metal sensor wins. Divert to PM-01."
            )
        else:
            reasons.append("Inductive coil HIGH — confirms metal / foil in the stream.")
        target = "plastic_metal"

    if moisture >= 0.45:
        if visual_class in ("paper", "organic", "residual", "plastic"):
            reasons.append(
                f"Moisture {moisture:.0%} — wet fibre / organics contaminate dry bays. "
                "Force RS-04 residual."
            )
            target = "residual"
        elif visual_class == "glass":
            reasons.append(
                f"Moisture {moisture:.0%} noted, glass still accepted in GL-03 (containers are rinsed)."
            )
        elif visual_class == "metal":
            reasons.append(
                f"Moisture {moisture:.0%} noted, metal still accepted in PM-01 after drip-off."
            )

    if not reasons:
        bay = BINS[target]
        reasons.append(
            f"Vision class '{visual_class}' maps to {bay['id']} {bay['title']} "
            "and no sensor veto fired."
        )

    return {
        "bin": target,
        "reasons": reasons,
        "ok": True,
        "tip": TIPS.get(visual_class, TIPS["residual"]),
        "co2e_kg": CO2E_KG.get(visual_class, 0.0),
        "bay": BINS[target],
    }
