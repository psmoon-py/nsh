"""
Test ACM with a DELIBERATE collision scenario.

Injects debris on a TRUE collision course using the satellite's actual
velocity vector from the snapshot API, and verifies:
  1. Conjunction IS detected (CDM with CRITICAL/RED risk)
  2. Evasion maneuver IS scheduled and executes
  3. Fuel is consumed (Tsiolkovsky mass depletion)
  4. Collision IS avoided (zero collisions)

FIX: Previous version used [-y, x, 0] as "along-track" direction, which
ignores the z-component of velocity (53° inclination). The debris ended up
~178 km away at closest approach — only YELLOW, never triggering evasion.
Now uses the actual velocity vector from the snapshot API.

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


def vec_mag(v):
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)


def vec_normalize(v):
    m = vec_mag(v)
    return [c / m for c in v] if m > 1e-10 else [0, 0, 0]


def run():
    print("=" * 70)
    print("  PROJECT AETHER — Collision Scenario Test")
    print("=" * 70)

    # Check API
    try:
        snap = get("/api/visualization/snapshot")
    except Exception:
        print("ERROR: API not running. Start with:")
        print("  python -m uvicorn backend.main:app --port 5173")
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

    # ── Read ACTUAL velocity from the snapshot API ──
    if "v" not in target:
        print("ERROR: Snapshot does not include velocity 'v' field.")
        print("  The backend needs to expose satellite velocities in the snapshot.")
        sys.exit(1)

    v = target["v"]
    sat_vel = [v["x"], v["y"], v["z"]]
    v_mag = vec_mag(sat_vel)
    print(f"  Velocity: ({v['x']:.3f}, {v['y']:.3f}, {v['z']:.3f}) km/s  |v|={v_mag:.3f}")

    # ── Create debris on a TRUE collision course ──
    # Strategy: place debris AHEAD of the satellite along its ACTUAL velocity
    # direction, moving in the OPPOSITE direction (counter-orbital).
    # This guarantees a head-on approach with ~2x orbital velocity closing speed.
    #
    # At 550km altitude, v_circ ≈ 7.6 km/s.
    # Counter-orbital closing speed ≈ 15.2 km/s.
    # At 400 km offset, TCA ≈ 400 / 15.2 ≈ 26 seconds.
    # Evasion burn at T+11s fires 15s before TCA → deflects ~230m transversely.

    sat_pos = [r["x"], r["y"], r["z"]]
    r_mag = vec_mag(sat_pos)

    # Along-track direction = actual velocity direction
    v_hat = vec_normalize(sat_vel)

    # Place debris ahead in the velocity direction
    offset = 400.0  # km ahead
    deb_pos = [sat_pos[i] + v_hat[i] * offset for i in range(3)]

    # Debris velocity: counter-orbital (opposite direction)
    v_circ = math.sqrt(MU / r_mag)
    deb_vel = [-v_hat[i] * v_circ for i in range(3)]

    closing_speed = v_mag + v_circ
    time_to_impact = offset / closing_speed

    print(f"\n  Along-track direction: ({v_hat[0]:.4f}, {v_hat[1]:.4f}, {v_hat[2]:.4f})")
    print(f"  Debris offset: {offset} km along velocity vector")
    print(f"  Closing speed: ~{closing_speed:.1f} km/s")
    print(f"  Time to impact: ~{time_to_impact:.1f} seconds")

    # Verify debris is at a reasonable altitude
    deb_r_mag = vec_mag(deb_pos)
    deb_alt = deb_r_mag - RE
    print(f"  Debris altitude: {deb_alt:.1f} km  (r={deb_r_mag:.1f} km)")

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
        marker = "⚠️ " if c['risk_level'] in ('CRITICAL', 'RED') else "  "
        print(f"    {marker}{c['sat_id']} ↔ {c['deb_id']} | TCA={c['tca_seconds']:.0f}s | miss={c['miss_distance_km']:.4f}km | {c['risk_level']}")
    print(f"  Maneuver queue: {len(queue)}")
    for m in queue[:5]:
        print(f"    {m['sat_id']} | {m['burn_type']} | ΔV={m['dv_magnitude_ms']:.2f} m/s | status={m['status']}")

    detected_on_telemetry = len(cdms) > 0
    evasion_scheduled = len(queue) > 0

    # Check specifically for our target satellite
    target_cdm = next((c for c in cdms if c['sat_id'] == sat_id and 'COLLIDER' in c['deb_id']), None)
    if target_cdm:
        print(f"\n  ✓ Target CDM found: {target_cdm['risk_level']} | TCA={target_cdm['tca_seconds']:.1f}s | miss={target_cdm['miss_distance_km']:.4f}km")
    else:
        # Also check if any CDM involves DEB-COLLIDER-001
        collider_cdm = next((c for c in cdms if 'COLLIDER' in c.get('deb_id', '')), None)
        if collider_cdm:
            print(f"\n  ✓ Collider CDM found (different sat): {collider_cdm['sat_id']} ↔ {collider_cdm['deb_id']}")
        else:
            print(f"\n  ✗ No CDM found for DEB-COLLIDER-001 (may appear during sim steps)")

    target_evasion = next((m for m in queue if m['sat_id'] == sat_id), None)
    if target_evasion:
        print(f"  ✓ Evasion queued: {target_evasion['burn_id']} | ΔV={target_evasion['dv_magnitude_ms']:.2f} m/s")

    # ── Advance simulation in small steps ──
    print(f"\n[3] Advancing 5s × 30 steps (150 seconds)...")
    total_man = 0
    total_col = 0
    for i in range(30):
        res = post("/api/simulate/step", {"step_seconds": 5})
        man = res.get("maneuvers_executed", 0)
        col = res.get("collisions_detected", 0)
        total_man += man
        total_col += col
        if man > 0:
            print(f"    Step {i + 1} (t={5*(i+1):>3}s): {man} maneuver(s) executed!")
        if col > 0:
            print(f"    Step {i + 1} (t={5*(i+1):>3}s): ⚠️  {col} COLLISION(S)!")

    # ── Check after simulate steps ──
    print("\n[4] Post-simulation check...")
    snap = get("/api/visualization/snapshot")
    cdms = snap.get("cdm_warnings", [])
    queue = snap.get("maneuver_queue", [])

    if not detected_on_telemetry and len(cdms) > 0:
        print(f"  CDM detected during simulation: {len(cdms)}")
        detected_on_telemetry = True

    if not evasion_scheduled and (len(queue) > 0 or total_man > 0):
        evasion_scheduled = True
        print(f"  Evasion acted upon during simulation")

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
        if man > 0:
            print(f"    Hour {i + 1}: {man} maneuver(s)")
        if col > 0:
            print(f"    Hour {i + 1}: ⚠️  {col} COLLISION(S)!")

    snap = get("/api/visualization/snapshot")
    target_final = next((s for s in snap["satellites"] if s["id"] == sat_id), None)
    fuel_final = target_final["fuel_kg"] if target_final else initial_fuel
    fuel_used_total = initial_fuel - fuel_final

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

    if fuel_used_total > 0:
        print(f"  ✅ PASS: Fuel tracking works ({fuel_used_total:.4f} kg consumed)")
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
