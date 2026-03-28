"""
Test ACM with REAL orbital data from CelesTrak.

Downloads actual Fengyun-1C debris TLEs (2,800+ tracked objects)
and Starlink satellite TLEs, converts them to ECI state vectors
using the sgp4 library, and sends them to your running API.

USAGE:
  1. Start your backend:  python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
  2. Run this script:     python scripts/test_with_real_data.py

WHAT IT DOES:
  - Downloads 50 Starlink satellites as your constellation
  - Downloads ~2,800 Fengyun-1C debris as the debris field
  - Converts all TLEs to ECI (x,y,z in km, vx,vy,vz in km/s)
  - Sends them via POST /api/telemetry
  - Runs 48 hours of simulation in 1-hour steps
  - Checks snapshot after each step for conjunctions, maneuvers, fuel use

REQUIRES:
  pip install requests sgp4
"""

import requests
import json
import math
import time
import sys
from datetime import datetime, timezone

# ── Configuration ──
API_BASE = "http://localhost:8000"
EPOCH_STR = "2026-03-28T12:00:00.000Z"  # Common epoch for all objects
N_SATS = 50        # How many Starlink sats to use
N_DEBRIS = 10000   # Max debris objects
SIM_STEPS = 48     # Number of 1-hour steps
STEP_SECONDS = 3600  # 1 hour per step


