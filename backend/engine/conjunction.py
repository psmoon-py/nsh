"""
Efficient conjunction detection using vectorized linearized gate + two-phase TCA refinement.

Architecture:
  Gate 1 — Linearized forecast gate (fully vectorized NumPy):
    For each satellite, compute linear TCA miss distance against all debris.
    Keep candidates where: linear_miss < LINEAR_GATE_MAX_MISS_KM
                        or current_dist < WARNING_THRESHOLD_YELLOW
                        or (linear_tca < 1800s and linear_miss < RELAXED)
    Select top MAX_SCREEN_CANDIDATES_PER_SAT by linear miss distance.

  Gate 2 — Per-pair TCA refinement (physics-accurate):
    Phase 1 coarse: bracket around linear TCA estimate, adaptive step.
    Phase 2 fine: 1s or 0.25s steps in ±60s window around coarse minimum.

  Output CDMs include approach_angle_deg (true RTN-frame approach vector angle)
  for accurate bullseye visualization, not a hash approximation.
"""
import numpy as np
from scipy.spatial import KDTree
from backend.config import (
    COLLISION_THRESHOLD, SCREENING_RADIUS,
    WARNING_THRESHOLD_RED, WARNING_THRESHOLD_YELLOW,
    PREDICTION_HORIZON, RK4_TIMESTEP,
    LINEAR_GATE_MAX_MISS_KM, LINEAR_GATE_RELAXED_MISS_KM,
    MAX_SCREEN_CANDIDATES_PER_SAT,
)
from backend.physics.propagator import propagate_single
from backend.physics.maneuver import compute_rtn_frame


