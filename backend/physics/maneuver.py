"""
Maneuver calculations: RTN frame, CW-STM evasion ΔV, recovery ΔV, Tsiolkovsky fuel.

Key upgrade: compute_evasion_dv now uses the Clohessy-Wiltshire State Transition Matrix
(CW-STM) for minimum-fuel evasion planning instead of the naive "miss/time" formula.

The naive formula `dv = (target_miss - miss) * r_mag / (tca * v_mag)` has WRONG units
(gives km not km/s) and ignores Coriolis coupling — always clips to MAX_DELTA_V.

The CW STM accounts for the coupling between radial and in-track motion:
  r(TCA) = Phi_rr · r0 + Phi_rv · (v0 + ΔV)
The minimum-ΔV direction is found via eigendecomposition of (Phi_rv^-1)^T · (Phi_rv^-1).

Regime selection:
  - TCA < 60s  OR  v_rel > 3 km/s   →  max transverse (T-hat) burn (imminent / head-on)
  - Otherwise                         →  CW minimum-fuel evasion

Reference: Clohessy & Wiltshire (1960), "Terminal guidance system for satellite rendezvous."
"""
import numpy as np
from numpy.linalg import inv, norm, eigh
from backend.config import ISP, G0, MAX_DELTA_V, MU, RE


# ─── RTN Frame Utilities ───────────────────────────────────────────────────────

def compute_rtn_frame(r_eci, v_eci):
    """Compute RTN rotation matrix.
    
    Columns = [R_hat | T_hat | N_hat] in ECI coordinates.
    • R (Radial): points from Earth center through satellite.
    • T (Transverse): along-velocity direction.
    • N (Normal): perpendicular to orbital plane (R × T / |R × T|).
    """
    r_hat = r_eci / np.linalg.norm(r_eci)
    h = np.cross(r_eci, v_eci)
    n_hat = h / np.linalg.norm(h)
    t_hat = np.cross(n_hat, r_hat)
    return np.column_stack([r_hat, t_hat, n_hat])  # shape (3,3)


def rtn_to_eci(r_eci, v_eci, dv_rtn):
    """Convert ΔV from RTN frame to ECI frame.
    
    dv_eci = RTN_matrix @ dv_rtn
    """
    rtn_matrix = compute_rtn_frame(r_eci, v_eci)
    return rtn_matrix @ dv_rtn


# ─── Tsiolkovsky Fuel Model ────────────────────────────────────────────────────

def compute_fuel_consumed(current_mass_kg, delta_v_ms):
    """Tsiolkovsky rocket equation: Δm = m_current × (1 − e^(−|ΔV|/(Isp·g0))).
    
    Args:
        current_mass_kg: Current total mass (dry + remaining fuel) in kg.
        delta_v_ms: ΔV magnitude in m/s.
    
    Returns:
        Propellant mass consumed in kg.
    """
    exponent = -abs(delta_v_ms) / (ISP * G0)
    dm = current_mass_kg * (1.0 - np.exp(exponent))
    return float(dm)


# ─── CW State Transition Matrix ────────────────────────────────────────────────

def compute_cw_stm(n, tau):
    """Clohessy-Wiltshire State Transition Matrices.
    
    For relative motion near a circular reference orbit with mean motion n (rad/s),
    the relative state at time TCA (tau seconds ahead) satisfies:
        r(tau) = Phi_rr · r0 + Phi_rv · v0
    
    Phi_rv maps initial velocity to position at TCA — this is the key matrix
    for maneuver planning: to shift the TCA position by δr, apply ΔV = Phi_rv^-1 · δr.
    
    Args:
        n:   Mean motion of reference orbit (rad/s).  n = sqrt(μ / a³).
        tau: Time to TCA in seconds.
    
    Returns:
        (Phi_rr, Phi_rv) — each is a 3×3 NumPy array (RTN frame).
    """
    nt = n * tau
    c = np.cos(nt)
    s = np.sin(nt)

    # Position-to-position mapping
    Phi_rr = np.array([
        [4 - 3*c,       0,  0],
        [6*(s - nt),    1,  0],
        [0,             0,  c],
    ])

    # Velocity-to-position mapping (the critical matrix for maneuver planning)
    # The (T,T) element  (4s - 3nt)/n  contains the secular term −3nt/n that
    # grows linearly with lead time — prograde/retrograde burns are most efficient
    # for long lead times.
    Phi_rv = np.array([
        [s / n,              2*(1 - c) / n,       0     ],
        [-2*(1 - c) / n,    (4*s - 3*nt) / n,    0     ],
        [0,                  0,                    s / n ],
    ])

    return Phi_rr, Phi_rv


