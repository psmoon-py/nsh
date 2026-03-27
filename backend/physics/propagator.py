"""
J2-perturbed orbital propagator using RK4 numerical integration.

Equations of motion from the problem statement:
  d²r/dt² = -(μ/|r|³)·r + a_J2

Where a_J2 = (3/2)·J2·μ·RE²/|r|⁵ · [
    x·(5z²/|r|² - 1),
    y·(5z²/|r|² - 1),
    z·(5z²/|r|² - 3)
]
"""
import numpy as np
from numba import njit, prange
from backend.config import MU, RE, J2


@njit(cache=True)
def compute_acceleration(x, y, z):
    """Compute total acceleration (two-body + J2) at position [x, y, z].

    Returns: (ax, ay, az) in km/s²
    """
    r_sq = x * x + y * y + z * z
    r_mag = np.sqrt(r_sq)
    r_cubed = r_mag * r_sq
    r_fifth = r_sq * r_cubed

    z_sq_over_r_sq = (z * z) / r_sq

    # Two-body gravity
    two_body_factor = -MU / r_cubed

    # J2 perturbation
    j2_factor = 1.5 * J2 * MU * RE * RE / r_fifth

    ax = two_body_factor * x + j2_factor * x * (5.0 * z_sq_over_r_sq - 1.0)
    ay = two_body_factor * y + j2_factor * y * (5.0 * z_sq_over_r_sq - 1.0)
    az = two_body_factor * z + j2_factor * z * (5.0 * z_sq_over_r_sq - 3.0)

    return ax, ay, az


@njit(cache=True)
def rk4_step(x, y, z, vx, vy, vz, dt):
    """Single RK4 integration step."""
    ax1, ay1, az1 = compute_acceleration(x, y, z)
    k1x, k1y, k1z = vx, vy, vz
    k1vx, k1vy, k1vz = ax1, ay1, az1

    hdt = 0.5 * dt
    x2 = x + hdt * k1x
    y2 = y + hdt * k1y
    z2 = z + hdt * k1z
    vx2 = vx + hdt * k1vx
    vy2 = vy + hdt * k1vy
    vz2 = vz + hdt * k1vz
    ax2, ay2, az2 = compute_acceleration(x2, y2, z2)
    k2x, k2y, k2z = vx2, vy2, vz2
    k2vx, k2vy, k2vz = ax2, ay2, az2

    x3 = x + hdt * k2x
    y3 = y + hdt * k2y
    z3 = z + hdt * k2z
    vx3 = vx + hdt * k2vx
    vy3 = vy + hdt * k2vy
    vz3 = vz + hdt * k2vz
    ax3, ay3, az3 = compute_acceleration(x3, y3, z3)
    k3x, k3y, k3z = vx3, vy3, vz3
    k3vx, k3vy, k3vz = ax3, ay3, az3

    x4 = x + dt * k3x
    y4 = y + dt * k3y
    z4 = z + dt * k3z
    vx4 = vx + dt * k3vx
    vy4 = vy + dt * k3vy
    vz4 = vz + dt * k3vz
    ax4, ay4, az4 = compute_acceleration(x4, y4, z4)
    k4x, k4y, k4z = vx4, vy4, vz4
    k4vx, k4vy, k4vz = ax4, ay4, az4

    dt6 = dt / 6.0
    xn = x + dt6 * (k1x + 2.0 * k2x + 2.0 * k3x + k4x)
    yn = y + dt6 * (k1y + 2.0 * k2y + 2.0 * k3y + k4y)
    zn = z + dt6 * (k1z + 2.0 * k2z + 2.0 * k3z + k4z)
    vxn = vx + dt6 * (k1vx + 2.0 * k2vx + 2.0 * k3vx + k4vx)
    vyn = vy + dt6 * (k1vy + 2.0 * k2vy + 2.0 * k3vy + k4vy)
    vzn = vz + dt6 * (k1vz + 2.0 * k2vz + 2.0 * k3vz + k4vz)

    return xn, yn, zn, vxn, vyn, vzn


@njit(cache=True)
def propagate_single(x, y, z, vx, vy, vz, total_time, dt):
    """Propagate a single object for total_time seconds with step dt."""
    n_steps = int(total_time / dt)
    remainder = total_time - n_steps * dt

    for _ in range(n_steps):
        x, y, z, vx, vy, vz = rk4_step(x, y, z, vx, vy, vz, dt)

    if remainder > 1e-10:
        x, y, z, vx, vy, vz = rk4_step(x, y, z, vx, vy, vz, remainder)

    return x, y, z, vx, vy, vz


@njit(parallel=True, cache=True)
def propagate_batch(states, total_time, dt):
    """Propagate N objects in parallel.

    states: Nx6 array [[x, y, z, vx, vy, vz], ...]
    Returns: Nx6 array of new states
    """
    n = states.shape[0]
    result = np.empty_like(states)

    for i in prange(n):
        result[i, 0], result[i, 1], result[i, 2], \
        result[i, 3], result[i, 4], result[i, 5] = propagate_single(
            states[i, 0], states[i, 1], states[i, 2],
            states[i, 3], states[i, 4], states[i, 5],
            total_time, dt
        )

    return result
