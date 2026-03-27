# 🛰️ Project AETHER — Autonomous Constellation Manager

> **National Space Hackathon 2026** | Indian Institute of Technology, Delhi  
> Orbital Debris Avoidance & Constellation Management System

---

## Overview

Project AETHER (**A**utonomous **E**vasion, **T**racking, **H**euristic **E**ngine for **R**esilient orbits) is a full-stack system that autonomously manages a constellation of 50+ LEO satellites navigating through 10,000+ tracked debris objects. It ingests orbital telemetry, predicts collisions up to 24 hours ahead, plans and executes fuel-optimal evasion maneuvers, and returns satellites to their operational slots — all while respecting real-world constraints like communication blackouts, thruster cooldowns, and finite propellant budgets.

### Key Features

- **J2-perturbed RK4 orbital propagation** — Numba JIT-compiled for 10,000 objects in ~100ms
- **KD-tree conjunction detection** — O(N log N) spatial screening with coarse-then-fine TCA refinement
- **6-gate maneuver validation** — cooldown, LOS, signal delay, fuel, max-ΔV, satellite existence
- **Blind conjunction handling** — pre-uploads evasion sequences before satellite enters blackout
- **Autonomous station-keeping** — drift monitoring, recovery burn scheduling, uptime tracking
- **EOL management** — auto-schedules graveyard orbit at ≤5% fuel
- **3D WebGL dashboard** — Three.js Earth globe with InstancedMesh debris cloud at 60 FPS

---

## Quick Start

### Prerequisites

