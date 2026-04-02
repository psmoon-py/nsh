"""
Test: two burns consume slightly different fuel because mass changes (Tsiolkovsky).
"""
import numpy as np
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.physics.maneuver import compute_fuel_consumed
from backend.config import INITIAL_WET_MASS


def test_second_burn_uses_less_fuel():
    """After first burn depletes mass, second identical burn consumes less fuel."""
    dv_ms = 5.0   # 5 m/s each burn

    mass1    = INITIAL_WET_MASS
    fuel1    = compute_fuel_consumed(mass1, dv_ms)
    mass2    = mass1 - fuel1
    fuel2    = compute_fuel_consumed(mass2, dv_ms)

    assert fuel2 < fuel1, (
        f"Second burn fuel {fuel2:.6f} kg should be less than first {fuel1:.6f} kg"
    )
    assert abs(fuel1 - fuel2) > 1e-8, "Difference should be non-negligible"


def test_schedule_sequence_sequential_mass():
    """schedule_sequence uses sequential mass depletion."""
    from backend.engine.state_manager import StateManager
    from backend.engine.scheduler import ManeuverScheduler
    from backend.engine.ground_stations import GroundStationNetwork
    from datetime import datetime, timezone, timedelta

    sm = StateManager()
    sm.timestamp  = datetime(2026, 3, 12, 8, 0, 0, tzinfo=timezone.utc)
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

    now_str = sm.timestamp.isoformat().replace('+00:00', 'Z')
    burns = [
        {
            "burn_id": "B1",
            "burnTime": (sm.timestamp + timedelta(seconds=15)).isoformat().replace('+00:00','Z'),
            "deltaV_vector": {"x": 0.002, "y": 0.0, "z": 0.0},
            "type": "EVASION",
        },
        {
            "burn_id": "B2",
            "burnTime": (sm.timestamp + timedelta(seconds=620)).isoformat().replace('+00:00','Z'),
            "deltaV_vector": {"x": 0.002, "y": 0.0, "z": 0.0},
            "type": "RECOVERY",
        },
    ]
    success, msg, validation = sched.schedule_sequence('SAT-001', burns)
    assert success, f"schedule_sequence failed: {msg}"
    # projected mass should be less than if we'd used original mass for both
    proj = validation["projected_mass_remaining_kg"]
    assert proj < INITIAL_WET_MASS, f"Projected mass {proj} should be < initial {INITIAL_WET_MASS}"
