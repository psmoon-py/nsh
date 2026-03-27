"""
Maneuver calculations: RTN frame, evasion ΔV, recovery ΔV, Tsiolkovsky fuel.
"""
import numpy as np
from backend.config import ISP, G0, MAX_DELTA_V, MU


def compute_rtn_frame(r_eci, v_eci):
    """Compute RTN rotation matrix [R_hat | T_hat | N_hat]."""
    r_hat = r_eci / np.linalg.norm(r_eci)
    h = np.cross(r_eci, v_eci)
    n_hat = h / np.linalg.norm(h)
    t_hat = np.cross(n_hat, r_hat)
    return np.column_stack([r_hat, t_hat, n_hat])


def rtn_to_eci(r_eci, v_eci, dv_rtn):
    """Convert ΔV from RTN frame to ECI frame."""
    rtn_matrix = compute_rtn_frame(r_eci, v_eci)
    return rtn_matrix @ dv_rtn


def compute_fuel_consumed(current_mass_kg, delta_v_ms):
    """Tsiolkovsky: Δm = m_current * (1 - e^(-|ΔV|/(Isp·g0)))"""
    exponent = -abs(delta_v_ms) / (ISP * G0)
    dm = current_mass_kg * (1.0 - np.exp(exponent))
    return dm


def compute_evasion_dv(sat_r, sat_v, deb_r, deb_v, tca_seconds):
    """Calculate minimum ΔV to evade debris via transverse burn."""
    rel_pos = deb_r - sat_r
    miss_distance = np.linalg.norm(rel_pos)
    target_miss = 2.0
    rtn_matrix = compute_rtn_frame(sat_r, sat_v)
    r_mag = np.linalg.norm(sat_r)

    if tca_seconds > 0:
        dv_t = (target_miss - miss_distance) * r_mag / (tca_seconds * np.linalg.norm(sat_v))
        dv_t = np.clip(dv_t, -MAX_DELTA_V, MAX_DELTA_V)
    else:
        dv_t = MAX_DELTA_V

    dv_rtn = np.array([0.0, abs(dv_t), 0.0])
    dv_eci = rtn_matrix @ dv_rtn
    return dv_eci


def compute_recovery_dv(current_r, current_v, nominal_slot_r):
    """Calculate ΔV to return satellite to its nominal slot."""
    dr = nominal_slot_r - current_r
    distance_to_slot = np.linalg.norm(dr)

    if distance_to_slot < 1.0:
        v_hat = current_v / np.linalg.norm(current_v)
        return v_hat * 0.0001

    r_mag = np.linalg.norm(current_r)
    v_mag = np.linalg.norm(current_v)
    a_current = -MU / (2 * (v_mag**2 / 2 - MU / r_mag))
    T_current = 2 * np.pi * np.sqrt(abs(a_current) ** 3 / MU)
    delta_a = distance_to_slot * 0.1
    dv_magnitude = 2 * np.pi * delta_a / (3 * T_current)
    dv_magnitude = np.clip(dv_magnitude, 0.0001, MAX_DELTA_V)
    v_hat = current_v / np.linalg.norm(current_v)
    return v_hat * dv_magnitude