def _mean_motion(r_eci):
    """Compute mean motion n = sqrt(μ/a³) ≈ sqrt(μ/|r|³) for near-circular LEO."""
    r_mag = float(np.linalg.norm(r_eci))
    return float(np.sqrt(MU / (r_mag ** 3)))   # rad/s


# ─── Evasion ΔV (CW Minimum-Fuel) ─────────────────────────────────────────────

def compute_evasion_dv(sat_r, sat_v, deb_r, deb_v, tca_seconds):
    """Calculate minimum-fuel evasion ΔV using Clohessy-Wiltshire STM.
    
    Strategy:
      1. Compute relative state in RTN frame.
      2. Predict miss position at TCA without burn (CW propagation).
      3. If already safe, apply small insurance burn.
      4. Find the cheapest ΔV direction via eigendecomposition of cost matrix.
      5. Solve quadratic to find the ΔV magnitude that achieves d_target miss.
      6. Clamp to MAX_DELTA_V; if regime is head-on/imminent, use max T-burn.
    
    Args:
        sat_r: Satellite ECI position (km).
        sat_v: Satellite ECI velocity (km/s).
        deb_r: Debris ECI position (km).
        deb_v: Debris ECI velocity (km/s).
        tca_seconds: Time to closest approach in seconds.
    
    Returns:
        dv_eci (km/s): ΔV vector in ECI frame.
    """
    sat_r = np.asarray(sat_r, dtype=float)
    sat_v = np.asarray(sat_v, dtype=float)
    deb_r = np.asarray(deb_r, dtype=float)
    deb_v = np.asarray(deb_v, dtype=float)

    d_target = 2.0   # km — desired standoff miss distance after maneuver

    # Relative velocity magnitude
    rel_vel = deb_v - sat_v
    v_rel_mag = float(np.linalg.norm(rel_vel))

    # ── Regime selection: head-on or imminent → max transverse burn ──
    IMMINENT_THRESHOLD   = 60.0   # seconds: TCA too soon for CW to be accurate
    HEAD_ON_THRESHOLD    = 3.0    # km/s: high-speed approach, CW less accurate

    if tca_seconds < IMMINENT_THRESHOLD or v_rel_mag > HEAD_ON_THRESHOLD:
        # Max prograde (transverse) burn for immediate separation
        rtn = compute_rtn_frame(sat_r, sat_v)
        t_hat = rtn[:, 1]   # Transverse direction (along velocity)
        return t_hat * MAX_DELTA_V   # km/s

    # ── CW minimum-fuel evasion ──────────────────────────────────────────
    # Transform relative state into RTN frame of satellite
    RTN = compute_rtn_frame(sat_r, sat_v)    # shape (3,3); columns = R,T,N unit vectors

    r_rel_eci = deb_r - sat_r
    v_rel_eci = deb_v - sat_v

    r_rel_rtn = RTN.T @ r_rel_eci   # m (RTN frame)
    v_rel_rtn = RTN.T @ v_rel_eci   # m/s (RTN frame)

    # Mean motion from satellite radius
    n = _mean_motion(sat_r)
    tau = float(tca_seconds)

    Phi_rr, Phi_rv = compute_cw_stm(n, tau)

    # Predicted miss position WITHOUT maneuver (relative debris w.r.t. satellite at TCA)
    r_tca_noburn = Phi_rr @ r_rel_rtn + Phi_rv @ v_rel_rtn
    miss_noburn = float(np.linalg.norm(r_tca_noburn))

    # Already safe with margin — tiny insurance burn along T to widen gap slightly
    if miss_noburn >= d_target:
        rtn_col = compute_rtn_frame(sat_r, sat_v)
        t_hat = rtn_col[:, 1]
        return t_hat * 0.001   # 1 m/s insurance

    # ── Eigenvalue decomposition: find cheapest ΔV direction ────────────
    # Cost of shifting miss by δr: |ΔV|² = δr^T · (Phi_rv^-1)^T · (Phi_rv^-1) · δr
    # Minimum cost direction = eigenvector corresponding to minimum eigenvalue of A.
    try:
        Phi_rv_inv = inv(Phi_rv)
    except np.linalg.LinAlgError:
        # Fallback: transverse burn
        rtn_col = compute_rtn_frame(sat_r, sat_v)
        return rtn_col[:, 1] * MAX_DELTA_V

    A = Phi_rv_inv.T @ Phi_rv_inv
    eigenvalues, eigenvectors = eigh(A)   # ascending order
    best_dir = eigenvectors[:, 0]         # cheapest ΔV direction

    # ── Quadratic solve: |r_noburn + α · best_dir| = d_target ───────────
    # |r_noburn|² + 2α (r_noburn · best_dir) + α² = d_target²
    b_coef = float(np.dot(r_tca_noburn, best_dir))
    c_coef = float(miss_noburn ** 2 - d_target ** 2)
    discriminant = b_coef ** 2 - c_coef

    if discriminant < 0:
        discriminant = 0.0

    alpha1 = -b_coef + np.sqrt(discriminant)
    alpha2 = -b_coef - np.sqrt(discriminant)
    # Choose the root with smaller absolute value (cheaper burn)
    alpha = alpha1 if abs(alpha1) <= abs(alpha2) else alpha2

    delta_r_rtn = alpha * best_dir
    dv_rtn = Phi_rv_inv @ delta_r_rtn    # km/s in RTN frame

    # Convert RTN ΔV → ECI ΔV
    dv_eci = RTN @ dv_rtn

    # ── Clamp to max ΔV ─────────────────────────────────────────────────
    dv_mag = float(np.linalg.norm(dv_eci))
    if dv_mag * 1000.0 > MAX_DELTA_V * 1000.0:
        # Scale down to MAX_DELTA_V while preserving direction
        dv_eci = dv_eci / dv_mag * MAX_DELTA_V

    # Safety guard: if result is near zero (degenerate geometry), fall back to T-burn
    if float(np.linalg.norm(dv_eci)) < 1e-9:
        rtn_col = compute_rtn_frame(sat_r, sat_v)
        return rtn_col[:, 1] * MAX_DELTA_V

    return dv_eci


