"""
Efficient conjunction detection using KD-Tree spatial indexing.
Avoids O(N²) by screening with spatial tree, then refining close pairs.
"""
import numpy as np
from scipy.spatial import KDTree
from backend.config import (
    COLLISION_THRESHOLD, SCREENING_RADIUS,
    WARNING_THRESHOLD_RED, WARNING_THRESHOLD_YELLOW,
    PREDICTION_HORIZON, RK4_TIMESTEP,
)
from backend.physics.propagator import propagate_single


class ConjunctionDetector:
    def __init__(self, state_manager):
        self.sm = state_manager

    def screen_conjunctions(self):
        sat_indices = self.sm.get_satellite_indices()
        deb_indices = self.sm.get_debris_indices()
        if not sat_indices or not deb_indices:
            return []
        sat_positions = self.sm.positions[sat_indices]
        deb_positions = self.sm.positions[deb_indices]
        tree = KDTree(deb_positions)
        close_pairs = []
        for i, sat_idx in enumerate(sat_indices):
            nearby = tree.query_ball_point(sat_positions[i], r=SCREENING_RADIUS)
            for j in nearby:
                deb_idx = deb_indices[j]
                dist = np.linalg.norm(
                    self.sm.positions[sat_idx] - self.sm.positions[deb_idx]
                )
                close_pairs.append((
                    self.sm.ids[sat_idx], self.sm.ids[deb_idx], dist
                ))
        return close_pairs

    def predict_conjunction(self, sat_id, deb_id, horizon_seconds=PREDICTION_HORIZON):
        sat_r, sat_v = self.sm.get_state(sat_id)
        deb_r, deb_v = self.sm.get_state(deb_id)
        coarse_dt = 60.0
        n_coarse = int(horizon_seconds / coarse_dt)
        min_dist = float("inf")
        min_t = 0.0
        sx, sy, sz, svx, svy, svz = *sat_r, *sat_v
        dx, dy, dz, dvx, dvy, dvz = *deb_r, *deb_v
        for step in range(n_coarse + 1):
            t = step * coarse_dt
            dist = np.sqrt((sx - dx) ** 2 + (sy - dy) ** 2 + (sz - dz) ** 2)
            if dist < min_dist:
                min_dist = dist
                min_t = t
            if step < n_coarse:
                sx, sy, sz, svx, svy, svz = propagate_single(
                    sx, sy, sz, svx, svy, svz, coarse_dt, RK4_TIMESTEP
                )
                dx, dy, dz, dvx, dvy, dvz = propagate_single(
                    dx, dy, dz, dvx, dvy, dvz, coarse_dt, RK4_TIMESTEP
                )
        if min_dist < WARNING_THRESHOLD_YELLOW:
            fine_start = max(0, min_t - 120)
            fine_end = min(horizon_seconds, min_t + 120)
            sx, sy, sz, svx, svy, svz = *sat_r, *sat_v
            dx, dy, dz, dvx, dvy, dvz = *deb_r, *deb_v
            if fine_start > 0:
                sx, sy, sz, svx, svy, svz = propagate_single(
                    sx, sy, sz, svx, svy, svz, fine_start, RK4_TIMESTEP
                )
                dx, dy, dz, dvx, dvy, dvz = propagate_single(
                    dx, dy, dz, dvx, dvy, dvz, fine_start, RK4_TIMESTEP
                )
            fine_dt = 1.0
            n_fine = int((fine_end - fine_start) / fine_dt)
            for step in range(n_fine + 1):
                t = fine_start + step * fine_dt
                dist = np.sqrt((sx - dx) ** 2 + (sy - dy) ** 2 + (sz - dz) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    min_t = t
                if step < n_fine:
                    sx, sy, sz, svx, svy, svz = propagate_single(
                        sx, sy, sz, svx, svy, svz, fine_dt, fine_dt
                    )
                    dx, dy, dz, dvx, dvy, dvz = propagate_single(
                        dx, dy, dz, dvx, dvy, dvz, fine_dt, fine_dt
                    )
        if min_dist < COLLISION_THRESHOLD:
            risk = "CRITICAL"
        elif min_dist < WARNING_THRESHOLD_RED:
            risk = "RED"
        elif min_dist < WARNING_THRESHOLD_YELLOW:
            risk = "YELLOW"
        else:
            risk = "GREEN"
        return min_t, min_dist, risk

    def run_full_assessment(self):
        close_pairs = self.screen_conjunctions()
        cdm_warnings = []
        for sat_id, deb_id, current_dist in close_pairs:
            tca, min_dist, risk = self.predict_conjunction(sat_id, deb_id)
            if risk in ("CRITICAL", "RED", "YELLOW"):
                cdm_warnings.append({
                    "sat_id": sat_id,
                    "deb_id": deb_id,
                    "tca_seconds": tca,
                    "miss_distance_km": min_dist,
                    "risk_level": risk,
                    "current_distance_km": current_dist,
                })
        risk_order = {"CRITICAL": 0, "RED": 1, "YELLOW": 2}
        cdm_warnings.sort(key=lambda w: (risk_order[w["risk_level"]], w["tca_seconds"]))
        return cdm_warnings
