# BIN-GENIE · DASHBOARD DESIGN SPEC  v1.0
> Status: **APPROVED PLAN — implementation follows these rules exactly.**
> Scope: the FastAPI control-room SPA (`plant/templates/index.html` + `plant/static/`).
> Brand base: the existing BIN-GENIE plant identity (dark-green control room, lime accent, 4 bay hues).

---

## 1 · BRAND FOUNDATION

| Item | Rule |
|---|---|
| Name | **BIN-GENIE** (always caps, hyphen) |
| Tagline | *Smart Waste Segregation OS* |
| Voice | Control-room, verbs not prose: `SORT`, `PONG`, `HOLD`, `VETO`. Short declaratives. Never cutesy, never IoT-jargon soup |
| Mark | Existing bin mark (`static/img/mark.svg`): rect + disc circle + slot line. 36px in rail, 20px in top-right pills. No recolors |
| Numbers | Sort tickets as `#%04d`. All times 24-h **IST** with `IST` suffix. All angles with `°` |
| Product truth | Never fake "live": every feed shows its true source — `SIMULATED HW` / `SERIAL COM3`, and vision backend (`siglip2:*`, `mobilenetv2`, `phash`) |

### 1.1 Brand voice examples
- Bay title: `PM-01 · PLASTIC / METAL` — not "Your plastic bin"
- Veto message: `Inductive coil HIGH — vision said paper. Metal wins. → PM-01`
- Empty state: `No live sorts yet.` — not "Nothing here 😴"

---

## 2 · COLOR TOKENS (primitive → semantic)

### 2.1 Primitives (from shipped plant colors)

| Token | Hex | Origin |
|---|---|---|
| `bg-0` | `#08110D` | deepest backdrop (demo BG) |
| `bg-1` | `#0B120E` | page background |
| `surface` | `#101C16` | panel (demo PANEL) |
| `surface-2` | `#16241C` | raised panel / hover |
| `line` | `#1E3A2C` | hairline borders (demo LINE) |
| `lime` | `#C6F25A` | brand accent / PM-01 |
| `lime-dim` | `#8FB83A` | accent quiet state |
| `teal` | `#3EE0C5` | secondary accent (vision/AI) |
| `paper-hue` | `#E7D7A3` | PA-02 |
| `glass-blue` | `#7ECBFF` | GL-03 / info |
| `copper` | `#E08A4A` | RS-04 / warning |
| `rose` | `#FF6B5D` | danger / `SORT_ERR` |
| `ink` | `#E7F3EA` | primary text |
| `muted` | `#7F9A88` | secondary text |

### 2.2 Semantic tokens

| Token | Value | Use |
|---|---|---|
| `--bg` | bg-1 | page |
| `--surface` / `--surface-2` | as above | panels / raised |
| `--border` | line @ 60% on `--bg`, line @ 35% inside `--surface` | 1px hairlines |
| `--text` / `--text-muted` | ink / muted | body ≥4.5:1 verified on both surfaces |
| `--accent`, `--accent-dim` | lime, lime-dim | CTA, active nav, focus ring |
| `--ai` | teal | anything classifier-related (backend chip, prob bars) |
| `--ok` / `--warn` / `--danger` / `--info` | lime / copper / rose / glass-blue | status system |
| `--bay-pm`, `--bay-pa`, `--bay-gl`, `--bay-rs` | lime / paper-hue / glass-blue / copper | **only** for bay-coded things |

**Status discipline:** rose = error/aborted only; copper = fusion veto or fill >85%; lime = healthy/`SORT_OK`. Bay color never doubles as status color in discs/labels (letters inherit bay hue, *state* uses status tokens).

---

## 3 · TYPE SYSTEM

| Role | Font | Notes |
|---|---|---|
| Display H (Hero/eye on Plant & Proof) | **Syne 700/800** | keep — it's the brand voice |
| Body/UI | **IBM Plex Sans 400/500/600** | 13–15px |
| Data/telemetry | **IBM Plex Mono 400/500/600** | ALL machine-read values: tickets, TX/RX, angles, `t_ms`, confidences |

Scale (px): display 30 · h2 20 · body 14 · label 12·mono-tight 11 (0.05em tracking, uppercase, muted).
Uppercase + tracking only on kickers/labels; never on body.

---

## 4 · SPACING · SHAPE · ELEVATION · MOTION

- Spacing scale: **4 / 8 / 12 / 16 / 24 / 32** (dashboard density).
- Panel: radius 12, padding 16, `--surface`, 1px `--border`. Inner cards radius 8. Chips radius 999.
- Elevation: `E1 = 0 1px 0 rgba(198,242,90,.06) inset` · `E2 = 0 8px 24px rgba(0,0,0,.35)` for modals/fly-item.
- Glass layer (only on: live camera overlay, nav rail hover sheet, modal scrim): `backdrop-blur(14px)` + `rgba(8,17,13,.55)` + 1px `rgba(255,255,255,.08)`. Text on glass = ink, 4.5:1 measured against video.
- Motion tokens: hover/press `150ms ease`; panel swap `250ms`; disc rotation **`700ms cubic-bezier(.2,.8,.2,1)`** (keep shipped); fly-item `700ms ease` + fade; toast `200ms in / 120ms out`
- Live loop visuals: stability ring fills 50% → 100% per confirmed frame.
- **Reduced motion:** disc jump-cut (0ms), fly-item hidden, only border-flash on target bay; charts render, no animation. `@media (prefers-reduced-motion: reduce)`.

---

## 5 · INFORMATION ARCHITECTURE (5 views, top rail)

```
⌂ PLANT      overview carousel + bays + sensors + latest ticket
▣ SORT       live camera stage · upload · gallery · decision detail
▦ LOG        analytics + ledger
⚡ BAY        hardware bridge · TX/RX console · overrides
✓ PROOF      10-item run + report link
```

