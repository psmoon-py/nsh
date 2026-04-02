"""Utility to construct a dynamically collisional debris state.

This copy is bundled with the validation suite so the seeded collision checks
remain self-contained even if the backend patch bundle has not yet been merged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from scipy.optimize import least_squares

from backend.physics.propagator import propagate_single


@dataclass
class CollisionCase:
    sat_id: str
    deb_id: str
    tca_seconds: float
    offset_km: float
    basis_name: str
    miss_distance_km: float
    relative_speed_kms: float
    debris_r: np.ndarray
    debris_v: np.ndarray

    def telemetry_object(self) -> Dict:
        return {
            "id": self.deb_id,
            "type": "DEBRIS",
            "r": {"x": float(self.debris_r[0]), "y": float(self.debris_r[1]), "z": float(self.debris_r[2])},
            "v": {"x": float(self.debris_v[0]), "y": float(self.debris_v[1]), "z": float(self.debris_v[2])},
        }


def _propagate(r: np.ndarray, v: np.ndarray, total_time: float, dt: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    out = propagate_single(float(r[0]), float(r[1]), float(r[2]), float(v[0]), float(v[1]), float(v[2]), float(total_time), float(dt))
    return np.array(out[:3], dtype=float), np.array(out[3:], dtype=float)


def _basis_vectors(r0: np.ndarray, v0: np.ndarray) -> Dict[str, np.ndarray]:
    r_hat = r0 / np.linalg.norm(r0)
    h_hat = np.cross(r0, v0)
    h_hat = h_hat / np.linalg.norm(h_hat)
    t_hat = np.cross(h_hat, r_hat)
    return {
        "radial": r_hat,
        "along_track": t_hat,
        "cross_track": h_hat,
        "radial_along": (r_hat + t_hat) / np.linalg.norm(r_hat + t_hat),
        "along_cross": (t_hat + h_hat) / np.linalg.norm(t_hat + h_hat),
    }


def _sample_min_miss(sat_r0: np.ndarray, sat_v0: np.ndarray, deb_r0: np.ndarray, deb_v0: np.ndarray, horizon_seconds: float, dt: float = 1.0) -> Tuple[float, float, float]:
    best_t = 0.0
    best_miss = float("inf")
    best_rel_speed = 0.0
    t = 0.0
    while t <= horizon_seconds + 1e-9:
        sr, sv = _propagate(sat_r0, sat_v0, t, dt)
        dr, dv = _propagate(deb_r0, deb_v0, t, dt)
        miss = float(np.linalg.norm(dr - sr))
        if miss < best_miss:
            best_miss = miss
            best_t = t
            best_rel_speed = float(np.linalg.norm(dv - sv))
        t += dt
    return best_t, best_miss, best_rel_speed


def _candidate_case(sat_id: str, sat_r0: np.ndarray, sat_v0: np.ndarray, deb_id: str, tca_seconds: float, offset_km: float, basis_name: str) -> CollisionCase | None:
    basis = _basis_vectors(sat_r0, sat_v0)[basis_name]
    deb_r0 = sat_r0 + basis * offset_km
    sat_r_tca, _ = _propagate(sat_r0, sat_v0, tca_seconds, dt=1.0)

    def residual(v_guess: np.ndarray) -> np.ndarray:
        deb_r_tca, _ = _propagate(deb_r0, v_guess, tca_seconds, dt=1.0)
        return deb_r_tca - sat_r_tca

    initial_guess = sat_v0 - basis * (offset_km / max(tca_seconds, 1.0))
    result = least_squares(residual, initial_guess, xtol=1e-11, ftol=1e-11, gtol=1e-11, max_nfev=80)
    if not result.success:
        return None

    deb_v0 = np.array(result.x, dtype=float)
    t_min, miss_km, rel_speed = _sample_min_miss(sat_r0, sat_v0, deb_r0, deb_v0, horizon_seconds=tca_seconds + 30.0, dt=1.0)
    if miss_km > 0.01 or abs(t_min - tca_seconds) > 30.0 or rel_speed < 0.005 or rel_speed > 0.2:
        return None

    return CollisionCase(
        sat_id=sat_id,
        deb_id=deb_id,
        tca_seconds=float(t_min),
        offset_km=float(offset_km),
        basis_name=basis_name,
        miss_distance_km=float(miss_km),
        relative_speed_kms=float(rel_speed),
        debris_r=deb_r0,
        debris_v=deb_v0,
    )


def build_dynamic_collision_case(snapshot_satellite: Dict, deb_id: str = "DEB-DYN-COLLIDER-001") -> CollisionCase:
    sat_id = snapshot_satellite["id"]
    sat_r0 = np.array([snapshot_satellite["r"]["x"], snapshot_satellite["r"]["y"], snapshot_satellite["r"]["z"]], dtype=float)
    sat_v0 = np.array([snapshot_satellite["v"]["x"], snapshot_satellite["v"]["y"], snapshot_satellite["v"]["z"]], dtype=float)

    search_order: List[Tuple[float, float, str]] = [
        (600.0, 20.0, "radial"),
        (600.0, 10.0, "radial"),
        (600.0, 20.0, "cross_track"),
        (900.0, 10.0, "cross_track"),
        (900.0, 10.0, "along_track"),
        (1200.0, 10.0, "cross_track"),
        (1200.0, 20.0, "radial_along"),
    ]

    for tca_seconds, offset_km, basis_name in search_order:
        case = _candidate_case(sat_id, sat_r0, sat_v0, deb_id, tca_seconds, offset_km, basis_name)
        if case is not None:
            return case

    raise RuntimeError("Could not construct a dynamically collisional debris case")
