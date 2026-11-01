"""Hardware bridge.

The dashboard always talks to this module. In SIMULATED mode the ESP32
protocol is spoken against an in-memory device so the UI, logs, and
proof report look identical to a live serial session.

Plug in a board flashed with firmware/bin_genie_esp32 and call
connect(port) — same verbs, same parser.
"""
from __future__ import annotations

import random
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from .config import BINS, VISUAL_TO_BIN

IST = timezone(timedelta(hours=5, minutes=30))


def _ts() -> str:
    return datetime.now(IST).strftime("%H:%M:%S.%f")[:-3]


class Hardware:
    def __init__(self):
        self.mode = "simulated"  # simulated | serial
        self.port = None
        self.serial = None
        self.log = deque(maxlen=80)
        self.overrides = {"ir": None, "moisture": None, "metal": None}
        self.last_sensors = {"ir": 0, "moisture": 0.04, "metal": 0}
        self.last_sort = None
        self.connected = True  # simulator is always up

    def _line(self, direction: str, text: str):
        entry = {"t": _ts(), "dir": direction, "text": text}
        self.log.append(entry)
        return entry

    def status(self) -> dict:
        return {
            "mode": self.mode,
            "connected": self.connected,
            "port": self.port or "sim://bin-genie",
            "firmware": "1.0.0-sim" if self.mode == "simulated" else "1.0.0",
            "overrides": self.overrides,
            "sensors": self.last_sensors,
            "last_sort": self.last_sort,
            "log": list(self.log)[-40:],
        }

    def set_overrides(self, ir=None, moisture=None, metal=None, clear: bool = False):
        if clear:
            self.overrides = {"ir": None, "moisture": None, "metal": None}
            return self.status()
        if ir is not None:
            self.overrides["ir"] = int(ir)
        if moisture is not None:
            self.overrides["moisture"] = float(moisture)
        if metal is not None:
            self.overrides["metal"] = int(metal)
        return self.status()

    def sense_for(self, visual_class: str) -> dict:
        """Produce a sensor snapshot that is physically plausible for this item.

        Overrides from the Hardware panel always win — that is how you
        demonstrate fusion (wet paper, hidden metal, empty tray).
        """
        base = {
            "plastic": {"ir": 1, "moisture": 0.06, "metal": 0},
            "metal": {"ir": 1, "moisture": 0.05, "metal": 1},
            "paper": {"ir": 1, "moisture": 0.08, "metal": 0},
            "glass": {"ir": 1, "moisture": 0.05, "metal": 0},
            "organic": {"ir": 1, "moisture": 0.74, "metal": 0},
            "residual": {"ir": 1, "moisture": 0.33, "metal": 0},
        }.get(visual_class, {"ir": 1, "moisture": 0.1, "metal": 0})
        # tiny jitter so the gauges are alive
        base["moisture"] = max(0.0, min(1.0, base["moisture"] + random.uniform(-0.02, 0.02)))
        for k in ("ir", "moisture", "metal"):
            if self.overrides.get(k) is not None:
                base[k] = self.overrides[k]
        self.last_sensors = {
            "ir": int(base["ir"]),
            "moisture": round(float(base["moisture"]), 3),
            "metal": int(base["metal"]),
        }
        self._line(
            "rx",
            f"SENSORS ir={self.last_sensors['ir']} "
            f"moist={self.last_sensors['moisture']:.2f} "
            f"metal={self.last_sensors['metal']}",
        )
        return dict(self.last_sensors)

    def sort_to(self, bin_key: str) -> dict:
        bay = BINS[bin_key]
        self._line("tx", f"SORT {bin_key}")
        t0 = time.time()
        if self.mode == "serial" and self.serial:
            try:
                self.serial.write(f"SORT {bin_key}\n".encode())
                deadline = time.time() + 4
                rx = ""
                while time.time() < deadline:
                    line = self.serial.readline().decode(errors="ignore").strip()
                    if line:
                        self._line("rx", line)
                        rx = line
                        if line.startswith("SORT_OK"):
                            break
                sort_ms = int((time.time() - t0) * 1000)
            except Exception as e:
                sort_ms = int((time.time() - t0) * 1000)
                rx = f"SORT_ERR reason={e}"
                self._line("rx", rx)
        else:
            # disc travel: 0.35s per 90°
            travel = abs(bay["disc"] - (self.last_sort["disc_deg"] if self.last_sort else 0))
            time.sleep(0.25 + (travel / 90) * 0.18)
            sort_ms = int((time.time() - t0) * 1000)
            rx = f"SORT_OK bin={bin_key} t_ms={sort_ms} disc={bay['disc']} flap=18"
            self._line("rx", rx)
        self.last_sort = {
            "bin": bin_key,
            "disc_deg": bay["disc"],
            "flap_deg": 18,
            "sort_ms": sort_ms,
            "rx": rx,
        }
        return self.last_sort

    def ping(self) -> dict:
        self._line("tx", "PING")
        if self.mode == "serial" and self.serial:
            try:
                self.serial.write(b"PING\n")
                line = self.serial.readline().decode(errors="ignore").strip()
                self._line("rx", line or "PONG")
            except Exception as e:
                self._line("rx", f"ERR {e}")
        else:
            self._line("rx", "PONG firmware=1.0.0-sim mode=simulated")
        return self.status()

    def list_ports(self) -> list[str]:
        try:
            from serial.tools import list_ports

            return [p.device for p in list_ports.comports()]
        except Exception:
            return []

    def connect(self, port: str | None):
        if not port or port in ("sim", "simulated", "sim://bin-genie"):
            self.disconnect()
            self.mode = "simulated"
            self.connected = True
            self.port = None
            self._line("rx", "PONG firmware=1.0.0-sim mode=simulated")
            return self.status()
        try:
            import serial

            ser = serial.Serial(port, 115200, timeout=1)
            time.sleep(1.5)
            self.serial = ser
            self.port = port
            self.mode = "serial"
            self.connected = True
            self._line("tx", "PING")
            ser.write(b"PING\n")
            line = ser.readline().decode(errors="ignore").strip()
            self._line("rx", line or "PONG")
            return self.status()
        except Exception as e:
            self.mode = "simulated"
            self.connected = True
            self.serial = None
            self._line("rx", f"SERIAL_FAIL {e} — staying on simulator")
            return {**self.status(), "error": str(e)}

    def disconnect(self):
        if self.serial:
            try:
                self.serial.close()
            except Exception:
                pass
        self.serial = None
        self.mode = "simulated"
        self.port = None
        self.connected = True


hardware = Hardware()
