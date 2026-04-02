"""
Test: snapshot endpoint returns the enriched contract fields.
Requires backend running on localhost:8000.
"""
import pytest
import requests

BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def snapshot():
    try:
        r = requests.get(f"{BASE}/api/visualization/snapshot", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        pytest.skip(f"Backend not running: {e}")


def test_snapshot_has_ground_stations(snapshot):
    assert "ground_stations" in snapshot
    assert isinstance(snapshot["ground_stations"], list)
    assert len(snapshot["ground_stations"]) > 0
    gs = snapshot["ground_stations"][0]
    assert "id" in gs and "lat" in gs and "lon" in gs


def test_snapshot_satellite_has_tracks(snapshot):
    sats = snapshot.get("satellites", [])
    if not sats:
        pytest.skip("No satellites in snapshot")
    sat = sats[0]
    assert "past_track"   in sat, "Satellite missing past_track"
    assert "future_track" in sat, "Satellite missing future_track"


def test_snapshot_cdm_has_approach_angle(snapshot):
    cdms = snapshot.get("cdm_warnings", [])
    if not cdms:
        pytest.skip("No CDMs in snapshot")
    cdm = cdms[0]
    assert "approach_angle_deg"  in cdm
    assert "relative_speed_kms" in cdm


def test_snapshot_has_metrics_history(snapshot):
    assert "metrics_history" in snapshot
    assert isinstance(snapshot["metrics_history"], list)


def test_snapshot_debris_is_tuple_format(snapshot):
    cloud = snapshot.get("debris_cloud", [])
    if not cloud:
        pytest.skip("No debris in snapshot")
    item = cloud[0]
    assert isinstance(item, list), "Debris items must be arrays (PS tuple format)"
    assert len(item) == 4, "Debris tuple must be [id, lat, lon, alt]"


def test_snapshot_has_exponential_uptime(snapshot):
    assert "fleet_uptime_exp" in snapshot
    assert 0.0 <= snapshot["fleet_uptime_exp"] <= 1.0
