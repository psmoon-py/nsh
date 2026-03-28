"""
Efficient conjunction detection using KD-Tree spatial indexing.
Avoids O(N²) by screening with spatial tree, then refining close pairs.

FIX: Uses adaptive coarse step based on relative velocity to avoid
missing high-speed close approaches. Previous 60s fixed step would
miss a head-on approach (15 km/s closing) where objects are <1000km apart.
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
        """KD-tree screening: find all sat-debris pairs within SCREENING_RADIUS."""
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
                dist = float(np.linalg.norm(
                    self.sm.positions[sat_idx] - self.sm.positions[deb_idx]
                ))
                close_pairs.append((
                    self.sm.ids[sat_idx], self.sm.ids[deb_idx], dist
                ))

        return close_pairs

    def _compute_closing_speed(self, sat_r, sat_v, deb_r, deb_v):
        """Compute relative closing speed between two objects."""
        rel_pos = np.array(deb_r) - np.array(sat_r)
        rel_vel = np.array(deb_v) - np.array(sat_v)
        dist = np.linalg.norm(rel_pos)
        if dist < 1e-10:
            return float(np.linalg.norm(rel_vel))
        # Closing speed = component of relative velocity along the line of sight
        closing = -np.dot(rel_vel, rel_pos / dist)
        return max(float(closing), float(np.linalg.norm(rel_vel)) * 0.1)

    def predict_conjunction(self, sat_id, deb_id, horizon_seconds=PREDICTION_HORIZON):
        """Predict closest approach between a satellite and debris.
        
        Uses ADAPTIVE step sizing:
        - Computes relative velocity to determine safe coarse step
        - For high-speed approaches (>5 km/s closing), uses ~10s coarse steps
        - For slow approaches (<1 km/s), uses standard 60s coarse steps
        - Fine pass always uses 1s steps in ±120s window around minimum
        """
        sat_r, sat_v = self.sm.get_state(sat_id)
        deb_r, deb_v = self.sm.get_state(deb_id)

        # Compute closing speed to determine safe step size
        closing_speed = self._compute_closing_speed(sat_r, sat_v, deb_r, deb_v)
        current_dist = float(np.linalg.norm(np.array(sat_r) - np.array(deb_r)))

        # Adaptive coarse step: ensure we don't skip more than half the current distance
        # per step. This guarantees we catch the minimum.
        if closing_speed > 0.1:  # > 100 m/s
            # Objects moving at closing_speed km/s, we want step < distance / (2 * speed)
            safe_step = max(1.0, min(60.0, current_dist / (2.0 * closing_speed)))
        else:
            safe_step = 60.0

        # For very close objects (< 50 km), use very fine steps immediately
        if current_dist < 50.0:
            safe_step = min(safe_step, 2.0)
        elif current_dist < 200.0:
            safe_step = min(safe_step, 10.0)

        coarse_dt = safe_step
        n_coarse = int(horizon_seconds / coarse_dt)
        # Cap at 50000 steps max to prevent memory issues
        if n_coarse > 50000:
            coarse_dt = horizon_seconds / 50000.0
            n_coarse = 50000

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

            # Early exit: if we found something very close and now it's moving away
            if dist > min_dist * 3 and min_dist < WARNING_THRESHOLD_YELLOW and step > 10:
                break

            if step < n_coarse:
                sx, sy, sz, svx, svy, svz = propagate_single(
                    sx, sy, sz, svx, svy, svz, coarse_dt, RK4_TIMESTEP
                )
                dx, dy, dz, dvx, dvy, dvz = propagate_single(
                    dx, dy, dz, dvx, dvy, dvz, coarse_dt, RK4_TIMESTEP
                )

        # Fine pass if coarse found something interesting
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

        # Classify risk
        if min_dist < COLLISION_THRESHOLD:
            risk = "CRITICAL"
        elif min_dist < WARNING_THRESHOLD_RED:
            risk = "RED"
        elif min_dist < WARNING_THRESHOLD_YELLOW:
            risk = "YELLOW"
        else:
            risk = "GREEN"

        return float(min_t), float(min_dist), risk

    def run_full_assessment(self):
        """Full conjunction assessment pipeline: screen → predict → classify."""
        close_pairs = self.screen_conjunctions()
        cdm_warnings = []

        for sat_id, deb_id, current_dist in close_pairs:
            tca, min_dist, risk = self.predict_conjunction(sat_id, deb_id)
            if risk in ("CRITICAL", "RED", "YELLOW"):
                cdm_warnings.append({
                    "sat_id": sat_id,
                    "deb_id": deb_id,
                    "tca_seconds": float(tca),
                    "miss_distance_km": float(min_dist),
                    "risk_level": risk,
                    "current_distance_km": float(current_dist),
                })

        risk_order = {"CRITICAL": 0, "RED": 1, "YELLOW": 2}
        cdm_warnings.sort(key=lambda w: (risk_order[w["risk_level"]], w["tca_seconds"]))
        return cdm_warnings
