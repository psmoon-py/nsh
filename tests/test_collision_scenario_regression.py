"""Regression test for an actually dynamically collisional scenario.

This test is self-contained. It uses FastAPI TestClient and computes a debris
state that is collisional under the same J2-perturbed propagator used by the
backend, rather than relying on a visually plausible but dynamically invalid
head-on setup.
"""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from scripts.collision_case_builder import build_dynamic_collision_case


def _mute_logger(logger_obj):
    logger_obj.telemetry_ingested = lambda *a, **k: None
    logger_obj.conjunction_detected = lambda *a, **k: None
    logger_obj.maneuver_scheduled = lambda *a, **k: None
    logger_obj.maneuver_executed = lambda *a, **k: None
    logger_obj.maneuver_rejected = lambda *a, **k: None
    logger_obj.collision_detected = lambda *a, **k: None
    logger_obj.eol_triggered = lambda *a, **k: None
    logger_obj.sim_step_complete = lambda *a, **k: None
    logger_obj.los_check = lambda *a, **k: None


def _reduce_world_to_one_satellite(backend_main, sat_id: str):
    sm = backend_main.sm
    idx = sm._id_to_idx[sat_id]
    sm.ids = [sat_id]
    sm.sat_ids = [sat_id]
    sm.deb_ids = []
    sm.positions = sm.positions[[idx], :].copy()
    sm.velocities = sm.velocities[[idx], :].copy()
    sm._id_to_idx = {sat_id: 0}
    sm.objects = {sat_id: sm.objects[sat_id]}
    sm.nominal_slots = {sat_id: sm.nominal_slots[sat_id]}
    sm.nominal_slot_vels = {sat_id: sm.nominal_slot_vels[sat_id]}
    sm.fuel = {sat_id: sm.fuel[sat_id]}
    sm.masses = {sat_id: sm.masses[sat_id]}
    sm.last_burn_time = {sat_id: sm.last_burn_time[sat_id]}
    sm.track_history = {sat_id: sm.track_history.get(sat_id, [])}
    sm.active_cdms = []
    sm.conjunction_watchlist = []
    sm.maneuver_log = []
    sm.total_collisions_avoided = 0
    backend_main.scheduler.queue = []
    backend_main.scheduler.burn_counter = 0


def test_collision_scenario_regression():
    import backend.main as backend_main

    backend_main = importlib.reload(backend_main)
    _mute_logger(backend_main.logger)
    client = TestClient(backend_main.app)

    snapshot = client.get("/api/visualization/snapshot").json()
    target = snapshot["satellites"][0]
    _reduce_world_to_one_satellite(backend_main, target["id"])
    client = TestClient(backend_main.app)
    snapshot = client.get("/api/visualization/snapshot").json()
    target = snapshot["satellites"][0]
    initial_fuel = float(target["fuel_kg"])

    case = build_dynamic_collision_case(target, deb_id="DEB-REGTEST-DYN-001")
    telemetry = client.post(
        "/api/telemetry",
        json={
            "timestamp": snapshot["timestamp"],
            "objects": [case.telemetry_object()],
        },
    )
    assert telemetry.status_code == 200

    snap_after_ingest = client.get("/api/visualization/snapshot").json()
    cdm = next((c for c in snap_after_ingest.get("cdm_warnings", []) if c.get("deb_id") == case.deb_id), None)
    assert cdm is not None, "Injected debris should create a detectable CDM"
    assert cdm["risk_level"] in ("CRITICAL", "RED")

    queue = [m for m in snap_after_ingest.get("maneuver_queue", []) if m.get("sat_id") == target["id"]]
    assert any(m["burn_type"] == "EVASION" for m in queue), "Evasion should be queued"

    step_seconds = 30
    total_steps = int((cdm["tca_seconds"] + 120.0) // step_seconds) + 1
    total_collisions = 0
    total_maneuvers = 0
    for _ in range(total_steps):
        resp = client.post("/api/simulate/step", json={"step_seconds": step_seconds})
        assert resp.status_code == 200
        data = resp.json()
        total_collisions += int(data.get("collisions_detected", 0))
        total_maneuvers += int(data.get("maneuvers_executed", 0))

    assert total_collisions == 0, f"Expected zero collisions, got {total_collisions}"
    assert total_maneuvers >= 1, f"Expected at least one maneuver execution, got {total_maneuvers}"

    final_snapshot = client.get("/api/visualization/snapshot").json()
    final_sat = next(s for s in final_snapshot["satellites"] if s["id"] == target["id"])
    fuel_used = initial_fuel - float(final_sat["fuel_kg"])
    assert fuel_used > 0.0, "Fuel should decrease after evasion"
