"""Test: snapshot endpoint returns the enriched contract fields.

Runs fully in-process so the suite does not depend on a separately running backend.
A dynamically collisional debris case is injected so CDM-only fields are always present.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from scripts.collision_case_builder import build_dynamic_collision_case


@pytest.fixture(scope="module")
def snapshot():
    import backend.main as backend_main

    backend_main = importlib.reload(backend_main)
    backend_main.reset_world(load_defaults=True)
    client = TestClient(backend_main.app)

    base = client.get("/api/visualization/snapshot").json()
    sats = base.get("satellites", [])
    assert sats, "Expected at least one satellite in default world"

    case = build_dynamic_collision_case(sats[0], deb_id="DEB-SNAPSHOT-CONTRACT-001")
    resp = client.post(
        "/api/telemetry",
        json={"timestamp": base["timestamp"], "objects": [case.telemetry_object()]},
    )
    resp.raise_for_status()
    return client.get("/api/visualization/snapshot").json()


def test_snapshot_has_ground_stations(snapshot):
    assert "ground_stations" in snapshot
    assert isinstance(snapshot["ground_stations"], list)
    assert len(snapshot["ground_stations"]) > 0
    gs = snapshot["ground_stations"][0]
    assert "id" in gs and "lat" in gs and "lon" in gs


def test_snapshot_satellite_has_tracks(snapshot):
    sats = snapshot.get("satellites", [])
    assert sats
    sat = sats[0]
    assert "past_track" in sat
    assert "future_track" in sat
    assert isinstance(sat["past_track"], list)
    assert isinstance(sat["future_track"], list)


def test_snapshot_cdm_has_approach_angle(snapshot):
    cdms = snapshot.get("cdm_warnings", [])
    assert cdms
    cdm = cdms[0]
    assert "approach_angle_deg" in cdm
    assert "relative_speed_kms" in cdm


def test_snapshot_has_metrics_history(snapshot):
    assert "metrics_history" in snapshot
    assert isinstance(snapshot["metrics_history"], list)


def test_snapshot_debris_is_tuple_format(snapshot):
    cloud = snapshot.get("debris_cloud", [])
    assert cloud
    item = cloud[0]
    assert isinstance(item, list)
    assert len(item) == 4


def test_snapshot_has_exponential_uptime(snapshot):
    assert "fleet_uptime_exp" in snapshot
    assert 0.0 <= snapshot["fleet_uptime_exp"] <= 1.0