# ─── Recovery ΔV (Phasing Maneuver) ───────────────────────────────────────────

def compute_recovery_dv(current_r, current_v, nominal_slot_r):
    """Calculate ΔV to return satellite to its nominal orbital slot.
    
    Uses orbital phasing: adjust semi-major axis (and hence orbital period)
    so the satellite drifts back to its slot.
    
    The key insight from CW dynamics: a prograde burn raises the orbit (longer period,
    satellite falls behind), retrograde lowers it (shorter period, satellite catches up).
    
    For along-track separation Δs (km):
        Required ΔV ≈ n · Δs / 3    (phasing maneuver approximation)
    
    where n = mean motion of current orbit.
    
    Args:
        current_r:      Current ECI position (km).
        current_v:      Current ECI velocity (km/s).
        nominal_slot_r: Nominal slot ECI position (km).
    
    Returns:
        dv_eci (km/s): Recovery ΔV vector in ECI frame (prograde or retrograde).
    """
    current_r    = np.asarray(current_r,     dtype=float)
    current_v    = np.asarray(current_v,     dtype=float)
    nominal_slot_r = np.asarray(nominal_slot_r, dtype=float)

    dr = nominal_slot_r - current_r
    distance_to_slot = float(np.linalg.norm(dr))

    # Already in slot — minimal station-keeping
    if distance_to_slot < 1.0:
        v_hat = current_v / np.linalg.norm(current_v)
        return v_hat * 0.0001   # 0.1 m/s

    # Decompose separation into RTN frame
    rtn = compute_rtn_frame(current_r, current_v)
    dr_rtn = rtn.T @ dr

    # Along-track separation (T component)
    delta_along = float(dr_rtn[1])   # positive = slot is ahead of satellite

    # Mean motion
    n = _mean_motion(current_r)   # rad/s

    # Phasing ΔV (from CW secular term: δT = (4s-3nτ)/n · ΔV_T ≈ -3τ/n · ΔV_T for large τ)
    # Simplified: ΔV_T = -n · Δalong / 3  (per-orbit correction)
    # For practical recovery, use the period-based formula:
    T_orb = 2.0 * np.pi / n                        # orbital period (s)
    dv_t = -(delta_along / (3.0 * T_orb))           # km/s

    # Clamp to a reasonable range: don't burn more than 1 m/s for recovery
    dv_t = float(np.clip(dv_t, -0.001, 0.001))

    # Convert to ECI along transverse direction
    t_hat = rtn[:, 1]
    dv_eci = t_hat * dv_t

    # Safety guard: zero velocity can't define RTN frame
    if np.isnan(dv_eci).any() or np.isinf(dv_eci).any():
        v_hat = current_v / np.linalg.norm(current_v)
        return v_hat * 0.0001

    return dv_eci
