# Project AETHER — Critical Fixes

## How to Apply

Copy each file from this zip to your project root, replacing the existing files:

```bash
# From your project root:
cp fixes/Dockerfile ./Dockerfile
cp fixes/backend/main.py ./backend/main.py
cp fixes/backend/engine/state_manager.py ./backend/engine/state_manager.py
cp fixes/frontend/src/App.jsx ./frontend/src/App.jsx
cp fixes/frontend/src/components/Globe3D.jsx ./frontend/src/components/Globe3D.jsx
cp fixes/frontend/src/components/GroundTrack2D.jsx ./frontend/src/components/GroundTrack2D.jsx
cp fixes/frontend/src/components/FuelHeatmap.jsx ./frontend/src/components/FuelHeatmap.jsx
cp fixes/frontend/src/three/EarthScene.js ./frontend/src/three/EarthScene.js
cp fixes/frontend/src/three/SatelliteMesh.js ./frontend/src/three/SatelliteMesh.js
cp fixes/frontend/src/three/DebrisCloud.js ./frontend/src/three/DebrisCloud.js
cp fixes/frontend/src/three/OrbitLine.js ./frontend/src/three/OrbitLine.js
cp fixes/frontend/src/three/GroundStations.js ./frontend/src/three/GroundStations.js
cp fixes/scripts/download_textures.sh ./scripts/download_textures.sh

# ALSO: Copy your root technical_report.tex to docs/
cp ./technical_report.tex ./docs/technical_report.tex
```

## What Each Fix Does

### 1. Dockerfile (DISQUALIFICATION FIX)
**Problem:** Used `python:3.12-slim` as base image.
**PS says:** "The Dockerfile must use the ubuntu:22.04 image. This is a HARD requirement! If the repository does not use the specified base image, your submission cannot be auto-tested and will be disqualified."
**Fix:** Changed final stage to `FROM ubuntu:22.04`, installed Python via apt.

### 2. backend/main.py (3 CRITICAL FIXES)
**Fix A — Pydantic v2 crash:** `.dict()` → `.model_dump()` in telemetry endpoint. The old `.dict()` is deprecated in Pydantic v2 and will break.
**Fix B — Nominal slot propagation:** Replaced crude velocity approximation (`[-ry, rx, 0]`) with stored actual velocities from `nominal_slot_vels`. This is WHY "NOMINAL: 0" appeared in every screenshot — all satellites were immediately marked OUT_OF_SLOT because the nominal slots were drifting on a different trajectory than the actual satellites.
**Fix C — NumPy serialization:** Added `np_safe()` helper and wrapped ALL return values with explicit `float()` / `int()` casts. FastAPI cannot JSON-serialize `numpy.float64` or `numpy.int64` — it crashes silently.

### 3. backend/engine/state_manager.py (NOMINAL FIX)
**Problem:** No `nominal_slot_vels` dictionary existed.
**Fix:** Added `self.nominal_slot_vels = {}` and populated it during `load_initial_data()` and `update_from_telemetry()` with the satellite's actual velocity at initialization time.

### 4. frontend/src/components/GroundTrack2D.jsx (NEW — PS REQUIRED)
**Problem:** File was completely empty (0 bytes).
**PS says (Section 6.2):** "The 'Ground Track' Map (Mercator Projection): A dynamic 2D world map displaying sub-satellite points. Must feature: real-time location markers, historical trailing path (90 min), dashed predicted trajectory (90 min), dynamic shadow overlay for the Terminator Line."
**Fix:** Full implementation with Mercator projection, satellite markers, 90-min historical trail (solid), 90-min predicted trajectory (dashed), terminator line (day/night boundary), ground station markers, debris overlay, and click-to-select.

### 5. frontend/src/components/Globe3D.jsx (2 FIXES)
**Fix A — DebrisCloud useMemo→useEffect:** `useMemo` runs during render when refs aren't available. Changed to `useEffect` which fires after mount.
**Fix B — InstancedMesh key:** Added `key={count}` to force React to remount the InstancedMesh when debris count changes (Three.js InstancedMesh cannot resize its internal buffer).
**Fix C — Texture paths:** Changed from CDN URLs to local `/textures/` paths (works offline and in Docker).

### 6. frontend/src/App.jsx (VIEW TOGGLE + DATA PASS)
**Fix:** Added 3D/2D view toggle button, integrated GroundTrack2D component, and passes new snapshot fields (`total_collisions_avoided`, `totalFuelConsumed`) to FuelHeatmap for the cost analysis chart.

### 7. frontend/src/components/FuelHeatmap.jsx (PS REQUIRED ADDITION)
**Problem:** PS requires "a ΔV cost analysis graph plotting Fuel Consumed versus Collisions Avoided."
**Fix:** Added SVG scatter plot below the fuel grid showing per-satellite fuel consumption vs estimated evasion count.

### 8. frontend/src/three/*.js (5 EMPTY FILES)
**Problem:** 5 files with 0 bytes cluttering the repo.
**Fix:** Added proper stub content with re-exports pointing to Globe3D.jsx.

### 9. scripts/download_textures.sh (EMPTY FILE)
**Problem:** 0 bytes.
**Fix:** Functional script that downloads Earth textures from CDN.

### 10. docs/technical_report.tex (EMPTY FILE)
**Problem:** 0 bytes in docs/ even though root has the full .tex.
**Fix:** YOU MUST manually copy: `cp ./technical_report.tex ./docs/technical_report.tex`
