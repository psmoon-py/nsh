"""
FastAPI application — Autonomous Constellation Manager API.
Exposes all endpoints on port 8000 as required by the problem statement.

UPDATED: Now integrates all engine modules:
  - GroundStationNetwork for LOS validation
  - ManeuverScheduler for constraint-enforced burn queuing
  - StationKeepingManager for slot drift monitoring
  - ACMLogger for structured event logging
"""
import os
import numpy as np
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.models import (
    TelemetryInput, TelemetryResponse,
    ManeuverInput, ManeuverResponse,
    SimulateStepInput, SimulateStepResponse,
)
from backend.config import (
    RK4_TIMESTEP, COLLISION_THRESHOLD, SIGNAL_DELAY,
)
from backend.engine.state_manager import StateManager
from backend.engine.conjunction import ConjunctionDetector
from backend.engine.ground_stations import GroundStationNetwork
from backend.engine.scheduler import ManeuverScheduler, ManeuverCommand
from backend.engine.station_keeping import StationKeepingManager
from backend.physics.propagator import propagate_batch
from backend.physics.coordinates import eci_to_lla
from backend.physics.maneuver import compute_fuel_consumed
from backend.utils.logger import logger

# ══════════════════════════════════════════════════════════
# Initialize application
# ══════════════════════════════════════════════════════════

