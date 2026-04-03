"""Run a compact exceptional-case verification matrix in-process."""
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
    case = build_dynamic_collision_case(target, deb_id=f'DEB-RUNNER-{step_seconds:03d}')
    client.post('/api/telemetry', json={'timestamp': snapshot['timestamp'], 'objects': [case.telemetry_object()]}).raise_for_status()
    snap_after = client.get('/api/visualization/snapshot').json()
    cdm = next(c for c in snap_after.get('cdm_warnings', []) if c.get('deb_id') == case.deb_id)
    total_steps = int((cdm['tca_seconds'] + 120.0) // step_seconds) + 2
    total_collisions = 0
    total_maneuvers = 0
    for _ in range(total_steps):
        data = client.post('/api/simulate/step', json={'step_seconds': step_seconds}).json()
        total_collisions += int(data.get('collisions_detected', 0))
        total_maneuvers += int(data.get('maneuvers_executed', 0))
    return total_collisions, total_maneuvers


def main():
    print('== Exceptional case matrix ==')
    for step in (5, 60, 300):
        collisions, maneuvers = _run_dynamic_case(step)
        print(f'dynamic_case step={step}s -> collisions={collisions}, maneuvers={maneuvers}')

    backend_main = _reload_backend()
    scheduler = backend_main.scheduler
    sm = backend_main.sm
    sat_id = sm.sat_ids[0]

    scheduler.gn.has_los_any_station = lambda *a, **k: (False, [])
    scheduler.gn.find_next_contact_window = lambda *a, **k: (20.0, 120.0, 'GS-TEST')
    cmd = ManeuverCommand(sat_id, 'RUN-ALLOW', sm.timestamp + timedelta(seconds=120), [0.0, 0.0, 0.001], 'MANUAL')
    ok, msg, _ = scheduler.schedule(cmd)
    print(f'future_contact_before_deadline -> ok={ok}, msg={msg}')

    backend_main = _reload_backend()
    scheduler = backend_main.scheduler
    sm = backend_main.sm
    sat_id = sm.sat_ids[0]
    scheduler.gn.has_los_any_station = lambda *a, **k: (False, [])
    scheduler.gn.find_next_contact_window = lambda *a, **k: (200.0, 120.0, 'GS-LATE')
    cmd = ManeuverCommand(sat_id, 'RUN-REJECT', sm.timestamp + timedelta(seconds=90), [0.0, 0.0, 0.001], 'MANUAL')
    ok, msg, _ = scheduler.schedule(cmd)
    print(f'future_contact_after_deadline -> ok={ok}, msg={msg}')

    backend_main = _reload_backend()
    scheduler = backend_main.scheduler
    sm = backend_main.sm
    sat_id = sm.sat_ids[0]
    scheduler.gn.has_los_any_station = lambda *a, **k: (True, ['GS-NOW'])
    burn1 = ManeuverCommand(sat_id, 'RUN-CD-1', sm.timestamp + timedelta(seconds=SIGNAL_DELAY + 30), [0.0, 0.0, 0.001], 'MANUAL')
    ok1, msg1, _ = scheduler.schedule(burn1)
    burn2 = ManeuverCommand(sat_id, 'RUN-CD-2', burn1.burn_time + timedelta(seconds=COOLDOWN_SECONDS - 1), [0.0, 0.0, 0.001], 'MANUAL')
    ok2, msg2, _ = scheduler.schedule(burn2)
    print(f'cooldown_first -> ok={ok1}, msg={msg1}')
    print(f'cooldown_second -> ok={ok2}, msg={msg2}')


if __name__ == '__main__':
    main()


# Note: a step=300s run is included to verify event-driven stepping remains collision-safe even for very coarse fast-forward inputs.
