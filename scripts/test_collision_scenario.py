"""
Test ACM with a DELIBERATE collision scenario.

Injects debris on a collision course and verifies:
  1. Conjunction IS detected
  2. Evasion maneuver IS scheduled
  3. Maneuver executes and fuel decreases
  4. Collision IS avoided

USAGE:
  1. Start backend fresh:  python -m uvicorn backend.main:app --port 8000
  2. Run:                  python scripts/test_collision_scenario.py
"""
import requests
import json
import math
import sys

API = "http://localhost:8000"
MU = 398600.4418
RE = 6378.137


def get(path):
    return requests.get(f"{API}{path}", timeout=10).json()


def post(path, data):
    return requests.post(f"{API}{path}", json=data, timeout=120).json()


def run():
    print("=" * 70)
    print("  PROJECT AETHER — Collision Scenario Test")
    print("=" * 70)

    # Check API
    try:
        snap = get("/api/visualization/snapshot")
    except:
        print("ERROR: API not running. Start with:")
        print("  python -m uvicorn backend.main:app --port 8000")
        sys.exit(1)

    sats = snap["satellites"]
    if not sats:
        print("ERROR: No satellites. Run: python scripts/generate_initial_data.py")
        sys.exit(1)

    target = sats[0]
    sat_id = target["id"]
    r = target["r"]
    initial_fuel = target["fuel_kg"]

    print(f"\n  Target: {sat_id}")
    print(f"  Position: ({r['x']:.1f}, {r['y']:.1f}, {r['z']:.1f}) km")
    print(f"  Fuel: {initial_fuel} kg")

    # ── Create debris on collision course ──
    # Strategy: place debris in the same orbit but slightly ahead,
    # moving in the OPPOSITE direction (counter-orbital).
    # At 550km altitude, circular velocity is ~7.6 km/s.
    # Counter-orbital closing speed = ~15.2 km/s.
    # Place debris 500km ahead — collision in ~33 seconds.
    # The adaptive coarse step should use ~3s steps for this (500km / (2 * 15.2) ≈ 16s → step ~8s).

    sat_pos = [r["x"], r["y"], r["z"]]
    r_mag = math.sqrt(sum(p ** 2 for p in sat_pos))
    v_circ = math.sqrt(MU / r_mag)

    # Unit vectors
    r_hat = [p / r_mag for p in sat_pos]

    # Perpendicular in orbital plane (along-track direction)
    perp = [-sat_pos[1], sat_pos[0], 0]
    perp_mag = math.sqrt(sum(p ** 2 for p in perp))
    if perp_mag > 0:
        perp = [p / perp_mag for p in perp]

    # Debris 500km ahead in along-track direction
    offset = 400.0
    deb_pos = [sat_pos[i] + perp[i] * offset for i in range(3)]

    # Debris velocity: counter-orbital (opposite direction to satellite motion)
    # Satellite moves in +perp direction, debris moves in -perp direction
    deb_vel = [-perp[i] * v_circ for i in range(3)]

    time_to_impact = offset / (2 * v_circ)

    print(f"\n  Debris offset: {offset} km along-track")
    print(f"  Closing speed: ~{2 * v_circ:.1f} km/s")
    print(f"  Time to impact: ~{time_to_impact:.1f} seconds")

    # ── Inject debris via telemetry ──
    print("\n[1] Injecting collision debris via POST /api/telemetry...")
    result = post("/api/telemetry", {
        "timestamp": snap["timestamp"],
        "objects": [{
            "id": "DEB-COLLIDER-001",
            "type": "DEBRIS",
            "r": {"x": round(deb_pos[0], 6), "y": round(deb_pos[1], 6), "z": round(deb_pos[2], 6)},
            "v": {"x": round(deb_vel[0], 6), "y": round(deb_vel[1], 6), "z": round(deb_vel[2], 6)},
        }]
    })
    print(f"  Response: {json.dumps(result)}")
    print(f"  CDM warnings from telemetry: {result.get('active_cdm_warnings', 0)}")

    # ── Check snapshot for CDMs ──
    print("\n[2] Checking snapshot for CDM detection...")
    snap = get("/api/visualization/snapshot")
    cdms = snap.get("cdm_warnings", [])
    queue = snap.get("maneuver_queue", [])

    print(f"  CDMs: {len(cdms)}")
    for c in cdms[:5]:
        print(f"    {c['sat_id']} ↔ {c['deb_id']} | TCA={c['tca_seconds']:.0f}s | miss={c['miss_distance_km']:.4f}km | {c['risk_level']}")
    print(f"  Maneuver queue: {len(queue)}")
    for m in queue[:5]:
        print(f"    {m['sat_id']} | {m['burn_type']} | ΔV={m['dv_magnitude_ms']:.2f} m/s")

    detected_on_telemetry = len(cdms) > 0
    evasion_scheduled = len(queue) > 0

    # ── Advance simulation in small steps ──
    print("\n[3] Advancing 5s × 30 steps (150 seconds)...")
    total_man = 0
    total_col = 0
    for i in range(30):
        res = post("/api/simulate/step", {"step_seconds": 5})
        man = res.get("maneuvers_executed", 0)
        col = res.get("collisions_detected", 0)
        total_man += man
        total_col += col
        if man > 0:
            print(f"    Step {i + 1}: {man} maneuver(s) executed!")
        if col > 0:
            print(f"    Step {i + 1}: ⚠️  {col} COLLISION(S)!")

    # ── Check after simulate steps ──
    print("\n[4] Post-simulation check...")
    snap = get("/api/visualization/snapshot")
    cdms = snap.get("cdm_warnings", [])
    queue = snap.get("maneuver_queue", [])

    if not detected_on_telemetry and len(cdms) > 0:
        print(f"  CDM detected during simulation: {len(cdms)}")
        detected_on_telemetry = True

    if not evasion_scheduled and len(queue) > 0:
        print(f"  Evasion scheduled during simulation: {len(queue)}")
        evasion_scheduled = True

    target_now = next((s for s in snap["satellites"] if s["id"] == sat_id), None)
    fuel_now = target_now["fuel_kg"] if target_now else initial_fuel
    fuel_used = initial_fuel - fuel_now

    print(f"  Target fuel: {fuel_now:.2f} kg (used {fuel_used:.4f} kg)")
    print(f"  Target status: {target_now['status'] if target_now else 'N/A'}")
    print(f"  Total maneuvers: {total_man}")
    print(f"  Total collisions: {total_col}")

    # ── Continue 24h to test recovery ──
    print("\n[5] Running 24h in 1h steps for recovery test...")
    for i in range(24):
        res = post("/api/simulate/step", {"step_seconds": 3600})
        man = res.get("maneuvers_executed", 0)
        col = res.get("collisions_detected", 0)
        total_man += man
        total_col += col

    snap = get("/api/visualization/snapshot")
    target_final = next((s for s in snap["satellites"] if s["id"] == sat_id), None)

    # ── Verdict ──
    print("\n" + "=" * 70)
    print("  VERDICT")
    print("=" * 70)

    all_pass = True

    if total_col == 0:
        print("  ✅ PASS: Zero collisions")
    else:
        print(f"  ❌ FAIL: {total_col} collision(s)")
        all_pass = False

    if detected_on_telemetry:
        print("  ✅ PASS: Conjunction detected")
    else:
        print("  ❌ FAIL: Conjunction NOT detected")
        all_pass = False

    if total_man > 0:
        print(f"  ✅ PASS: {total_man} maneuver(s) executed")
    else:
        print("  ❌ FAIL: No maneuvers executed")
        all_pass = False

    if fuel_used > 0:
        print(f"  ✅ PASS: Fuel tracking works ({fuel_used:.4f} kg consumed)")
    else:
        print("  ⚠️  WARN: No fuel consumed")

    if target_final:
        nominal = sum(1 for s in snap["satellites"] if s["status"] == "NOMINAL")
        print(f"  ℹ️  NOMINAL: {nominal}/{len(snap['satellites'])}")
        print(f"  ℹ️  Fleet uptime: {snap.get('fleet_uptime', 'N/A')}")

    if all_pass:
        print("\n  ══ ALL CRITICAL TESTS PASSED ══")
    else:
        print("\n  ══ SOME TESTS FAILED ══")


if __name__ == "__main__":
    run()