- [Python 3.11+](https://www.python.org/downloads/)
- [Node.js 20 LTS](https://nodejs.org/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for submission)

### Option A: Docker (Production / Submission)

```bash
docker build -t acm-nsh2026 .
docker run -p 8000:8000 acm-nsh2026
```

Open **http://localhost:8000** — both API and dashboard served on the same port.

### Option B: Local Development (Recommended During Development)

**Terminal 1 — Backend:**
```bash
pip install -r requirements.txt
python scripts/generate_initial_data.py
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Backend: http://localhost:8000  
Frontend: http://localhost:5173 (auto-proxies `/api` to backend)

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/telemetry` | Ingest orbital state vectors for satellites and debris |
| `POST` | `/api/maneuver/schedule` | Schedule an evasion + recovery burn sequence |
| `POST` | `/api/simulate/step` | Advance simulation time by N seconds |
| `GET`  | `/api/visualization/snapshot` | Compressed state for frontend rendering |

### Example: Send Telemetry

```bash
curl -X POST http://localhost:8000/api/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-03-12T08:00:00.000Z",
    "objects": [
      {
        "id": "DEB-99421", "type": "DEBRIS",
        "r": {"x": 4500.2, "y": -2100.5, "z": 4800.1},
        "v": {"x": -1.25, "y": 6.84, "z": 3.12}
      }
    ]
  }'
```

### Example: Advance Simulation 1 Hour

```bash
curl -X POST http://localhost:8000/api/simulate/step \
  -H "Content-Type: application/json" \
  -d '{"step_seconds": 3600}'
```

---

## Project Structure

```
├── Dockerfile                    # ubuntu:22.04 base, exposes port 8000
├── docker-compose.yml            # Optional convenience wrapper
├── requirements.txt              # Python dependencies
├── README.md
│
├── backend/
│   ├── main.py                   # FastAPI app — all 4 API endpoints
│   ├── config.py                 # Physical constants from problem statement
│   ├── models.py                 # Pydantic request/response schemas
│   ├── physics/
│   │   ├── propagator.py         # RK4 + J2 with Numba JIT
│   │   ├── coordinates.py        # ECI ↔ ECEF ↔ Lat/Lon/Alt
│   │   └── maneuver.py           # RTN frame, ΔV planning, Tsiolkovsky
│   ├── engine/
│   │   ├── state_manager.py      # In-memory NumPy state store
│   │   ├── conjunction.py        # KD-tree spatial indexing + TCA search
│   │   ├── scheduler.py          # Constraint-validated maneuver queue
│   │   ├── station_keeping.py    # Slot drift monitoring + recovery
│   │   └── ground_stations.py    # Line-of-sight + visibility windows
│   ├── utils/
│   │   ├── logger.py             # Structured JSON event logging
│   │   └── data_loader.py        # TLE → ECI conversion utilities
│   └── data/
│       └── ground_stations.csv   # 6 ground stations from problem statement
│
├── frontend/
│   ├── package.json              # React 18, Three.js, Recharts, D3
│   ├── vite.config.js            # Vite + API proxy
│   └── src/
│       ├── App.jsx               # Dashboard grid layout
│       ├── components/
│       │   ├── Globe3D.jsx       # 3D Earth + satellites + debris cloud
│       │   ├── BullseyePlot.jsx  # Polar conjunction proximity chart
│       │   ├── FuelHeatmap.jsx   # Fleet propellant status grid
│       │   ├── ManeuverGantt.jsx # Timeline with burns + cooldowns
│       │   ├── CDMList.jsx       # Conjunction warning list
│       │   ├── SatellitePanel.jsx# Selected satellite detail view
│       │   └── StatusBar.jsx     # Header with time + sim controls
│       └── hooks/
│           └── useSnapshot.js    # API polling hook
│
├── scripts/
│   └── generate_initial_data.py  # Generate synthetic test constellation
│
└── docs/
    └── technical_report.tex      # LaTeX technical report
```

---

## Physics & Algorithms

### Orbital Propagation

J2-perturbed two-body equations integrated via RK4 (h = 10s):

```
d²r/dt² = -(μ/|r|³)·r + a_J2

a_J2 = (3/2)·J2·μ·R²_E/|r|⁵ · [x(5z²/r² - 1), y(5z²/r² - 1), z(5z²/r² - 3)]
```

Constants: μ = 398600.4418 km³/s², R_E = 6378.137 km, J₂ = 1.08263×10⁻³

### Conjunction Detection

1. Build KD-tree over debris positions → O(N log N)
2. Query 500 km screening ball per satellite → O(k) candidates
3. Coarse propagation at 60s steps over 24h → find TCA neighborhood
4. Fine refinement at 1s steps in ±120s window → precise TCA and miss distance
5. Classify: CRITICAL (<100m), RED (<1km), YELLOW (<5km)

### Fuel Consumption

Tsiolkovsky equation: `Δm = m_current · (1 - e^(-|ΔV| / (Isp · g₀)))`

Where: Isp = 300s, g₀ = 9.80665 m/s², initial fuel = 50 kg, dry mass = 500 kg

### Maneuver Constraints

| Constraint | Value |
|------------|-------|
| Max ΔV per burn | 15 m/s (0.015 km/s) |
| Thruster cooldown | 600 seconds |
| Signal delay | 10 seconds |
| Station-keeping box | 10 km spherical radius |
| EOL fuel threshold | 5% of initial (2.5 kg) |
| Collision threshold | 100 meters (0.1 km) |

---

## Evaluation Criteria

| Criterion | Weight | Our Approach |
|-----------|--------|-------------|
| Safety Score | 25% | Auto-evasion at 2 km safety margin; blind-conjunction pre-upload |
| Fuel Efficiency | 20% | Transverse burns (most efficient); early detection reduces ΔV |
| Constellation Uptime | 15% | Auto recovery burns; drift monitoring; exponential penalty tracking |
| Algorithmic Speed | 15% | KD-tree O(N log N); Numba parallel propagation; coarse/fine TCA |
| UI/UX & Visualization | 15% | 3D WebGL globe; 60 FPS; all 4 required visualization modules |
| Code Quality & Logging | 10% | Modular architecture; JSON event logs; Pydantic-validated API |

---

## Team

| Name | Role |
|------|------|
| _Member 1_ | Backend Physics Engine |
| _Member 2_ | Conjunction Detection & Maneuver Planning |
| _Member 3_ | Frontend Visualization |
| _Member 4_ | Integration, Docker, Documentation |

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- Indian Institute of Technology, Delhi — for hosting the National Space Hackathon 2026
- NASA/CelesTrak — for public orbital element data
- Three.js / React Three Fiber — for the 3D rendering framework
- SciPy — for spatial indexing algorithms