Global top strip (every view): `● SIMULATED HW` pill · `AI: SIGLIP2` backend pill (teal) · IST clock. Backend pill reads the last `sort.backend`, dimmed until first sort.

---

## 6 · VIEW-BY-VIEW SPEC

### 6.1 PLANT (overview)
- **Disc stage** (center, SVG keep + upgrades): 4 bays orbit `PM/PA/GL/RS` in bay hues, crosshair slot on top. Under the disc: `ANGLE 0° · FLAP 18° · t=250ms` mono line, updates after each sort.
- **Bay cards row** (4): id/short title, fill bar in bay hue, count. States: **HOT** (target of last sort — lime border + glow), **WARN** fill>85% copper bar, **FULL** fill=100% rose + `SWAP BAG` label.
- **Sensor strip**: 3 gauges (IR present/clear · moisture % + bar · metal hit) with `SIM` tag when simulated.
- **Latest ticket** panel: monospace, copy button, source badge.
- **Sort feed** (right column, 10 rows): `#0021 GLS glass glass_bottle.jpg 14:03:22` clickable → jumps to Log row.

### 6.2 SORT (the flagship view)
Three columns: **camera stage / decision detail / inputs**.

**Camera stage** (16:9, camera fills panel):
- Idle: crosshair + `OPEN CAMERA` center CTA (SVG icon, text ≤ 12px).
- Manual: `● CAPTURE` corner button + `Capture & sort`.
- **LIVE ON:** top-left chip `● LIVE · probe 1.6s`, bottom overlay bar (glass): `metal 100% → PM-01` + probability bar in teal + stability ring (2 ticks) around crosshair; ring completes → disc animates once.
- States: `IDLE → ARMED (camera open) → PROBING → STABLE(2/2) → SORTED → back to PROBING`. Each state visible to the user (chip text), never silent.

**Decision detail**:
1. **Vision card** — winner class, confidence, backend chip, **top-5 SigLIP2 probability bars** (teal; only top-1 labeled text).
2. **Fusion card(s)** — reason strings rendered as verdict lines: green `no veto fired`, copper `metal wins → PM-01`, with before/after chip if vetoed (e.g., `paper ✕ → RS-04`).
3. **Ticket** panel — mono, copy button.

**Inputs column**: Upload drop-zone, calibration gallery (10 tiles, hover lifts 2px → `surface-2`), `Run proof pass`.

### 6.3 LOG
- Stat row: Window / All-time / Recycled % / Residual (4 `StatCard`).
- Charts: doughnut by bay (bay hues), stacked 7-day bar; Chart.js fonts mono 11px, grid `--line` color.
- Ledger table: `# · time · source · visual → LABEL bay · IR/M/M · sort_ms` + new **backend column** (chip). Source chips: `seed` dimmed 60%.

### 6.4 BAY
- Hardware status card: mode pill, port, firmware; `PING` + connect `SIM/COM3…`.
- **TX/RX console** (mono, chat-style): `tx` lines dimmed, `rx` lines ink, `SORT_OK` prefixed with lime `✔`, `SORT_ERR` rose `✕`. Auto-scroll + copy button.
- Overrides: IR toggle, moisture slider (with live label), metal toggle; tiles show simulated plausibility note.
- Wiring cheat-sheet grid (keep).

### 6.5 PROOF
- 10-item run list with inline pass state (`run` pulse → `ok` lime check) + `Open report` (server HTML stays as shipped).

---

## 7 · COMPONENT INVENTORY
`Pill · StatCard · BayCard · GaugeRow · TicketPanel · CamStage(+overlay) · ProbBars · FusionCard · LogConsole · LedgerTable · ChartPanel · GalleryTile · NavRail · Toast` — all implemented in plain CSS/JS matching `style.css` structure (BEM-ish, e.g. `.baycard__bar`).

## 8 · ICONS
Switch emoji glyphs (`⌂ ▣ ▦ ⚡ ✓`) → inline SVG (Heroicons stroke 1.5): home, scan, chart-bar, bolt, check-badge. Rail SVGs inherit `currentColor`.

## 9 · ACCESSIBILITY
- Contrast verified ≥4.5:1 for `--text`/`--text-muted` on both surfaces and glass composite; 3:1 for chips/borders.
- Keyboard: every control focusable; visible focus ring = 2px `--accent` offset 2px; rail = tablist semantics.
- `aria-live="polite"` on toast + live status chip; `SORT_OK` announced as text.
- Confidence/sensors never color-only: text value always beside the bar.
- Touch targets ≥44px, camera buttons ≥48px.

## 10 · RESPONSIVE
- ≥1440: 3-col workspaces, rail 72px.
- 900–1440: decision detail stacks under camera.
- <900: rail → top bar (icons only), Plant/Sensors stack, camera full-width, tables horizontally scrollable (sticky headers).

## 11 · SLIMMER (do NOT change)
- Serial protocol, pipeline order, phash-first calibration, probe→stable→sort logic (just re-skinned), `/api/*`, proof report HTML (light re-style only), ticket number format.

## 12 · IMPLEMENTATION PHASES
| Phase | Deliverable |
|---|---|
| **P1** | tokens.css in `style.css` + top strip (HW / AI / clock) + rail SVGs + panel system |
| **P2** | SORT rebuild: camera stage states, live overlay + stability ring, ProbBars, FusionCard, ticket |
| **P3** | PLANT: bay states (HOT/WARN/FULL), disc telemetry line, feed column |
| **P4** | LOG + BAY + PROOF styling, chart tokens, console styling |
| **P5** | a11y + responsive + reduced-motion pass, dead-CSS purge |