app = FastAPI(title="ACM — Autonomous Constellation Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Core engine components ──
sm = StateManager()
cd = ConjunctionDetector(sm)
gn = GroundStationNetwork()
scheduler = ManeuverScheduler(sm, gn)
sk = StationKeepingManager(sm, scheduler)

# ── Load ground stations ──
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
gs_csv = os.path.join(DATA_DIR, "ground_stations.csv")
if os.path.exists(gs_csv):
    gn.load_from_csv(gs_csv)
else:
    gn.load_defaults()

# ── Load initial satellite and debris data ──
sat_file = os.path.join(DATA_DIR, "satellites_init.json")
deb_file = os.path.join(DATA_DIR, "debris_init.json")
if os.path.exists(sat_file) and os.path.exists(deb_file):
    sm.load_initial_data(sat_file, deb_file)
    logger.telemetry_ingested(
        len(sm.ids), 0, sm.timestamp.isoformat()
    )


# ══════════════════════════════════════════════════════════
# POST /api/telemetry
# ══════════════════════════════════════════════════════════

@app.post("/api/telemetry", response_model=TelemetryResponse)
async def ingest_telemetry(data: TelemetryInput):
    """Ingest orbital state vectors for satellites and debris."""

    # 1. Update internal state
    sm.update_from_telemetry(data.timestamp, [obj.dict() for obj in data.objects])

    # 2. Run conjunction assessment
    cdm_warnings = cd.run_full_assessment()
    sm.active_cdms = cdm_warnings

    # 3. Log CDMs
    for cdm in cdm_warnings:
        logger.conjunction_detected(
            cdm["sat_id"], cdm["deb_id"],
            cdm["tca_seconds"], cdm["miss_distance_km"], cdm["risk_level"],
        )

    # 4. Auto-schedule evasion for CRITICAL conjunctions
    for cdm in cdm_warnings:
        if cdm["risk_level"] == "CRITICAL":
            evasion_cmd = scheduler.auto_schedule_evasion(cdm)
            if evasion_cmd:
                logger.maneuver_scheduled(
                    evasion_cmd.sat_id, evasion_cmd.burn_id,
                    evasion_cmd.burn_type, evasion_cmd.delta_v_magnitude_ms,
                    evasion_cmd.burn_time,
                )

    # 5. Check for EOL satellites
    scheduler.check_and_schedule_eol()

    logger.telemetry_ingested(
        len(data.objects), len(cdm_warnings), data.timestamp
    )

    return TelemetryResponse(
        status="ACK",
        processed_count=len(data.objects),
        active_cdm_warnings=len(cdm_warnings),
    )


# ══════════════════════════════════════════════════════════
# POST /api/maneuver/schedule
# ══════════════════════════════════════════════════════════

@app.post("/api/maneuver/schedule", response_model=ManeuverResponse)
async def schedule_maneuver(data: ManeuverInput):
    """Schedule a maneuver sequence for a satellite.

    Validates:
      - Satellite exists
      - Sufficient fuel (Tsiolkovsky)
      - Ground station LOS at upload time
      - 600s cooldown between burns
      - Max ΔV per burn ≤ 15 m/s
      - Signal delay (burn ≥ now + 10s)
    """
    sat_id = data.satelliteId

    if sat_id not in sm.objects:
        return ManeuverResponse(
            status="REJECTED",
            validation={"error": f"Satellite {sat_id} not found"},
        )

    # Use the scheduler to validate and queue the entire sequence
    burns = []
    for burn in data.maneuver_sequence:
        burns.append({
            "burn_id": burn.burn_id,
            "burnTime": burn.burnTime,
            "deltaV_vector": {
                "x": burn.deltaV_vector.x,
                "y": burn.deltaV_vector.y,
                "z": burn.deltaV_vector.z,
            },
            "type": "EVASION" if "EVASION" in burn.burn_id.upper() else "RECOVERY",
        })

    success, msg, validation = scheduler.schedule_sequence(sat_id, burns)

    if success:
        for burn in data.maneuver_sequence:
            dv = np.sqrt(
                burn.deltaV_vector.x ** 2
                + burn.deltaV_vector.y ** 2
                + burn.deltaV_vector.z ** 2
            )
            logger.maneuver_scheduled(
                sat_id, burn.burn_id, "MANUAL", dv * 1000, burn.burnTime
            )

    return ManeuverResponse(
        status="SCHEDULED" if success else "REJECTED",
        validation=validation if validation else {"error": msg},
    )


# ══════════════════════════════════════════════════════════
# POST /api/simulate/step
# ══════════════════════════════════════════════════════════

@app.post("/api/simulate/step", response_model=SimulateStepResponse)
async def simulate_step(data: SimulateStepInput):
    """Advance simulation by step_seconds.

    During each tick:
    1. Propagate all objects (J2-perturbed RK4)
    2. Execute any scheduled maneuvers within the time window
    3. Propagate nominal slots (they orbit too)
    4. Update station-keeping statuses
    5. Trigger recovery burns for drifted satellites
    6. Check for collisions
    """
    step = data.step_seconds
    old_time = sm.timestamp
    new_time = old_time + timedelta(seconds=step)

    # 1. Propagate all objects
    if sm.positions.shape[0] > 0:
        states = np.hstack([sm.positions, sm.velocities])  # Nx6
        new_states = propagate_batch(states, float(step), RK4_TIMESTEP)
        sm.positions = new_states[:, :3]
        sm.velocities = new_states[:, 3:]

    # 2. Execute scheduled maneuvers within [old_time, new_time]
    maneuvers_executed = scheduler.execute_due_maneuvers(old_time, new_time)

    # 3. Propagate nominal slots (they are reference orbits that also move)
    if sm.nominal_slots:
        slot_ids = list(sm.nominal_slots.keys())
        # Build state array for nominal slots — need velocity too
        # Slots have stored positions; we re-derive velocity from circular orbit
        slot_states = []
        for sid in slot_ids:
            r = sm.nominal_slots[sid]
            r_mag = np.linalg.norm(r)
            if r_mag > 0:
                # Circular orbit velocity: v = sqrt(μ/r), perpendicular to r
                v_mag = np.sqrt(398600.4418 / r_mag)
                # Approximate velocity direction (perpendicular in orbital plane)
                r_hat = r / r_mag
                # Use a simple perpendicular: rotate r_hat by 90° in the x-y plane
                v_hat = np.array([-r_hat[1], r_hat[0], 0.0])
                v_hat_mag = np.linalg.norm(v_hat)
                if v_hat_mag > 1e-10:
                    v_hat = v_hat / v_hat_mag
                else:
                    v_hat = np.array([0.0, 1.0, 0.0])
                v = v_hat * v_mag
            else:
                v = np.zeros(3)
            slot_states.append(np.concatenate([r, v]))

        slot_arr = np.array(slot_states)
        if slot_arr.shape[0] > 0:
            new_slot_states = propagate_batch(slot_arr, float(step), RK4_TIMESTEP)
            for i, sid in enumerate(slot_ids):
                sm.nominal_slots[sid] = new_slot_states[i, :3]

    # 4. Update timestamp
    sm.timestamp = new_time

    # 5. Update station-keeping statuses
    sk.update_all_statuses()

    # 6. Trigger recovery burns for out-of-slot satellites
    sk.run_recovery_sweep()

    # 7. Check for collisions
    collisions = _check_collisions()

    logger.sim_step_complete(
        new_time.isoformat(), collisions, maneuvers_executed, len(sm.ids)
    )

    return SimulateStepResponse(
        status="STEP_COMPLETE",
        new_timestamp=new_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        collisions_detected=collisions,
        maneuvers_executed=maneuvers_executed,
    )


# ══════════════════════════════════════════════════════════
# GET /api/visualization/snapshot
# ══════════════════════════════════════════════════════════

@app.get("/api/visualization/snapshot")
async def get_snapshot():
    """Return compressed state for frontend visualization."""
    ts_unix = sm.timestamp.timestamp()

    satellites = []
    for sid in sm.sat_ids:
        if sid not in sm._id_to_idx:
            continue
        idx = sm._id_to_idx[sid]
        r = sm.positions[idx]
        lat, lon, alt = eci_to_lla(r, ts_unix)

        satellites.append({
            "id": sid,
            "lat": round(lat, 3),
            "lon": round(lon, 3),
            "alt": round(alt, 1),
            "fuel_kg": round(sm.fuel.get(sid, 0), 2),
            "status": sm.objects.get(sid, {}).get("status", "NOMINAL"),
            "drift_km": sm.objects.get(sid, {}).get("drift_km", 0),
            "r": {
                "x": round(float(r[0]), 3),
                "y": round(float(r[1]), 3),
                "z": round(float(r[2]), 3),
            },
        })

    debris_cloud = []
    for did in sm.deb_ids[:5000]:
        if did not in sm._id_to_idx:
            continue
        idx = sm._id_to_idx[did]
        r = sm.positions[idx]
        lat, lon, alt = eci_to_lla(r, ts_unix)
        debris_cloud.append([did, round(lat, 2), round(lon, 2), round(alt, 1)])

    return {
        "timestamp": sm.timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "satellites": satellites,
        "debris_cloud": debris_cloud,
        "cdm_warnings": sm.active_cdms[:20],
        "maneuver_queue": scheduler.get_queue_as_dicts(limit=50),
        "fleet_uptime": sk.get_fleet_uptime(),
    }


# ══════════════════════════════════════════════════════════
# Helper functions
# ══════════════════════════════════════════════════════════

def _check_collisions():
    """Check for actual collisions (miss < 100m) at current time."""
    sat_indices = sm.get_satellite_indices()
    deb_indices = sm.get_debris_indices()
    if not sat_indices or not deb_indices:
        return 0

    from scipy.spatial import KDTree

    deb_pos = sm.positions[deb_indices]
    tree = KDTree(deb_pos)
    collisions = 0

    for si in sat_indices:
        nearby = tree.query_ball_point(sm.positions[si], r=COLLISION_THRESHOLD)
        if nearby:
            collisions += len(nearby)
            # Log each collision
            for j in nearby:
                deb_idx = deb_indices[j]
                dist = np.linalg.norm(sm.positions[si] - sm.positions[deb_idx])
                logger.collision_detected(sm.ids[si], sm.ids[deb_idx], dist)

    return collisions


# ══════════════════════════════════════════════════════════
# Serve frontend static files (production mode)
# ══════════════════════════════════════════════════════════

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