def download_celestrak_tles(group):
    """Download TLE data from CelesTrak in 3LE format (name + line1 + line2)."""
    url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=tle"
    print(f"  Downloading {group} from CelesTrak...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    lines = [l.strip() for l in resp.text.strip().split('\n') if l.strip()]
    
    tles = []
    i = 0
    while i < len(lines) - 2:
        name = lines[i]
        line1 = lines[i + 1]
        line2 = lines[i + 2]
        if line1.startswith('1') and line2.startswith('2'):
            tles.append((name, line1, line2))
            i += 3
        else:
            i += 1
    
    print(f"  Got {len(tles)} objects")
    return tles


def tle_to_eci(line1, line2, epoch_year, epoch_month, epoch_day, epoch_hour=12):
    """Convert TLE to ECI position (km) and velocity (km/s) using sgp4."""
    from sgp4.api import Satrec, jday
    
    sat = Satrec.twoline2rv(line1, line2)
    jd, fr = jday(epoch_year, epoch_month, epoch_day, epoch_hour, 0, 0.0)
    error, position, velocity = sat.sgp4(jd, fr)
    
    if error != 0:
        return None, None
    
    return list(position), list(velocity)


def format_as_telemetry(sat_tles, deb_tles, epoch_str):
    """Convert TLE lists to the /api/telemetry JSON format.
    
    Your API expects:
    {
        "timestamp": "2026-03-28T12:00:00.000Z",
        "objects": [
            {"id": "SAT-Alpha-01", "type": "SATELLITE", "r": {"x":..., "y":..., "z":...}, "v": {"x":..., "y":..., "z":...}},
            {"id": "DEB-00001", "type": "DEBRIS", "r": {"x":..., "y":..., "z":...}, "v": {"x":..., "y":..., "z":...}}
        ]
    }
    """
    objects = []
    
    print(f"\n  Converting {len(sat_tles)} satellites to ECI...")
    for i, (name, l1, l2) in enumerate(sat_tles):
        r, v = tle_to_eci(l1, l2, 2026, 3, 28, 12)
        if r is None:
            continue
        
        # Check for valid positions (skip if propagation diverged)
        r_mag = math.sqrt(r[0]**2 + r[1]**2 + r[2]**2)
        if r_mag < 6300 or r_mag > 50000:  # Clearly wrong
            continue
        
        objects.append({
            "id": f"SAT-Alpha-{i+1:02d}",
            "type": "SATELLITE",
            "r": {"x": round(r[0], 6), "y": round(r[1], 6), "z": round(r[2], 6)},
            "v": {"x": round(v[0], 6), "y": round(v[1], 6), "z": round(v[2], 6)},
        })
    
    print(f"  Converting {len(deb_tles)} debris to ECI...")
    for i, (name, l1, l2) in enumerate(deb_tles):
        r, v = tle_to_eci(l1, l2, 2026, 3, 28, 12)
        if r is None:
            continue
        
        r_mag = math.sqrt(r[0]**2 + r[1]**2 + r[2]**2)
        if r_mag < 6300 or r_mag > 50000:
            continue
        
        objects.append({
            "id": f"DEB-{10000+i}",
            "type": "DEBRIS",
            "r": {"x": round(r[0], 6), "y": round(r[1], 6), "z": round(r[2], 6)},
            "v": {"x": round(v[0], 6), "y": round(v[1], 6), "z": round(v[2], 6)},
        })
    
    sats = [o for o in objects if o["type"] == "SATELLITE"]
    debs = [o for o in objects if o["type"] == "DEBRIS"]
    print(f"  Valid: {len(sats)} satellites, {len(debs)} debris")
    
    return {"timestamp": epoch_str, "objects": objects}


def check_api_health():
    """Verify the API is running."""
    try:
        r = requests.get(f"{API_BASE}/api/visualization/snapshot", timeout=5)
        return r.status_code == 200
    except:
        return False


def run_test():
    print("=" * 60)
    print("  PROJECT AETHER — Real Data Test")
    print("=" * 60)
    
    # Step 0: Check API is running
    print("\n[0] Checking API health...")
    if not check_api_health():
        print("  ERROR: API not reachable at", API_BASE)
        print("  Start with: python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000")
        sys.exit(1)
    print("  API is running")
    
    # Step 1: Download real TLE data
    print("\n[1] Downloading real orbital data from CelesTrak...")
    try:
        sat_tles = download_celestrak_tles("starlink")[:N_SATS]
        
        # Combine multiple debris sources for a larger debris field
        deb_tles = []
        for group in ["fengyun-1c-debris", "cosmos-2251-debris", "iridium-33-debris"]:
            try:
                deb_tles.extend(download_celestrak_tles(group))
            except Exception as e:
                print(f"  Warning: Could not download {group}: {e}")
        
        deb_tles = deb_tles[:N_DEBRIS]
        print(f"  Total: {len(sat_tles)} sats, {len(deb_tles)} debris")
    except Exception as e:
        print(f"  ERROR downloading TLEs: {e}")
        print("  Falling back to existing synthetic data...")
        print("  (Your API already loaded satellites_init.json + debris_init.json)")
        sat_tles = []
        deb_tles = []
    
    # Step 2: Convert to ECI and send telemetry
    if sat_tles and deb_tles:
        print("\n[2] Converting TLEs to ECI state vectors...")
        telemetry = format_as_telemetry(sat_tles, deb_tles, EPOCH_STR)
        
        print(f"\n[3] Sending telemetry to POST /api/telemetry...")
        print(f"  Payload: {len(telemetry['objects'])} objects")
        resp = requests.post(f"{API_BASE}/api/telemetry", json=telemetry, timeout=60)
        result = resp.json()
        print(f"  Response: {json.dumps(result, indent=2)}")
    else:
        print("\n[2-3] Using existing data (already loaded at startup)")
    
    # Step 3: Get initial snapshot
    print(f"\n[4] Initial snapshot...")
    snap = requests.get(f"{API_BASE}/api/visualization/snapshot", timeout=10).json()
    print(f"  Timestamp: {snap['timestamp']}")
    print(f"  Satellites: {len(snap['satellites'])}")
    print(f"  Debris: {len(snap['debris_cloud'])}")
    print(f"  CDM Warnings: {len(snap.get('cdm_warnings', []))}")
    print(f"  Maneuver Queue: {len(snap.get('maneuver_queue', []))}")
    print(f"  Fleet Uptime: {snap.get('fleet_uptime', 'N/A')}")
    
    # Step 4: Run simulation steps
    print(f"\n[5] Running {SIM_STEPS} simulation steps ({STEP_SECONDS}s each = {SIM_STEPS*STEP_SECONDS/3600:.0f}h)...")
    print(f"{'Step':>4} | {'Sim Time':>24} | {'Collisions':>10} | {'Maneuvers':>9} | {'CDMs':>5} | {'Fleet Fuel':>10}")
    print("-" * 80)
    
    total_collisions = 0
    total_maneuvers = 0
    
    for step_num in range(1, SIM_STEPS + 1):
        # Advance simulation
        resp = requests.post(
            f"{API_BASE}/api/simulate/step",
            json={"step_seconds": STEP_SECONDS},
            timeout=120
        )
        step_result = resp.json()
        
        # Get snapshot
        snap = requests.get(f"{API_BASE}/api/visualization/snapshot", timeout=10).json()
        
        collisions = step_result.get("collisions_detected", 0)
        maneuvers = step_result.get("maneuvers_executed", 0)
        total_collisions += collisions
        total_maneuvers += maneuvers
        cdm_count = len(snap.get("cdm_warnings", []))
        
        # Calculate fleet fuel
        fleet_fuel = sum(s.get("fuel_kg", 0) for s in snap.get("satellites", []))
        
        print(f"{step_num:>4} | {snap['timestamp']:>24} | {collisions:>10} | {maneuvers:>9} | {cdm_count:>5} | {fleet_fuel:>9.1f}kg")
        
        # Log interesting events
        for cdm in snap.get("cdm_warnings", [])[:3]:
            print(f"       CDM: {cdm['sat_id']} ↔ {cdm['deb_id']} | TCA: {cdm['tca_seconds']:.0f}s | Miss: {cdm['miss_distance_km']:.4f}km | {cdm['risk_level']}")
    
    # Step 5: Final summary
    print("\n" + "=" * 60)
    print("  FINAL RESULTS")
    print("=" * 60)
    
    snap = requests.get(f"{API_BASE}/api/visualization/snapshot", timeout=10).json()
    sats = snap.get("satellites", [])
    
    nominal = sum(1 for s in sats if s.get("status") == "NOMINAL")
    out_of_slot = sum(1 for s in sats if s.get("status") == "OUT_OF_SLOT")
    fuels = [s.get("fuel_kg", 0) for s in sats]
    
    print(f"  Total Collisions:     {total_collisions}")
    print(f"  Total Maneuvers:      {total_maneuvers}")
    print(f"  Satellites NOMINAL:   {nominal}/{len(sats)}")
    print(f"  Satellites OUT_SLOT:  {out_of_slot}/{len(sats)}")
    print(f"  Fleet Uptime:         {snap.get('fleet_uptime', 'N/A')}")
    print(f"  Fuel — Min: {min(fuels):.2f}kg, Avg: {sum(fuels)/len(fuels):.2f}kg, Max: {max(fuels):.2f}kg")
    print(f"  Total Fuel Remaining: {sum(fuels):.1f}kg / {50.0 * len(sats):.0f}kg")
    
    if total_collisions == 0:
        print("\n  ✅ SAFETY: Zero collisions — all conjunctions avoided!")
    else:
        print(f"\n  ❌ SAFETY: {total_collisions} collisions detected — evasion failed!")
    
    if total_maneuvers > 0:
        print(f"  ✅ AUTONOMY: {total_maneuvers} maneuvers executed autonomously")
    else:
        print(f"  ⚠️  NO MANEUVERS: Either no conjunctions arose, or evasion logic didn't trigger")
    
    print("\nDone!")


if __name__ == "__main__":
    run_test()
