const BAY_META = {
  plastic_metal: { id: "PM-01", title: "Plastic / Metal", hue: "#c6f25a", disc: 0 },
  paper:         { id: "PA-02", title: "Paper",           hue: "#e7d7a3", disc: 90 },
  glass:         { id: "GL-03", title: "Glass",           hue: "#7ecbff", disc: 180 },
  residual:      { id: "RS-04", title: "Residual",        hue: "#e08a4a", disc: 270 },
};

const state = {
  view: "facility",
  samples: [],
  last: null,
  charts: {},
  camStream: null,
  moistManual: false,
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._id);
  toast._id = setTimeout(() => (t.hidden = true), 2400);
}

function clock() {
  const d = new Date();
  const ist = new Date(d.getTime() + (5.5 * 60 + d.getTimezoneOffset()) * 60000);
  const pad = (n) => String(n).padStart(2, "0");
  $("#clock").textContent =
    `${pad(ist.getHours())}:${pad(ist.getMinutes())}:${pad(ist.getSeconds())} IST`;
}
setInterval(clock, 1000);
clock();

/* ---------- nav ---------- */
$$(".rail nav button").forEach((b) => {
  b.addEventListener("click", () => show(b.dataset.view));
});
function show(name) {
  state.view = name;
  $$(".rail nav button").forEach((b) => b.classList.toggle("on", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("on", v.id === "view-" + name));
  if (name === "analytics") loadAnalytics();
  if (name === "hardware") loadHardware();
}

/* ---------- plant drawing ---------- */
function drawBays() {
  const g = $("#baysDraw");
  const row = $("#bayRow");
  g.innerHTML = "";
  row.innerHTML = "";
  const keys = Object.keys(BAY_META);
  keys.forEach((k, i) => {
    const m = BAY_META[k];
    const ang = (m.disc - 90) * Math.PI / 180;
    const cx = 210 + Math.cos(ang) * 145;
    const cy = 210 + Math.sin(ang) * 145;
    const el = document.createElementNS("http://www.w3.org/2000/svg", "g");
    el.innerHTML = `
      <rect x="${cx - 36}" y="${cy - 22}" width="72" height="44" rx="8"
            fill="#0b1511" stroke="${m.hue}" stroke-width="1.6"/>
      <text x="${cx}" y="${cy - 4}" text-anchor="middle" fill="${m.hue}"
            font-size="9" font-family="IBM Plex Mono">${m.id}</text>
      <text x="${cx}" y="${cy + 12}" text-anchor="middle" fill="#e7f3ea"
            font-size="9" font-family="IBM Plex Sans">${m.title}</text>`;
    g.appendChild(el);

    const card = document.createElement("div");
    card.className = "bay";
    card.id = "bay-" + k;
    card.innerHTML = `
      <div class="id">${m.id}</div>
      <div class="title">${m.title}</div>
      <div class="fill"><i id="fill-${k}" style="background:${m.hue}"></i></div>
      <div class="n" id="count-${k}">0 items · 0%</div>`;
    row.appendChild(card);
  });
}
drawBays();

function setDisc(deg, flap = 0) {
  const rotor = $("#discRotor");
  rotor.style.transition = "transform .7s cubic-bezier(.2,.8,.2,1)";
  rotor.style.transform = `rotate(${deg}deg)`;
  const arm = $("#flapArm");
  arm.style.opacity = flap ? 1 : 0.45;
}

function applyBins(bins) {
  if (!bins) return;
  for (const [k, v] of Object.entries(bins)) {
    const bar = $("#fill-" + k);
    const n = $("#count-" + k);
    if (bar) bar.style.width = Math.min(100, v.fill) + "%";
    if (n) n.textContent = `${v.count} items · ${v.fill.toFixed(0)}%`;
  }
}

function applySensors(s) {
  if (!s) return;
  const ir = $("#gIr");
  ir.textContent = s.ir ? "PRESENT" : "CLEAR";
  ir.parentElement.classList.toggle("on", !!s.ir);
  $("#gMoist").textContent = Math.round(s.moisture * 100) + "%";
  $("#gMoistBar").style.width = Math.round(s.moisture * 100) + "%";
  const metal = $("#gMetal");
  metal.textContent = s.metal ? "METAL HIT" : "NO METAL";
  metal.parentElement.classList.toggle("on", !!s.metal);
}

function applyHardware(hw) {
  if (!hw) return;
  const pill = $("#hwPill");
  const sim = hw.mode !== "serial";
  pill.innerHTML = `<span class="dot live"></span> ${sim ? "SIMULATED HW" : "SERIAL " + (hw.port || "")}`;
  const st = $("#hwState");
  if (st) st.textContent = `mode=${hw.mode}  port=${hw.port || "sim://bin-genie"}  fw=${hw.firmware}`;
  const log = $("#txrx");
  if (log && hw.log) {
    log.textContent = hw.log.map((l) => `${l.t}  ${l.dir.toUpperCase()}  ${l.text}`).join("\n") || "Waiting for traffic.";
    log.scrollTop = log.scrollHeight;
  }
}

function applyLedger(rows) {
  const ul = $("#ledger");
  if (!ul) return;
  ul.innerHTML = (rows || []).slice(0, 10).map((r) => {
    const bay = BAY_META[r.fused_bin];
    return `<li><b>${bay ? bay.id : r.fused_bin}</b> · ${r.visual_class} · ${r.source} · ${String(r.ts).slice(11, 19)}</li>`;
  }).join("") || "<li>No live sorts yet.</li>";
}

function highlightBay(key) {
  $$(".bay").forEach((b) => b.classList.remove("hot"));
  const el = $("#bay-" + key);
  if (el) el.classList.add("hot");
}

function playSort(result) {
  state.last = result;
  if (result.ticket) $("#ticket").textContent = result.ticket;
  applySensors(result.sensors);
  applyBins(result.bins);
  applyHardware(result.hardware);
  const bin = result.fusion && result.fusion.bin;
  if (bin && BAY_META[bin]) {
    highlightBay(bin);
    setDisc(BAY_META[bin].disc, 18);
    const fly = $("#flyingItem");
    fly.hidden = false;
    fly.style.background = BAY_META[bin].hue;
    fly.style.transition = "none";
    fly.style.transform = "translate(-50%,-50%) scale(1)";
    requestAnimationFrame(() => {
      const ang = (BAY_META[bin].disc - 90) * Math.PI / 180;
      const x = Math.cos(ang) * 120;
      const y = Math.sin(ang) * 120;
      fly.style.transition = "transform .7s ease";
      fly.style.transform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px)) scale(.4)`;
    });
    setTimeout(() => { fly.hidden = true; }, 800);
  }
}

/* ---------- api ---------- */
async function api(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.error || msg; } catch {}
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/json")) return r.json();
  return r.text();
}

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    applyBins(s.bins);
    applyHardware(s.hardware);
    applySensors(s.hardware.sensors);
    applyLedger(s.recent);
    if (s.hardware.last_sort && BAY_META[s.hardware.last_sort.bin]) {
      setDisc(s.hardware.last_sort.disc_deg, s.hardware.last_sort.flap_deg);
    }
  } catch (e) {
    console.warn(e);
  }
}

async function classifySample(id, source = "sample") {
  const fd = new FormData();
  fd.append("sample_id", id);
  fd.append("source", source);
  const res = await api("/api/classify", { method: "POST", body: fd });
  playSort(res);
  return res;
}

async function classifyFile(file, source = "upload") {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("source", source);
  const res = await api("/api/classify", { method: "POST", body: fd });
  playSort(res);
  toast(`${res.visual.class} → ${BAY_META[res.fusion.bin]?.id || "—"}`);
  return res;
}

/* ---------- gallery / drop ---------- */
async function loadSamples() {
  state.samples = await api("/api/samples");
  const g = $("#gallery");
  g.innerHTML = state.samples.map((s) => `
    <button data-id="${s.id}">
      <img src="${s.url}" alt="${s.name}" />
      <span>${s.name}</span>
    </button>`).join("");
  g.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      try { await classifySample(b.dataset.id); toast("Sorted " + b.dataset.id); }
      catch (e) { toast(e.message); }
      b.disabled = false;
    });
  });
  $("#proofList").innerHTML = state.samples.map((s) =>
    `<li data-id="${s.id}">${s.name} — waiting</li>`
  ).join("");
}

const drop = $("#drop");
const file = $("#file");
drop.addEventListener("click", () => file.click());
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  const f = e.dataTransfer.files[0];
  if (f) handleFile(f);
});
file.addEventListener("change", () => { if (file.files[0]) handleFile(file.files[0]); });

function handleFile(f) {
  const img = $("#preview");
  img.src = URL.createObjectURL(f);
  img.hidden = false;
  classifyFile(f, "upload");
}

$$(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.remove("on"));
    t.classList.add("on");
    $$(".tabbody").forEach((b) => b.classList.remove("on"));
    $("#tab-" + t.dataset.tab).classList.add("on");
  });
});

$("#btnCam").addEventListener("click", async () => {
  try {
    state.camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    $("#cam").srcObject = state.camStream;
  } catch (e) {
    toast("Camera blocked — use upload instead");
  }
});
$("#btnSnap").addEventListener("click", async () => {
  const v = $("#cam");
  if (!v.srcObject) {
    toast("Open the camera first");
    return;
  }
  const c = document.createElement("canvas");
  c.width = v.videoWidth || 640;
  c.height = v.videoHeight || 480;
  c.getContext("2d").drawImage(v, 0, 0);
  c.toBlob(async (blob) => {
    const f = new File([blob], "webcam.jpg", { type: "image/jpeg" });
    $("#preview").src = URL.createObjectURL(f);
    $("#preview").hidden = false;
    try { await classifyFile(f, "webcam"); }
    catch (err) { toast(err.message); }
  }, "image/jpeg", 0.9);
});

/* ---------- proof ---------- */
async function runProof() {
  show("proof");
  const items = state.samples;
  const lis = $$("#proofList li");
  const btn = $("#btnProof");
  btn.disabled = true;
  for (let i = 0; i < items.length; i++) {
    lis[i].className = "run";
    lis[i].textContent = `${items[i].name} — sorting…`;
    try {
      const res = await classifySample(items[i].id, "proof");
      const bay = BAY_META[res.fusion.bin];
      lis[i].className = "ok";
      lis[i].textContent =
        `${items[i].name} → ${res.visual.class} → ${bay.id}  (${res.sort.sort_ms} ms, ${res.hardware.mode})`;
    } catch (e) {
      lis[i].textContent = `${items[i].name} — FAIL ${e.message}`;
    }
    await new Promise((r) => setTimeout(r, 450));
  }
  btn.disabled = false;
  toast("Proof run complete — open the report");
}
$("#btnProof").addEventListener("click", runProof);
$("#btnProofLite").addEventListener("click", runProof);

/* ---------- analytics ---------- */
async function loadAnalytics() {
  const a = await api("/api/analytics?days=7");
  const recyc = a.recyclable_pct;
  $("#statsRow").innerHTML = `
    <div class="stat"><span>Window</span><b>${a.count}</b></div>
    <div class="stat"><span>All-time</span><b>${a.total_all_time}</b></div>
    <div class="stat"><span>Recycled</span><b>${recyc}%</b></div>
    <div class="stat"><span>Residual</span><b>${a.by_bin.residual || 0}</b></div>`;

  const tbody = $("#tbody");
  tbody.innerHTML = (a.rows || []).slice().reverse().map((r) => `
    <tr>
      <td>${r.id}</td>
      <td>${String(r.ts).replace("T", " ").slice(0, 19)}</td>
      <td>${r.source}</td>
      <td>${r.visual_class} ${Number(r.visual_confidence).toFixed(2)}</td>
      <td>IR ${r.ir} · ${Math.round(r.moisture * 100)}% · M${r.metal}</td>
      <td>${r.fused_bin}</td>
      <td>${r.sort_ms}</td>
    </tr>`).join("");

  const labels = Object.keys(BAY_META);
  const colors = labels.map((k) => BAY_META[k].hue);
  const dataBin = labels.map((k) => a.by_bin[k] || 0);
  paint("chartBin", "doughnut", labels.map((k) => BAY_META[k].id), dataBin, colors, false);

  const days = Object.keys(a.by_day).sort();
  paint("chartDay", "bar", days.map((d) => d.slice(5)), null, colors, true, {
    labels: days.map((d) => d.slice(5)),
    datasets: labels.map((k) => ({
      label: BAY_META[k].id,
      data: days.map((d) => a.by_day[d][k] || 0),
      backgroundColor: BAY_META[k].hue,
      stack: "s",
    })),
  });
}

function paint(id, type, labels, data, colors, stacked, ready) {
  const ctx = document.getElementById(id);
  if (!ctx || typeof Chart === "undefined") return;
  if (state.charts[id]) state.charts[id].destroy();
  const cfg = ready || {
    labels,
    datasets: [{ data, backgroundColor: colors, borderWidth: 0 }],
  };
  state.charts[id] = new Chart(ctx, {
    type,
    data: cfg,
    options: {
      plugins: { legend: { labels: { color: "#7f9a88", boxWidth: 10 } } },
      scales: type === "bar" ? {
        x: { stacked, ticks: { color: "#7f9a88" }, grid: { color: "#1e3a2c" } },
        y: { stacked, ticks: { color: "#7f9a88" }, grid: { color: "#1e3a2c" } },
      } : undefined,
    },
  });
}

$("#btnReset").addEventListener("click", async () => {
  if (!confirm("Clear live + seed logs and reset fill levels?")) return;
  await api("/api/facility/reset", { method: "POST" });
  await refreshStatus();
  await loadAnalytics();
  toast("Facility reset");
});

/* ---------- hardware ---------- */
async function loadHardware() {
  const h = await api("/api/hardware");
  applyHardware(h);
  const box = $("#wiring");
  box.innerHTML = `
    <div><b>GPIO 18</b>Servo flap</div>
    <div><b>GPIO 19 / 21</b>Disc STEP / DIR</div>
    <div><b>GPIO 32</b>IR tray (active LOW)</div>
    <div><b>GPIO 34</b>Moisture analog</div>
    <div><b>GPIO 35</b>Inductive metal</div>
    <div><b>GPIO 25–27, 14</b>Bay LEDs</div>
    <div><b>115200 8N1</b>SORT / PING / STATUS</div>
    <div><b>Angles</b>0° 90° 180° 270°</div>`;
}

$("#btnConnect").addEventListener("click", async () => {
  const fd = new FormData();
  fd.append("port", $("#port").value || "sim");
  const h = await api("/api/hardware/connect", { method: "POST", body: fd });
  applyHardware(h);
  toast(h.error ? h.error : "Bridge updated");
});
$("#btnPing").addEventListener("click", async () => {
  applyHardware(await api("/api/hardware/ping", { method: "POST" }));
});
$("#ovMoist").addEventListener("input", () => {
  state.moistManual = true;
  $("#ovMoistLab").textContent = $("#ovMoist").value + "%";
});
$("#btnOvApply").addEventListener("click", async () => {
  const fd = new FormData();
  fd.append("ir", $("#ovIr").checked ? "1" : "0");
  fd.append("metal", $("#ovMetal").checked ? "1" : "0");
  if (state.moistManual) fd.append("moisture", String(Number($("#ovMoist").value) / 100));
  applyHardware(await api("/api/hardware/overrides", { method: "POST", body: fd }));
  toast("Overrides on — sort a sample to see the veto");
});
$("#btnOvClear").addEventListener("click", async () => {
  const fd = new FormData();
  fd.append("clear", "1");
  state.moistManual = false;
  $("#ovMoistLab").textContent = "auto";
  applyHardware(await api("/api/hardware/overrides", { method: "POST", body: fd }));
  toast("Overrides cleared");
});

/* ---------- boot ---------- */
loadSamples().then(refreshStatus);
setInterval(refreshStatus, 4000);
show("facility");
