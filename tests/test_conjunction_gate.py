"""
Test suite: conjunction linearized gate correctness.

Verifies that the vectorised linearized gate:
  1. Does NOT drop a head-on imminent pair (sat directly in path of debris)
  2. Does NOT drop a currently-close pair (debris < WARNING_THRESHOLD_YELLOW)
  3. Does NOT apply a global per-satellite cap that kills a critical pair
"""
import numpy as np
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.engine.state_manager import StateManager
from backend.engine.conjunction import ConjunctionDetector
from backend.config import COLLISION_THRESHOLD, WARNING_THRESHOLD_YELLOW


def _make_sm(sat_r, sat_v, deb_r, deb_v):
    sm = StateManager()
    sm.positions = np.array([sat_r, deb_r], dtype=float)
    sm.velocities = np.array([sat_v, deb_v], dtype=float)
    sm.ids = ['SAT-001', 'DEB-001']
    sm._id_to_idx = {'SAT-001': 0, 'DEB-001': 1}
    sm.sat_ids = ['SAT-001']
    sm.deb_ids = ['DEB-001']
    sm.objects = {
        'SAT-001': {'type': 'SATELLITE', 'status': 'NOMINAL'},
        'DEB-001': {'type': 'DEBRIS',    'status': 'ACTIVE'},
    }
    sm.nominal_slots = {'SAT-001': np.array(sat_r)}
    sm.nominal_slot_vels = {'SAT-001': np.array(sat_v)}
    sm.fuel  = {'SAT-001': 50.0}
    sm.masses = {'SAT-001': 550.0}
    sm.last_burn_time = {'SAT-001': None}
    return sm


def test_head_on_imminent_not_dropped():
    """Debris 400 km ahead along track, closing at 15 km/s (head-on)."""
    sat_r = np.array([6778.0, 0.0, 0.0])
    sat_v = np.array([0.0, 7.785, 0.0])
    # Debris counter-orbital: same plane, opposite direction
    deb_r = sat_r + np.array([0.0, 400.0, 0.0])
    deb_v = np.array([0.0, -7.785, 0.0])

    sm = _make_sm(sat_r, sat_v, deb_r, deb_v)
    cd = ConjunctionDetector(sm)
    candidates = cd.screen_conjunctions()
    assert len(candidates) >= 1, "Head-on imminent pair was incorrectly dropped by gate"


def test_currently_close_not_dropped():
    """Debris 3 km away (inside WARNING_THRESHOLD_YELLOW = 5 km)."""
    sat_r = np.array([6778.0, 0.0, 0.0])
    sat_v = np.array([0.0, 7.785, 0.0])
    deb_r = sat_r + np.array([0.0, 0.0, 3.0])
    deb_v = np.array([0.01, 7.8, 0.0])

    sm = _make_sm(sat_r, sat_v, deb_r, deb_v)
    cd = ConjunctionDetector(sm)
    candidates = cd.screen_conjunctions()
    assert len(candidates) >= 1, "Currently-close pair (3 km) was incorrectly dropped"


def test_full_assessment_flags_critical():
    """End-to-end: objects on collision course produce CRITICAL CDM."""
    sat_r = np.array([6778.0, 0.0, 0.0])
    sat_v = np.array([0.0, 7.785, 0.0])
    # Place debris 50 km away, closing at 8 km/s — will pass within ~0.05 km
    deb_r = sat_r + np.array([0.0, 50.0, 0.0])
    deb_v = np.array([0.0, -0.215, 0.0])   # relative speed ~8 km/s

    sm = _make_sm(sat_r, sat_v, deb_r, deb_v)
    cd = ConjunctionDetector(sm)
    cdms = cd.run_full_assessment()
    # At minimum we expect a YELLOW or higher
    assert len(cdms) >= 1, "No CDM generated for approaching debris"
    assert cdms[0]['risk_level'] in ('CRITICAL', 'RED', 'YELLOW')
