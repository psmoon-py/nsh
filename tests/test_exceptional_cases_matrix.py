from __future__ import annotations

import importlib
from datetime import timedelta

from fastapi.testclient import TestClient

from backend.config import COOLDOWN_SECONDS, SIGNAL_DELAY
from backend.engine.scheduler import ManeuverCommand
from scripts.collision_case_builder import build_dynamic_collision_case


def _reload_backend():
    import backend.main as backend_main

    backend_main = importlib.reload(backend_main)
    backend_main.reset_world(load_defaults=True)
    return backend_main


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


def _run_dynamic_case(step_seconds: int):
    backend_main = _reload_backend()
    client = TestClient(backend_main.app)
    snapshot = client.get('/api/visualization/snapshot').json()
    target = snapshot['satellites'][0]
    _reduce_world_to_one_satellite(backend_main, target['id'])
    client = TestClient(backend_main.app)
    snapshot = client.get('/api/visualization/snapshot').json()
    target = snapshot['satellites'][0]
    initial_fuel = float(target['fuel_kg'])

    case = build_dynamic_collision_case(target, deb_id=f'DEB-STEP-{step_seconds:03d}')
    telemetry = client.post('/api/telemetry', json={'timestamp': snapshot['timestamp'], 'objects': [case.telemetry_object()]})
    telemetry.raise_for_status()

    snap_after = client.get('/api/visualization/snapshot').json()
    cdm = next(c for c in snap_after.get('cdm_warnings', []) if c.get('deb_id') == case.deb_id)

    total_steps = int((cdm['tca_seconds'] + 120.0) // step_seconds) + 2
    total_collisions = 0
    total_maneuvers = 0
    for _ in range(total_steps):
        resp = client.post('/api/simulate/step', json={'step_seconds': step_seconds})
        resp.raise_for_status()
        data = resp.json()
        total_collisions += int(data.get('collisions_detected', 0))
        total_maneuvers += int(data.get('maneuvers_executed', 0))

    final_snapshot = client.get('/api/visualization/snapshot').json()
    final_sat = next(s for s in final_snapshot['satellites'] if s['id'] == target['id'])
    fuel_used = initial_fuel - float(final_sat['fuel_kg'])
    return {'collisions': total_collisions, 'maneuvers': total_maneuvers, 'fuel_used': fuel_used}


def test_dynamic_case_step_invariance():
    fine = _run_dynamic_case(5)
    coarse = _run_dynamic_case(60)
    very_coarse = _run_dynamic_case(300)
    assert fine['collisions'] == 0
    assert coarse['collisions'] == 0
    assert very_coarse['collisions'] == 0
    assert fine['maneuvers'] >= 1
    assert coarse['maneuvers'] >= 1
    assert very_coarse['maneuvers'] >= 1
    assert fine['fuel_used'] > 0.0
    assert coarse['fuel_used'] > 0.0
    assert very_coarse['fuel_used'] > 0.0


def test_scheduler_accepts_future_contact_before_deadline():
    backend_main = _reload_backend()
    scheduler = backend_main.scheduler
    sm = backend_main.sm
    sat_id = sm.sat_ids[0]

    scheduler.gn.has_los_any_station = lambda *a, **k: (False, [])
    scheduler.gn.find_next_contact_window = lambda *a, **k: (20.0, 120.0, 'GS-TEST')

    cmd = ManeuverCommand(sat_id=sat_id, burn_id='MAN-ALLOW-001', burn_time=sm.timestamp + timedelta(seconds=120), delta_v=[0.0,0.0,0.001], burn_type='MANUAL')
    ok, msg, validation = scheduler.schedule(cmd)
    assert ok, msg
    assert validation['ground_station_los'] is True
    assert cmd.upload_station_id == 'GS-TEST'


def test_scheduler_rejects_contact_after_deadline():
    backend_main = _reload_backend()
    scheduler = backend_main.scheduler
    sm = backend_main.sm
    sat_id = sm.sat_ids[0]

    scheduler.gn.has_los_any_station = lambda *a, **k: (False, [])
    scheduler.gn.find_next_contact_window = lambda *a, **k: (200.0, 120.0, 'GS-LATE')

    cmd = ManeuverCommand(sat_id=sat_id, burn_id='MAN-REJECT-001', burn_time=sm.timestamp + timedelta(seconds=90), delta_v=[0.0,0.0,0.001], burn_type='MANUAL')
    ok, msg, _ = scheduler.schedule(cmd)
    assert not ok
    assert 'deadline' in msg.lower() or 'no ground station los' in msg.lower()


def test_scheduler_rejects_cooldown_conflict():
    backend_main = _reload_backend()
    scheduler = backend_main.scheduler
    sm = backend_main.sm
    sat_id = sm.sat_ids[0]

    scheduler.gn.has_los_any_station = lambda *a, **k: (True, ['GS-NOW'])

    burn1 = ManeuverCommand(sat_id=sat_id, burn_id='MAN-CD-001', burn_time=sm.timestamp + timedelta(seconds=SIGNAL_DELAY + 30), delta_v=[0.0,0.0,0.001], burn_type='MANUAL')
    ok1, msg1, _ = scheduler.schedule(burn1)
    assert ok1, msg1

    burn2 = ManeuverCommand(sat_id=sat_id, burn_id='MAN-CD-002', burn_time=burn1.burn_time + timedelta(seconds=COOLDOWN_SECONDS - 1), delta_v=[0.0,0.0,0.001], burn_type='MANUAL')
    ok2, msg2, _ = scheduler.schedule(burn2)
    assert not ok2
    assert 'cooldown' in msg2.lower()


def test_receding_post_tca_warning_is_suppressed():
    backend_main = _reload_backend()
    client = TestClient(backend_main.app)
    snapshot = client.get('/api/visualization/snapshot').json()
    target = snapshot['satellites'][0]
    _reduce_world_to_one_satellite(backend_main, target['id'])
    client = TestClient(backend_main.app)
    snapshot = client.get('/api/visualization/snapshot').json()
    target = snapshot['satellites'][0]

    case = build_dynamic_collision_case(target, deb_id='DEB-POST-TCA-001')
    client.post('/api/telemetry', json={'timestamp': snapshot['timestamp'], 'objects': [case.telemetry_object()]}).raise_for_status()

    # Advance well past TCA. Residual active CDMs for a now-receding pair should be suppressed.
    for _ in range(4):
        client.post('/api/simulate/step', json={'step_seconds': 300}).raise_for_status()

    final_snapshot = client.get('/api/visualization/snapshot').json()
    residual = [c for c in final_snapshot.get('cdm_warnings', []) if c.get('deb_id') == case.deb_id]
    assert residual == []
