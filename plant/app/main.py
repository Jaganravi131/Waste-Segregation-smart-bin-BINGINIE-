from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, UPLOADS, BINS, TIPS
from . import db
from .hardware import hardware
from .pipeline import run_bytes, run_sample, probe_bytes
from .samples import SAMPLES

app = FastAPI(title="BIN-GENIE", version="2.0.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")


@app.on_event("startup")
def startup():
    db.init()
    db.seed_history()


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    return {"ok": True, "name": "BIN-GENIE", "version": "2.0.0"}


@app.get("/api/status")
def status():
    return {
        "bins": db.get_bins(),
        "bin_meta": BINS,
        "hardware": hardware.status(),
        "recent": db.recent_detections(12),
        "tips": TIPS,
    }


@app.get("/api/samples")
def samples():
    return [
        {
            **s,
            "url": f"/static/samples/{s['file']}",
            "bin": {
                "plastic": "plastic_metal",
                "metal": "plastic_metal",
                "paper": "paper",
                "glass": "glass",
                "organic": "residual",
            }[s["label"]],
        }
        for s in SAMPLES
        if (ROOT / "static" / "samples" / s["file"]).exists()
    ]


@app.post("/api/classify")
async def classify(
    file: UploadFile | None = File(default=None),
    sample_id: str | None = Form(default=None),
    source: str = Form(default="upload"),
    probe: str = Form(default=""),
):
    try:
        if probe in ("1", "true", "yes"):
            # Live-camera probe: classify the frame without actuating or logging.
            if not file:
                return JSONResponse({"error": "Live probe needs a camera frame"}, status_code=400)
            data = await file.read()
            if not data:
                return JSONResponse({"error": "Empty file"}, status_code=400)
            return probe_bytes(data, source=source or "live")
        if sample_id:
            result = run_sample(sample_id, source=source or "sample")
            return result
        if not file:
            return JSONResponse({"error": "Provide an image or sample_id"}, status_code=400)
        data = await file.read()
        if not data:
            return JSONResponse({"error": "Empty file"}, status_code=400)
        return run_bytes(data, source=source or "upload")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/analytics")
def analytics(days: int = 7):
    return db.analytics(days=max(1, min(days, 60)))


@app.get("/api/detections")
def detections(limit: int = 80):
    return db.recent_detections(limit)


@app.get("/api/export.csv")
def export_csv():
    rows = db.recent_detections(2000)
    cols = [
        "id", "ts", "source", "visual_class", "visual_confidence", "backend",
        "imagenet_label", "ir", "moisture", "metal", "fused_bin",
        "fusion_reason", "hardware_mode", "sort_ms", "disc_deg",
    ]
    lines = [",".join(cols)]
    for r in reversed(rows):
        vals = []
        for c in cols:
            v = r.get(c)
            s = "" if v is None else str(v).replace('"', "'").replace("\n", " ")
            if "," in s:
                s = f'"{s}"'
            vals.append(s)
        lines.append(",".join(vals))
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/csv")


@app.get("/api/hardware")
def hw_status():
    return {**hardware.status(), "ports": hardware.list_ports()}


@app.post("/api/hardware/ping")
def hw_ping():
    return hardware.ping()


@app.post("/api/hardware/connect")
async def hw_connect(port: str = Form(default="sim")):
    return hardware.connect(port)


@app.post("/api/hardware/overrides")
async def hw_overrides(
    ir: str | None = Form(default=None),
    moisture: str | None = Form(default=None),
    metal: str | None = Form(default=None),
    clear: str | None = Form(default=None),
):
    if clear in ("1", "true", "yes"):
        return hardware.set_overrides(clear=True)
    kwargs = {}
    if ir not in (None, ""):
        kwargs["ir"] = int(ir)
    if moisture not in (None, ""):
        kwargs["moisture"] = float(moisture)
    if metal not in (None, ""):
        kwargs["metal"] = int(metal)
    return hardware.set_overrides(**kwargs)


@app.post("/api/facility/reset")
def reset():
    db.reset_facility()
    hardware.set_overrides(clear=True)
    db.seed_history()
    return {"ok": True, "bins": db.get_bins()}


@app.get("/firmware/bin_genie_esp32.ino")
def firmware_file():
    path = ROOT / "firmware" / "bin_genie_esp32" / "bin_genie_esp32.ino"
    return FileResponse(path, filename="bin_genie_esp32.ino")


@app.get("/api/proof/report")
def proof_report():
    rows = [r for r in db.recent_detections(200) if r["source"] in ("proof", "sample", "webcam", "upload")]
    live = [r for r in rows if r["source"] != "seed"]
    bins = db.get_bins()
    html = _render_proof(live, bins)
    return HTMLResponse(html)


def _render_proof(rows: list[dict], bins: dict) -> str:
    items = ""
    for r in rows:
        items += f"""
        <tr>
          <td>{r['id']}</td>
          <td>{r['ts']}</td>
          <td>{r['source']}</td>
          <td>{r['visual_class']} ({r['visual_confidence']:.2f})</td>
          <td>IR {r['ir']} · moist {r['moisture']:.0%} · metal {r['metal']}</td>
          <td>{r['fused_bin']}</td>
          <td>{r['sort_ms']} ms</td>
          <td>{r['hardware_mode']}</td>
        </tr>"""
    bay = "".join(
        f"<li><b>{k}</b> — {v['count']} items, fill {v['fill']:.0f}%</li>"
        for k, v in bins.items()
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>BIN-GENIE proof log</title>
<style>
  body {{ font-family: ui-monospace, monospace; background:#0b120e; color:#d7ead8; margin:40px; }}
  h1 {{ color:#c6f25a; letter-spacing:.08em; }}
  table {{ border-collapse: collapse; width:100%; font-size:12px; }}
  th,td {{ border-bottom:1px solid #244; padding:8px 10px; text-align:left; vertical-align:top; }}
  th {{ color:#7f9a88; font-weight:500; }}
  .stamp {{ color:#7f9a88; }}
</style></head>
<body>
  <h1>BIN-GENIE · PROOF LOG</h1>
  <p class="stamp">Generated from the live SQLite ledger. Seeded demo rows are excluded.</p>
  <ul>{bay}</ul>
  <table>
    <thead><tr><th>#</th><th>Time (IST)</th><th>Source</th><th>Vision</th><th>Sensors</th><th>Fused bay</th><th>Actuate</th><th>HW</th></tr></thead>
    <tbody>{items or '<tr><td colspan="8">No live sorts yet. Run Proof on the dashboard.</td></tr>'}</tbody>
  </table>
</body></html>"""
