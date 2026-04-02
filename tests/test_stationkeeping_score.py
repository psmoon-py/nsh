"""
Test: station keeping uptime scoring (raw and exponential).
"""
import numpy as np
import pytest
from datetime import datetime, timezone, timedelta
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.engine.state_manager import StateManager
from backend.engine.station_keeping import StationKeepingManager
from backend.engine.scheduler import ManeuverScheduler
from backend.engine.ground_stations import GroundStationNetwork


def _make_sk():
    sm = StateManager()
    sm.timestamp  = datetime(2026, 3, 12, 8, 0, 0, tzinfo=timezone.utc)
    sm.positions  = np.array([[6778.0, 0.0, 0.0]])
    sm.velocities = np.array([[0.0, 7.785, 0.0]])
    sm.ids        = ['SAT-001']
    sm._id_to_idx = {'SAT-001': 0}
    sm.sat_ids    = ['SAT-001']
    sm.deb_ids    = []
    sm.objects    = {'SAT-001': {'type': 'SATELLITE', 'status': 'NOMINAL', 'drift_km': 0.0}}
    sm.fuel       = {'SAT-001': 50.0}
    sm.masses     = {'SAT-001': 550.0}
    sm.last_burn_time = {'SAT-001': None}
    sm.nominal_slots  = {'SAT-001': np.array([6778.0, 0.0, 0.0])}
    sm.nominal_slot_vels = {'SAT-001': np.array([0.0, 7.785, 0.0])}
    sm.active_cdms = []

    gn = GroundStationNetwork()
    gn.load_defaults()
    sched = ManeuverScheduler(sm, gn)
    sk    = StationKeepingManager(sm, sched)
    return sm, sk


def test_in_slot_uptime_is_one():
    sm, sk = _make_sk()
    sk.update_all_statuses()
    assert sk.get_uptime_fraction('SAT-001') == 1.0
    assert sk.get_uptime_exponential_score('SAT-001') == 1.0


def test_out_of_slot_degrades_uptime():
    sm, sk = _make_sk()
    # Move satellite 20 km away from nominal slot (outside 10 km box)
    sm.positions[0] = np.array([6778.0, 20.0, 0.0])
    sk.update_all_statuses()
    assert sm.objects['SAT-001']['status'] == 'OUT_OF_SLOT'

    # Advance time by 1 hour
    sm.timestamp = sm.timestamp + timedelta(hours=1)
    sk.update_all_statuses()

    uptime = sk.get_uptime_fraction('SAT-001')
    assert uptime < 1.0, f"Uptime {uptime} should be <1.0 after 1h out-of-slot"

    exp_score = sk.get_uptime_exponential_score('SAT-001')
    assert exp_score < 1.0


def test_recovery_not_triggered_during_active_threat():
    sm, sk = _make_sk()
    # Set satellite out-of-slot
    sm.positions[0] = np.array([6778.0, 20.0, 0.0])
    sm.objects['SAT-001']['status'] = 'OUT_OF_SLOT'

    # Inject active CRITICAL CDM
    sm.active_cdms = [{
        'sat_id': 'SAT-001', 'deb_id': 'DEB-X',
        'risk_level': 'CRITICAL', 'tca_seconds': 120.0, 'miss_distance_km': 0.05,
    }]

    # Recovery should be blocked
    sk.trigger_recovery_if_needed('SAT-001')
    assert len(sk.scheduler.queue) == 0, "Recovery fired during active CRITICAL threat — should not"
