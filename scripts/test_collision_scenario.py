"""End-to-end live API validation using a dynamically-collisional debris case.

This version no longer assumes that a visually head-on setup remains collisional
under the backend's full J2-perturbed dynamics. Instead it builds a debris state
that is collisional under the same propagator used by the ACM.
"""
from __future__ import annotations

import json
import math
import sys
from typing import Any, Dict

import requests

from scripts.collision_case_builder import build_dynamic_collision_case

API = "http://localhost:8000"


def get(path: str) -> Dict[str, Any]:
    response = requests.get(f"{API}{path}", timeout=10)
    response.raise_for_status()
    return response.json()


def post(path: str, data: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(f"{API}{path}", json=data, timeout=120)
    response.raise_for_status()
    return response.json()


def run() -> int:
    print("=" * 72)
    print(" PROJECT AETHER — Dynamically Collisional Scenario Test")
    print("=" * 72)

    try:
        snap = get("/api/visualization/snapshot")
    except Exception:
        print("ERROR: API not running. Start with:")
        print("  python -m uvicorn backend.main:app --port 8000")
        return 1

    sats = snap.get("satellites", [])
    if not sats:
        print("ERROR: No satellites loaded.")
        return 1

    target = sats[0]
    sat_id = target["id"]
    initial_fuel = float(target["fuel_kg"])
    print(f"Target satellite: {sat_id}")
    print(f"Initial fuel: {initial_fuel:.3f} kg")

    case = build_dynamic_collision_case(target)
    print("\nConstructed dynamic collision case:")
    print(f"  Debris id: {case.deb_id}")
    print(f"  Basis: {case.basis_name}")
    print(f"  Initial offset: {case.offset_km:.2f} km")
    print(f"  Predicted TCA: {case.tca_seconds:.1f} s")
    print(f"  Predicted miss without evasion: {case.miss_distance_km:.6f} km")
    print(f"  Relative speed at TCA: {case.relative_speed_kms:.5f} km/s")

    telemetry_result = post("/api/telemetry", {
        "timestamp": snap["timestamp"],
        "objects": [case.telemetry_object()],
    })
    print("\nTelemetry ACK:")
    print(json.dumps(telemetry_result, indent=2))

    snap = get("/api/visualization/snapshot")
    cdms = snap.get("cdm_warnings", [])
    queue = snap.get("maneuver_queue", [])
    target_cdm = next((c for c in cdms if c.get("deb_id") == case.deb_id), None)
    target_queue = [m for m in queue if m.get("sat_id") == sat_id]

    print("\nPost-ingest status:")
    print(f"  Active CDMs: {len(cdms)}")
    print(f"  Maneuver queue entries for {sat_id}: {len(target_queue)}")
    if target_cdm:
        print(
            f"  CDM: {target_cdm['risk_level']} | "
            f"TCA={target_cdm['tca_seconds']:.1f}s | "
            f"miss={target_cdm['miss_distance_km']:.6f} km"
        )
    else:
        print("  ERROR: No CDM found for the injected collider.")
        return 1

    step_seconds = 30
    total_steps = int(math.ceil((target_cdm["tca_seconds"] + 120.0) / step_seconds))
    total_collisions = 0
    total_maneuvers = 0

    print(f"\nAdvancing {total_steps} steps of {step_seconds}s each...")
    for i in range(total_steps):
        result = post("/api/simulate/step", {"step_seconds": step_seconds})
        total_collisions += int(result.get("collisions_detected", 0))
        total_maneuvers += int(result.get("maneuvers_executed", 0))
        if result.get("maneuvers_executed", 0):
            print(f"  Step {i+1:03d}: executed {result['maneuvers_executed']} maneuver(s)")
        if result.get("collisions_detected", 0):
            print(f"  Step {i+1:03d}: COLLISION DETECTED")

    snap = get("/api/visualization/snapshot")
    target_after = next(s for s in snap["satellites"] if s["id"] == sat_id)
    fuel_used = initial_fuel - float(target_after["fuel_kg"])

    print("\nFinal status:")
    print(f"  Total maneuvers executed: {total_maneuvers}")
    print(f"  Total collisions detected: {total_collisions}")
    print(f"  Fuel used: {fuel_used:.6f} kg")
    print(f"  Final satellite status: {target_after['status']}")

    ok = True
    if total_collisions != 0:
        ok = False
        print("  FAIL: collision occurred")
    if total_maneuvers < 1:
        ok = False
        print("  FAIL: evasion maneuver did not execute")
    if fuel_used <= 0:
        ok = False
        print("  FAIL: no fuel was consumed")
    if target_cdm["risk_level"] not in ("CRITICAL", "RED"):
        ok = False
        print("  FAIL: injected case was not high-risk enough")

    if ok:
        print("\n✅ PASS: dynamic collision case detected, avoided, and logged correctly")
        return 0

    print("\n❌ FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(run())
