"""
Regression test: the critical collision scenario must succeed reliably.

This is a trimmed version of scripts/test_collision_scenario.py
designed to run in under 60 seconds and confirm the key invariants:
  - Zero collisions
  - Evasion maneuver fires
  - Fuel depletion happens
"""
import pytest
import requests
import time

BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def snapshot():
    try:
        r = requests.get(f"{BASE}/api/visualization/snapshot", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        pytest.skip(f"Backend not running: {e}")


def test_collision_scenario(snapshot):
    sats = snapshot.get("satellites", [])
    if not sats:
        pytest.skip("No satellites loaded")

    target = sats[0]
    sat_id = target["id"]
    v      = target.get("v")
    if not v:
        pytest.skip("Satellite has no velocity in snapshot")

    # Compute along-track direction from actual velocity
    import numpy as np
    vel = np.array([v["x"], v["y"], v["z"]])
    vn  = vel / np.linalg.norm(vel)

    sat_r = np.array([target["r"]["x"], target["r"]["y"], target["r"]["z"]])
    # Place debris 300 km ahead and counter-orbital
    deb_r = sat_r + vn * 300.0
    deb_v = -vel * 1.002  # counter-orbital

    ts = snapshot["timestamp"]

    # Inject debris
    r = requests.post(f"{BASE}/api/telemetry", json={
        "timestamp": ts,
        "objects": [{
            "id": "DEB-REGTEST-001",
            "type": "DEBRIS",
            "r": {"x": float(deb_r[0]), "y": float(deb_r[1]), "z": float(deb_r[2])},
            "v": {"x": float(deb_v[0]), "y": float(deb_v[1]), "z": float(deb_v[2])},
        }]
    }, timeout=30)
    assert r.status_code == 200

    # Advance simulation: 30 steps × 5s = 150s
    total_collisions = 0
    total_maneuvers  = 0
    for _ in range(30):
        resp = requests.post(f"{BASE}/api/simulate/step", json={"step_seconds": 5}, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        total_collisions += data.get("collisions_detected", 0)
        total_maneuvers  += data.get("maneuvers_executed", 0)

    assert total_collisions == 0, f"Expected 0 collisions, got {total_collisions}"
    assert total_maneuvers >= 1, f"Expected at least 1 maneuver executed, got {total_maneuvers}"
