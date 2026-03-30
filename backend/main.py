"""
FastAPI application — Autonomous Constellation Manager API.
Exposes all endpoints on port 8000 as required by the problem statement.

Fixes applied:
  - Satellite velocity included in snapshot (needed by test & frontend)
  - Auto-evasion triggers for both CRITICAL and RED CDMs
  - Duplicate evasion prevention: won't schedule if sat already has pending evasion
  - Sub-step propagation for large simulation steps (catches mid-step collisions)
  - Proper logging of burn execution events
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


def np_safe(val):
    """Convert numpy types to native Python for JSON serialization."""
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    if isinstance(val, dict):
        return {k: np_safe(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [np_safe(v) for v in val]
    return val


# ══════════════════════════════════════════════════════════
app = FastAPI(title="ACM — Autonomous Constellation Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

sm = StateManager()
cd = ConjunctionDetector(sm)
gn = GroundStationNetwork()
scheduler = ManeuverScheduler(sm, gn)
sk = StationKeepingManager(sm, scheduler)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
gs_csv = os.path.join(DATA_DIR, "ground_stations.csv")
if os.path.exists(gs_csv):
    gn.load_from_csv(gs_csv)
else:
    gn.load_defaults()

sat_file = os.path.join(DATA_DIR, "satellites_init.json")
deb_file = os.path.join(DATA_DIR, "debris_init.json")
if os.path.exists(sat_file) and os.path.exists(deb_file):
    sm.load_initial_data(sat_file, deb_file)
    logger.telemetry_ingested(len(sm.ids), 0, sm.timestamp.isoformat())


def _run_conjunction_and_evasion():
    """Run conjunction assessment and auto-schedule evasions for dangerous CDMs.

    FIX: Triggers for both CRITICAL (miss < 100m) and RED (miss < 1km) CDMs.
    FIX: Skips satellites that already have a pending evasion maneuver.
    Called after both telemetry ingestion AND simulation steps.
    """
    cdm_warnings = cd.run_full_assessment()
    sm.active_cdms = cdm_warnings

    for cdm in cdm_warnings:
        logger.conjunction_detected(
            cdm["sat_id"], cdm["deb_id"],
            cdm["tca_seconds"], cdm["miss_distance_km"], cdm["risk_level"],
        )

        # FIX: trigger evasion for CRITICAL and RED (not just CRITICAL)
        if cdm["risk_level"] in ("CRITICAL", "RED"):
            sat_id = cdm["sat_id"]

            # FIX: skip if satellite already has a pending evasion
            pending = scheduler.get_pending_for_satellite(sat_id)
            has_evasion = any(c.burn_type == "EVASION" for c in pending)
            if has_evasion:
                continue

            evasion_cmd = scheduler.auto_schedule_evasion(cdm)
            if evasion_cmd:
                logger.maneuver_scheduled(
                    evasion_cmd.sat_id, evasion_cmd.burn_id,
                    evasion_cmd.burn_type, evasion_cmd.delta_v_magnitude_ms,
                    evasion_cmd.burn_time,
                )

    scheduler.check_and_schedule_eol()
    return cdm_warnings


# ══════════════════════════════════════════════════════════
# POST /api/telemetry
# ══════════════════════════════════════════════════════════

@app.post("/api/telemetry", response_model=TelemetryResponse)
async def ingest_telemetry(data: TelemetryInput):
    sm.update_from_telemetry(data.timestamp, [obj.model_dump() for obj in data.objects])
    cdm_warnings = _run_conjunction_and_evasion()
    logger.telemetry_ingested(len(data.objects), len(cdm_warnings), data.timestamp)

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
    sat_id = data.satelliteId
    if sat_id not in sm.objects:
        return ManeuverResponse(
            status="REJECTED",
            validation={"error": f"Satellite {sat_id} not found"},
        )

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
            dv = np.sqrt(burn.deltaV_vector.x**2 + burn.deltaV_vector.y**2 + burn.deltaV_vector.z**2)
            logger.maneuver_scheduled(sat_id, burn.burn_id, "MANUAL", float(dv * 1000), burn.burnTime)

    return ManeuverResponse(
        status="SCHEDULED" if success else "REJECTED",
        validation=np_safe(validation) if validation else {"error": msg},
    )


# ══════════════════════════════════════════════════════════
# POST /api/simulate/step
# ══════════════════════════════════════════════════════════

@app.post("/api/simulate/step", response_model=SimulateStepResponse)
async def simulate_step(data: SimulateStepInput):
    step = data.step_seconds
    if step <= 0:
        return SimulateStepResponse(
            status="STEP_COMPLETE",
            new_timestamp=sm.timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            collisions_detected=0,
            maneuvers_executed=0,
        )

    old_time = sm.timestamp
    new_time = old_time + timedelta(seconds=step)

    # ── Sub-step propagation for large steps ──
    # Break steps > 30s into sub-steps to catch mid-step collisions
    # and execute maneuvers at the correct time within the interval.
    MAX_SUB_STEP = 30.0
    total_collisions = 0
    total_maneuvers = 0

    if step <= MAX_SUB_STEP:
        sub_steps = [float(step)]
    else:
        n_subs = max(1, int(np.ceil(step / MAX_SUB_STEP)))
        sub_dt = step / n_subs
        sub_steps = [sub_dt] * n_subs

    current_time = old_time

    for sub_dt in sub_steps:
        sub_new_time = current_time + timedelta(seconds=sub_dt)

        # 1. Propagate all objects
        if sm.positions.shape[0] > 0:
            states = np.hstack([sm.positions, sm.velocities])
            new_states = propagate_batch(states, sub_dt, RK4_TIMESTEP)
            sm.positions = new_states[:, :3]
            sm.velocities = new_states[:, 3:]

        # 2. Execute scheduled maneuvers in this sub-window
        maneuvers_executed = scheduler.execute_due_maneuvers(current_time, sub_new_time)
        total_maneuvers += maneuvers_executed

        # 3. Check for collisions at end of sub-step
        sub_collisions = _check_collisions()
        total_collisions += sub_collisions

        current_time = sub_new_time

    # 4. Propagate nominal slots for the full step
    if sm.nominal_slots:
        slot_ids = list(sm.nominal_slots.keys())
        slot_states = []
        for sid in slot_ids:
            r = sm.nominal_slots[sid]
            v = sm.nominal_slot_vels.get(sid, np.zeros(3))
            slot_states.append(np.concatenate([r, v]))
        slot_arr = np.array(slot_states)
        if slot_arr.shape[0] > 0:
            new_slot_states = propagate_batch(slot_arr, float(step), RK4_TIMESTEP)
            for i, sid in enumerate(slot_ids):
                sm.nominal_slots[sid] = new_slot_states[i, :3]
                sm.nominal_slot_vels[sid] = new_slot_states[i, 3:]

    # 5. Update timestamp
    sm.timestamp = new_time

    # 6. Station-keeping
    sk.update_all_statuses()
    sk.run_recovery_sweep()

    # 7. RE-RUN conjunction assessment after propagation
    _run_conjunction_and_evasion()

    logger.sim_step_complete(
        new_time.isoformat(), total_collisions, total_maneuvers, len(sm.ids)
    )

    return SimulateStepResponse(
        status="STEP_COMPLETE",
        new_timestamp=new_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        collisions_detected=int(total_collisions),
        maneuvers_executed=int(total_maneuvers),
    )


# ══════════════════════════════════════════════════════════
# GET /api/visualization/snapshot
# ══════════════════════════════════════════════════════════

@app.get("/api/visualization/snapshot")
async def get_snapshot():
    ts_unix = sm.timestamp.timestamp()

    satellites = []
    for sid in sm.sat_ids:
        if sid not in sm._id_to_idx:
            continue
        idx = sm._id_to_idx[sid]
        r = sm.positions[idx]
        v = sm.velocities[idx]
        lat, lon, alt = eci_to_lla(r, ts_unix)
        satellites.append({
            "id": sid,
            "lat": round(float(lat), 3), "lon": round(float(lon), 3),
            "alt": round(float(alt), 1),
            "fuel_kg": round(float(sm.fuel.get(sid, 0)), 2),
            "status": sm.objects.get(sid, {}).get("status", "NOMINAL"),
            "drift_km": float(sm.objects.get(sid, {}).get("drift_km", 0)),
            # ECI position AND velocity — needed by test scripts and frontend
            "r": {"x": round(float(r[0]), 6), "y": round(float(r[1]), 6), "z": round(float(r[2]), 6)},
            "v": {"x": round(float(v[0]), 6), "y": round(float(v[1]), 6), "z": round(float(v[2]), 6)},
        })

    debris_cloud = []
    for did in sm.deb_ids[:5000]:
        if did not in sm._id_to_idx:
            continue
        idx = sm._id_to_idx[did]
        r = sm.positions[idx]
        lat, lon, alt = eci_to_lla(r, ts_unix)
        debris_cloud.append([did, round(float(lat), 2), round(float(lon), 2), round(float(alt), 1)])

    safe_cdms = []
    for cdm in sm.active_cdms[:20]:
        safe_cdms.append({
            "sat_id": cdm.get("sat_id", ""),
            "deb_id": cdm.get("deb_id", ""),
            "tca_seconds": float(cdm.get("tca_seconds", 0)),
            "miss_distance_km": float(cdm.get("miss_distance_km", 0)),
            "risk_level": cdm.get("risk_level", "GREEN"),
            "current_distance_km": float(cdm.get("current_distance_km", 0)),
        })

    safe_queue = [np_safe(cmd_dict) for cmd_dict in scheduler.get_queue_as_dicts(limit=50)]

    return {
        "timestamp": sm.timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "satellites": satellites,
        "debris_cloud": debris_cloud,
        "cdm_warnings": safe_cdms,
        "maneuver_queue": safe_queue,
        "fleet_uptime": float(sk.get_fleet_uptime()),
        "total_maneuvers_executed": len(scheduler.history),
        "total_collisions_avoided": len([h for h in scheduler.history
                                         if h.burn_type == "EVASION" and h.status == "EXECUTED"]),
    }


def _check_collisions():
    """Check for actual collisions (miss distance < 100m) at current positions."""
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
            for j in nearby:
                deb_idx = deb_indices[j]
                dist = float(np.linalg.norm(sm.positions[si] - sm.positions[deb_idx]))
                logger.collision_detected(sm.ids[si], sm.ids[deb_idx], dist)
    return collisions


FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
