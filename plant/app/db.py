import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .config import DB_PATH, BINS

IST = timezone(timedelta(hours=5, minutes=30))


def now_iso() -> str:
    return datetime.now(IST).isoformat(timespec="milliseconds")


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                source TEXT NOT NULL,
                visual_class TEXT NOT NULL,
                visual_confidence REAL NOT NULL,
                backend TEXT,
                imagenet_label TEXT,
                ir INTEGER,
                moisture REAL,
                metal INTEGER,
                fused_bin TEXT NOT NULL,
                fusion_reason TEXT,
                hardware_mode TEXT,
                sort_ms INTEGER,
                disc_deg INTEGER,
                image_name TEXT
            );
            CREATE TABLE IF NOT EXISTS bins (
                name TEXT PRIMARY KEY,
                fill REAL NOT NULL,
                count INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proof_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                items INTEGER,
                notes TEXT
            );
            """
        )
        for name in BINS:
            c.execute(
                "INSERT OR IGNORE INTO bins(name, fill, count) VALUES (?,?,?)",
                (name, 8.0, 0),
            )


def insert_detection(row: dict) -> int:
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO detections(
                ts, source, visual_class, visual_confidence, backend, imagenet_label,
                ir, moisture, metal, fused_bin, fusion_reason, hardware_mode,
                sort_ms, disc_deg, image_name
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["ts"],
                row["source"],
                row["visual_class"],
                row["visual_confidence"],
                row.get("backend"),
                row.get("imagenet_label"),
                row.get("ir"),
                row.get("moisture"),
                row.get("metal"),
                row["fused_bin"],
                row.get("fusion_reason"),
                row.get("hardware_mode"),
                row.get("sort_ms"),
                row.get("disc_deg"),
                row.get("image_name"),
            ),
        )
        return int(cur.lastrowid)


def bump_bin(name: str, delta_fill: float = 6.5):
    with conn() as c:
        c.execute(
            "UPDATE bins SET fill = MIN(100.0, fill + ?), count = count + 1 WHERE name = ?",
            (delta_fill, name),
        )


def get_bins() -> dict:
    with conn() as c:
        rows = c.execute("SELECT name, fill, count FROM bins").fetchall()
    out = {}
    for r in rows:
        out[r["name"]] = {"fill": round(r["fill"], 1), "count": r["count"]}
    for name in BINS:
        out.setdefault(name, {"fill": 0.0, "count": 0})
    return out


def reset_facility():
    with conn() as c:
        c.execute("DELETE FROM detections")
        c.execute("DELETE FROM proof_runs")
        c.execute("UPDATE bins SET fill = 8.0, count = 0")


def recent_detections(limit: int = 40) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM detections ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def analytics(days: int = 7) -> dict:
    cutoff = (datetime.now(IST) - timedelta(days=days)).isoformat()
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM detections WHERE ts >= ? ORDER BY ts ASC", (cutoff,)
        ).fetchall()
        totals = c.execute(
            "SELECT COUNT(*) n FROM detections"
        ).fetchone()["n"]
    rows = [dict(r) for r in rows]
    by_bin = {k: 0 for k in BINS}
    by_class = {}
    by_day = {}
    recyclable = 0
    for r in rows:
        by_bin[r["fused_bin"]] = by_bin.get(r["fused_bin"], 0) + 1
        by_class[r["visual_class"]] = by_class.get(r["visual_class"], 0) + 1
        day = (r["ts"] or "")[:10]
        by_day.setdefault(day, {k: 0 for k in BINS})
        by_day[day][r["fused_bin"]] = by_day[day].get(r["fused_bin"], 0) + 1
        if r["fused_bin"] != "residual":
            recyclable += 1
    n = len(rows) or 1
    return {
        "window_days": days,
        "count": len(rows),
        "total_all_time": totals,
        "by_bin": by_bin,
        "by_class": by_class,
        "by_day": by_day,
        "recyclable_pct": round(100.0 * recyclable / n, 1) if rows else 0.0,
        "rows": rows[-200:],
    }


def seed_history():
    """Fill a quiet week of demo traffic so analytics is not an empty chart on first boot."""
    with conn() as c:
        n = c.execute("SELECT COUNT(*) n FROM detections").fetchone()["n"]
        if n > 0:
            return
    import random

    stream = [
        ("plastic", "plastic_metal"),
        ("metal", "plastic_metal"),
        ("paper", "paper"),
        ("glass", "glass"),
        ("organic", "residual"),
        ("plastic", "plastic_metal"),
        ("paper", "paper"),
        ("organic", "residual"),
        ("glass", "glass"),
        ("metal", "plastic_metal"),
    ]
    now = datetime.now(IST)
    i = 0
    for day in range(6, 0, -1):
        items = random.randint(5, 9)
        for k in range(items):
            visual, fused = stream[i % len(stream)]
            i += 1
            ts = now - timedelta(days=day, hours=random.randint(8, 20), minutes=random.randint(0, 59))
            moist = 0.62 if visual == "organic" else random.uniform(0.04, 0.12)
            metal = 1 if visual == "metal" else 0
            insert_detection(
                {
                    "ts": ts.isoformat(timespec="milliseconds"),
                    "source": "seed",
                    "visual_class": visual,
                    "visual_confidence": round(random.uniform(0.78, 0.96), 3),
                    "backend": "seed",
                    "imagenet_label": None,
                    "ir": 1,
                    "moisture": round(moist, 3),
                    "metal": metal,
                    "fused_bin": fused,
                    "fusion_reason": "Seeded facility log (not live).",
                    "hardware_mode": "simulated",
                    "sort_ms": random.randint(900, 1300),
                    "disc_deg": {"plastic_metal": 0, "paper": 90, "glass": 180, "residual": 270}[fused],
                    "image_name": None,
                }
            )
            bump_bin(fused, random.uniform(3.5, 7.0))
