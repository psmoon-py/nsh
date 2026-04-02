"""
Test: burns execute at their exact boundary time, not end-of-step.
"""
import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_burn_boundary_is_exact():
    """
    Simulate a 30s step with a burn at t=16s.
    The burn must be applied at exactly t=16s (velocity changes at boundary),
    not at t=30s (end of sub-step).
    """
    from backend.engine.state_manager import StateManager
    from backend.engine.scheduler import ManeuverScheduler, ManeuverCommand
    from backend.engine.ground_stations import GroundStationNetwork

    sm = StateManager()
    sm.timestamp = datetime(2026, 3, 12, 8, 0, 0, tzinfo=timezone.utc)
    sm.positions  = np.array([[6778.0, 0.0, 0.0]])
    sm.velocities = np.array([[0.0, 7.785, 0.0]])
    sm.ids        = ['SAT-001']
    sm._id_to_idx = {'SAT-001': 0}
    sm.sat_ids    = ['SAT-001']
    sm.deb_ids    = []
    sm.objects    = {'SAT-001': {'type': 'SATELLITE', 'status': 'NOMINAL'}}
    sm.fuel       = {'SAT-001': 50.0}
    sm.masses     = {'SAT-001': 550.0}
    sm.last_burn_time = {'SAT-001': None}
    sm.nominal_slots  = {'SAT-001': np.array([6778.0, 0.0, 0.0])}
    sm.nominal_slot_vels = {'SAT-001': np.array([0.0, 7.785, 0.0])}

    gn = GroundStationNetwork()
    gn.load_defaults()
    sched = ManeuverScheduler(sm, gn)

    burn_time = sm.timestamp + timedelta(seconds=16)
    dv = np.array([0.0, 0.001, 0.0])   # 1 m/s prograde
    cmd = ManeuverCommand('SAT-001', 'TEST_BURN', burn_time, dv, 'EVASION')
    cmd.status = 'PENDING'
    sched.queue.append(cmd)

    # Execute burns in the window [t=0, t=16] — should execute exactly 1
    old_t = sm.timestamp
    boundary_t = old_t + timedelta(seconds=16)
    count = sched.execute_due_maneuvers(old_t, boundary_t)
    assert count == 1, f"Expected 1 burn at boundary t=16s, got {count}"
    assert cmd.status == 'EXECUTED'

    # Execute burns in the window [t=16, t=30] — should execute 0
    count2 = sched.execute_due_maneuvers(boundary_t, boundary_t + timedelta(seconds=14))
    assert count2 == 0, f"Expected 0 burns in [16,30]s, got {count2}"