class ConjunctionDetector:
    def __init__(self, state_manager):
        self.sm = state_manager

    # ─────────────────────────────────────────────────────────────────────────
    # Gate 1: Vectorized linearized forecast gate
    # ─────────────────────────────────────────────────────────────────────────

    def _linearized_gate(self, sat_indices, deb_indices, horizon_seconds):
        """Vectorized linear TCA screening — O(N_sat × N_deb) but single NumPy op.

        Computes the time of closest approach using linear (constant-velocity)
        approximation. This is very fast and gives a safe lower bound on miss distance.

        Returns list of (sat_id, deb_id, current_dist_km, lin_tca_s, lin_miss_km, v_rel_kms)
        """
        if not sat_indices or not deb_indices:
            return []

        sat_r = self.sm.positions[sat_indices]   # (Ns, 3)
        sat_v = self.sm.velocities[sat_indices]  # (Ns, 3)
        deb_r = self.sm.positions[deb_indices]   # (Nd, 3)
        deb_v = self.sm.velocities[deb_indices]  # (Nd, 3)

        Ns = len(sat_indices)
        Nd = len(deb_indices)

        # Broadcast: (Ns, Nd, 3)
        r_rel = deb_r[None, :, :] - sat_r[:, None, :]   # debris - sat
        v_rel = deb_v[None, :, :] - sat_v[:, None, :]

        # Linear TCA: t_lin = -r·v / v·v   (scalar, shape Ns×Nd)
        v2 = np.sum(v_rel * v_rel, axis=2) + 1e-18   # avoid div0
        t_lin = -np.sum(r_rel * v_rel, axis=2) / v2
        t_lin = np.clip(t_lin, 0.0, float(horizon_seconds))

        # Miss distance at linear TCA
        miss_vec = r_rel + v_rel * t_lin[:, :, None]
        d_lin = np.linalg.norm(miss_vec, axis=2)       # (Ns, Nd)
        d_now = np.linalg.norm(r_rel, axis=2)           # (Ns, Nd)
        v_rel_mag = np.sqrt(v2)                         # (Ns, Nd)

        candidates = []
        for i, sat_idx in enumerate(sat_indices):
            sat_id = self.sm.ids[sat_idx]
            row_dlin = d_lin[i]
            row_dnow = d_now[i]
            row_tlin = t_lin[i]
            row_vrel = v_rel_mag[i]

            # Candidate selection rule
            mask = (
                (row_dlin <= LINEAR_GATE_MAX_MISS_KM)
                | (row_dnow <= WARNING_THRESHOLD_YELLOW)
                | ((row_tlin < 1800.0) & (row_dlin <= LINEAR_GATE_RELAXED_MISS_KM))
            )

            idxs = np.where(mask)[0]
            if len(idxs) == 0:
                continue

            # Sort by linear miss (ascending) and keep top N
            sorted_idxs = idxs[np.argsort(row_dlin[idxs])][:MAX_SCREEN_CANDIDATES_PER_SAT]

            for j in sorted_idxs:
                deb_idx = deb_indices[j]
                deb_id = self.sm.ids[deb_idx]
                candidates.append((
                    sat_id, deb_id,
                    float(row_dnow[j]),
                    float(row_tlin[j]),
                    float(row_dlin[j]),
                    float(row_vrel[j]),
                ))

        return candidates

    def screen_conjunctions(self):
        """Run linearized gate and return candidate tuples."""
        sat_indices = self.sm.get_satellite_indices()
        deb_indices = self.sm.get_debris_indices()
        return self._linearized_gate(sat_indices, deb_indices, PREDICTION_HORIZON)

    # ─────────────────────────────────────────────────────────────────────────
    # Gate 2: Physics-accurate TCA per pair (two-phase)
    # ─────────────────────────────────────────────────────────────────────────

    def predict_conjunction(self, sat_id, deb_id,
                            horizon_seconds=PREDICTION_HORIZON,
                            linear_tca_hint=None):
        """Predict TCA accurately using bracketed coarse + fine RK4 propagation.

        Phase 1 — Coarse:
          - Window: [max(0, t_lin - 300), min(horizon, t_lin + 300)]
          - dt: 10s if t_lin < 600 else 30s
        Phase 2 — Fine:
          - Window: ±60s around coarse minimum
          - dt: 0.25s if coarse miss < 1 km else 1.0s

        Returns: (tca_seconds, min_distance_km, risk_level)
        """
        sat_r, sat_v = self.sm.get_state(sat_id)
        deb_r, deb_v = self.sm.get_state(deb_id)

        # Compute linear TCA as bracket center if no hint given
        if linear_tca_hint is None:
            r_rel = np.array(deb_r) - np.array(sat_r)
            v_rel = np.array(deb_v) - np.array(sat_v)
            v2 = np.dot(v_rel, v_rel) + 1e-18
            t_lin = float(np.clip(-np.dot(r_rel, v_rel) / v2, 0.0, horizon_seconds))
        else:
            t_lin = float(linear_tca_hint)

        # ── Phase 1: Coarse scan ─────────────────────────────────────────────
        bracket_half = 300.0
        coarse_start = max(0.0, t_lin - bracket_half)
        coarse_end   = min(float(horizon_seconds), t_lin + bracket_half)
        coarse_dt    = 10.0 if t_lin < 600.0 else 30.0

        # Propagate to coarse_start
        sx, sy, sz, svx, svy, svz = *sat_r, *sat_v
        dx, dy, dz, dvx, dvy, dvz = *deb_r, *deb_v

        if coarse_start > 0:
            sx, sy, sz, svx, svy, svz = propagate_single(
                sx, sy, sz, svx, svy, svz, coarse_start, RK4_TIMESTEP
            )
            dx, dy, dz, dvx, dvy, dvz = propagate_single(
                dx, dy, dz, dvx, dvy, dvz, coarse_start, RK4_TIMESTEP
            )

        n_coarse = max(1, int((coarse_end - coarse_start) / coarse_dt))
        min_dist = float("inf")
        min_t    = coarse_start

        for step in range(n_coarse + 1):
            t    = coarse_start + step * coarse_dt
            dist = np.sqrt((sx-dx)**2 + (sy-dy)**2 + (sz-dz)**2)
            if dist < min_dist:
                min_dist = dist
                min_t    = t
            if step < n_coarse:
                sx, sy, sz, svx, svy, svz = propagate_single(
                    sx, sy, sz, svx, svy, svz, coarse_dt, RK4_TIMESTEP
                )
                dx, dy, dz, dvx, dvy, dvz = propagate_single(
                    dx, dy, dz, dvx, dvy, dvz, coarse_dt, RK4_TIMESTEP
                )

        # If coarse scan missed anything interesting, try full horizon at coarse_dt
        if min_dist >= WARNING_THRESHOLD_YELLOW and t_lin > bracket_half:
            # Fall back to a wider scan
            sx, sy, sz, svx, svy, svz = *sat_r, *sat_v
            dx, dy, dz, dvx, dvy, dvz = *deb_r, *deb_v
            n_wide = min(int(horizon_seconds / coarse_dt), 50000)
            for step in range(n_wide + 1):
                t    = step * coarse_dt
                dist = np.sqrt((sx-dx)**2 + (sy-dy)**2 + (sz-dz)**2)
                if dist < min_dist:
                    min_dist = dist
                    min_t    = t
                # Early exit
                if dist > min_dist * 5 and min_dist < WARNING_THRESHOLD_YELLOW and step > 20:
                    break
                if step < n_wide:
                    sx, sy, sz, svx, svy, svz = propagate_single(
                        sx, sy, sz, svx, svy, svz, coarse_dt, RK4_TIMESTEP
                    )
                    dx, dy, dz, dvx, dvy, dvz = propagate_single(
                        dx, dy, dz, dvx, dvy, dvz, coarse_dt, RK4_TIMESTEP
                    )

        # ── Phase 2: Fine scan ───────────────────────────────────────────────
        if min_dist < WARNING_THRESHOLD_YELLOW:
            fine_dt    = 0.25 if min_dist < WARNING_THRESHOLD_RED else 1.0
            fine_start = max(0.0, min_t - 60.0)
            fine_end   = min(float(horizon_seconds), min_t + 60.0)

            sx, sy, sz, svx, svy, svz = *sat_r, *sat_v
            dx, dy, dz, dvx, dvy, dvz = *deb_r, *deb_v

            if fine_start > 0:
                sx, sy, sz, svx, svy, svz = propagate_single(
                    sx, sy, sz, svx, svy, svz, fine_start, RK4_TIMESTEP
                )
                dx, dy, dz, dvx, dvy, dvz = propagate_single(
                    dx, dy, dz, dvx, dvy, dvz, fine_start, RK4_TIMESTEP
                )

            n_fine = int((fine_end - fine_start) / fine_dt)
            for step in range(n_fine + 1):
                t    = fine_start + step * fine_dt
                dist = np.sqrt((sx-dx)**2 + (sy-dy)**2 + (sz-dz)**2)
                if dist < min_dist:
                    min_dist = dist
                    min_t    = t
                if step < n_fine:
                    sx, sy, sz, svx, svy, svz = propagate_single(
                        sx, sy, sz, svx, svy, svz, fine_dt, fine_dt
                    )
                    dx, dy, dz, dvx, dvy, dvz = propagate_single(
                        dx, dy, dz, dvx, dvy, dvz, fine_dt, fine_dt
                    )

        # ── Risk classification ──────────────────────────────────────────────
        if   min_dist < COLLISION_THRESHOLD:      risk = "CRITICAL"
        elif min_dist < WARNING_THRESHOLD_RED:    risk = "RED"
        elif min_dist < WARNING_THRESHOLD_YELLOW: risk = "YELLOW"
        else:                                     risk = "GREEN"

        return float(min_t), float(min_dist), risk

    # ─────────────────────────────────────────────────────────────────────────
    # Approach angle (true RTN-frame, for accurate bullseye visualization)
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_approach_angle_deg(self, sat_id, deb_id, tca_seconds):
        """Compute the approach angle in the satellite RTN frame at TCA.

        Propagates both objects to TCA, then projects the relative velocity
        onto the RTN frame. Returns angle 0–360 degrees where:
          0° = approaching from transverse (along-track) direction
          90° = approaching from normal (cross-track) direction

        Returns float degrees 0–360.
        """
        try:
            sat_r, sat_v = self.sm.get_state(sat_id)
            deb_r, deb_v = self.sm.get_state(deb_id)

            if tca_seconds > 0:
                from backend.physics.propagator import propagate_single as _ps
                sr, sx, sy, sz, svx, svy, svz = (
                    None, *sat_r, *sat_v
                )
                sat_r_tca = propagate_single(
                    sat_r[0], sat_r[1], sat_r[2],
                    sat_v[0], sat_v[1], sat_v[2],
                    tca_seconds, RK4_TIMESTEP
                )
                deb_r_tca = propagate_single(
                    deb_r[0], deb_r[1], deb_r[2],
                    deb_v[0], deb_v[1], deb_v[2],
                    tca_seconds, RK4_TIMESTEP
                )
                # sat_r_tca and deb_r_tca are 6-tuples (x,y,z,vx,vy,vz)
                sat_pos = np.array(sat_r_tca[:3])
                sat_vel = np.array(sat_r_tca[3:])
                deb_vel_tca = np.array(deb_r_tca[3:])
            else:
                sat_pos = np.array(sat_r)
                sat_vel = np.array(sat_v)
                deb_vel_tca = np.array(deb_v)

            # Relative velocity at TCA
            v_rel = deb_vel_tca - sat_vel

            # RTN frame at TCA
            rtn = compute_rtn_frame(sat_pos, sat_vel)

            # Project relative velocity into RTN
            v_rtn = rtn.T @ v_rel

            # Angle in T-N plane (atan2(N, T))
            angle_rad = np.arctan2(float(v_rtn[2]), float(v_rtn[1]))
            angle_deg = float(np.degrees(angle_rad)) % 360.0
            return round(angle_deg, 1)
        except Exception:
            return 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Full assessment pipeline
    # ─────────────────────────────────────────────────────────────────────────

    def run_full_assessment(self):
        """Full conjunction assessment: linearized gate → TCA refinement → classify → sort.

        Returns list of CDM dicts enriched with approach_angle_deg, relative_speed_kms,
        linear_tca_seconds for frontend visualization.
        """
        candidates = self.screen_conjunctions()
        cdm_warnings = []

        for sat_id, deb_id, current_dist, lin_tca, lin_miss, v_rel in candidates:
            tca, min_dist, risk = self.predict_conjunction(
                sat_id, deb_id, linear_tca_hint=lin_tca
            )

            if risk in ("CRITICAL", "RED", "YELLOW"):
                approach_angle = self._compute_approach_angle_deg(sat_id, deb_id, tca)
                cdm_warnings.append({
                    "sat_id":              sat_id,
                    "deb_id":              deb_id,
                    "tca_seconds":         float(tca),
                    "miss_distance_km":    float(min_dist),
                    "risk_level":          risk,
                    "current_distance_km": float(current_dist),
                    "linear_tca_seconds":  float(lin_tca),
                    "linear_miss_km":      float(lin_miss),
                    "relative_speed_kms":  float(v_rel),
                    "approach_angle_deg":  approach_angle,
                })

        risk_order = {"CRITICAL": 0, "RED": 1, "YELLOW": 2}
        cdm_warnings.sort(
            key=lambda w: (risk_order[w["risk_level"]], w["miss_distance_km"], w["tca_seconds"])
        )

        self.sm.set_watchlist(cdm_warnings)
        return cdm_warnings
