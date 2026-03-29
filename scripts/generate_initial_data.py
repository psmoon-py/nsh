"""
Generate initial satellite constellation and debris field data.
Uses realistic orbital parameters to create test data in ECI format.
Generates 100 SATELLITE-GEN satellites in 5 Walker planes at 550 km.
"""
import json
import os
import numpy as np

MU = 398600.4418
RE = 6378.137


def keplerian_to_eci(a, e, i, raan, argp, nu):
    p = a * (1 - e**2)
    r_mag = p / (1 + e * np.cos(nu))
    r_pf = np.array([r_mag * np.cos(nu), r_mag * np.sin(nu), 0.0])
    v_pf = np.sqrt(MU / p) * np.array([-np.sin(nu), e + np.cos(nu), 0.0])
    cr, sr = np.cos(raan), np.sin(raan)
    ca, sa = np.cos(argp), np.sin(argp)
    ci, si = np.cos(i), np.sin(i)
    R = np.array([
        [cr*ca - sr*sa*ci, -cr*sa - sr*ca*ci, sr*si],
        [sr*ca + cr*sa*ci, -sr*sa + cr*ca*ci, -cr*si],
        [sa*si,            ca*si,             ci   ],
    ])
    return (R @ r_pf).tolist(), (R @ v_pf).tolist()


def generate_constellation(n_sats=100):
    """Generate n_sats satellites in a Walker Delta constellation."""
    satellites = []
    n_planes = 5
    sats_per_plane = n_sats // n_planes   # 20 per plane
    a = RE + 550.0     # 550 km altitude
    e = 0.0001         # nearly circular
    inc = np.radians(53.0)
    sat_id = 1

    for plane in range(n_planes):
        raan = np.radians(plane * 360.0 / n_planes)
        for s in range(sats_per_plane):
            nu = np.radians(s * 360.0 / sats_per_plane)
            r, v = keplerian_to_eci(a, e, inc, raan, 0.0, nu)

            # Verify velocity is non-zero
            v_mag = np.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
            assert v_mag > 6.0, f"Velocity too small: {v_mag}"

            satellites.append({
                "id": f"SATELLITE-GEN-{sat_id:03d}",
                "type": "SATELLITE",
                "r": {"x": round(r[0], 6), "y": round(r[1], 6), "z": round(r[2], 6)},
                "v": {"x": round(v[0], 6), "y": round(v[1], 6), "z": round(v[2], 6)},
                "fuel_kg": 50.0,
                "mass_kg": 550.0,     # dry(500) + fuel(50) per PS
                "nominal_slot": {
                    "x": round(r[0], 6),
                    "y": round(r[1], 6),
                    "z": round(r[2], 6)
                },
            })
            sat_id += 1

    return satellites


def generate_debris(n_debris=10000):
    debris = []
    rng = np.random.default_rng(42)

    for i in range(n_debris):
        alt = rng.uniform(300, 1200)
        a = RE + alt
        e = rng.uniform(0.0001, 0.05)
        inc = np.radians(rng.uniform(0, 100))
        raan = np.radians(rng.uniform(0, 360))
        argp = np.radians(rng.uniform(0, 360))
        nu   = np.radians(rng.uniform(0, 360))
        r, v = keplerian_to_eci(a, e, inc, raan, argp, nu)

        # Sanity check
        r_mag = np.sqrt(r[0]**2 + r[1]**2 + r[2]**2)
        if r_mag < 6400 or r_mag > 10000:
            continue

        debris.append({
            "id": f"DEB-{10000 + i}",
            "type": "DEBRIS",
            "r": {"x": round(r[0], 6), "y": round(r[1], 6), "z": round(r[2], 6)},
            "v": {"x": round(v[0], 6), "y": round(v[1], 6), "z": round(v[2], 6)},
            "fuel_kg": 0.0,
            "mass_kg": 250.0,
        })

    return debris


if __name__ == "__main__":
    os.makedirs("backend/data", exist_ok=True)

    print("Generating 100 satellites...")
    sats = generate_constellation(100)
    with open("backend/data/satellites_init.json", "w") as f:
        json.dump(sats, f, indent=2)
    print(f"  Saved {len(sats)} satellites")

    # Sample verification
    s0 = sats[0]
    v = s0["v"]
    v_mag = (v["x"]**2 + v["y"]**2 + v["z"]**2)**0.5
    print(f"  Sample: {s0['id']}  |v| = {v_mag:.3f} km/s  (should be ~7.5-7.6)")

    print("Generating 10000 debris objects...")
    debs = generate_debris(10000)
    with open("backend/data/debris_init.json", "w") as f:
        json.dump(debs, f, indent=2)
    print(f"  Saved {len(debs)} debris objects")

    print("Done! Restart the backend to load new data.")