"""
Data loader utilities.

Converts TLE (Two-Line Element) data from CelesTrak/Space-Track
into ECI state vectors usable by our physics engine.

Usage:
  If you want to load real satellite/debris data from CelesTrak
  instead of the synthetic generator, use these functions.
"""
import json
import numpy as np
from datetime import datetime, timezone


def tle_to_eci_sgp4(tle_line1: str, tle_line2: str, epoch: datetime = None):
    """Convert a TLE to ECI position and velocity using the sgp4 library.

    Args:
        tle_line1: First line of TLE
        tle_line2: Second line of TLE
        epoch: Time at which to compute the state (default: TLE epoch)

    Returns:
        (r, v): position (km) and velocity (km/s) in TEME/ECI
    """
    try:
        from sgp4.api import Satrec, jday

        satellite = Satrec.twoline2rv(tle_line1, tle_line2)

        if epoch is None:
            # Use TLE epoch
            jd = satellite.jdsatepoch
            fr = satellite.jdsatepochF
        else:
            jd, fr = jday(
                epoch.year, epoch.month, epoch.day,
                epoch.hour, epoch.minute, epoch.second + epoch.microsecond / 1e6
            )

        error, r, v = satellite.sgp4(jd, fr)
        if error != 0:
            return None, None

        return np.array(r), np.array(v)  # km, km/s (TEME ≈ ECI for our purposes)

    except ImportError:
        print("sgp4 library not installed. Run: pip install sgp4")
        return None, None


def load_tle_file(filepath: str, max_objects: int = None, epoch: datetime = None):
    """Load a 3LE (three-line element) file and convert to ECI states.

    3LE format:
      Line 0: Object name
      Line 1: 1 NNNNN...
      Line 2: 2 NNNNN...

    Returns:
        list of dicts with id, type, r, v
    """
    objects = []
    with open(filepath, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    i = 0
    while i < len(lines) - 2:
        name = lines[i]
        line1 = lines[i + 1]
        line2 = lines[i + 2]

        if not line1.startswith("1") or not line2.startswith("2"):
            i += 1
            continue

        r, v = tle_to_eci_sgp4(line1, line2, epoch)
        if r is not None:
            # Determine type from name
            obj_type = "DEBRIS" if any(
                kw in name.upper() for kw in ["DEB", "R/B", "FRAG", "UNKNOWN"]
            ) else "SATELLITE"

            # Extract NORAD catalog number
            norad_id = line1[2:7].strip()
            obj_id = f"{'DEB' if obj_type == 'DEBRIS' else 'SAT'}-{norad_id}"

            objects.append({
                "id": obj_id,
                "type": obj_type,
                "name": name.strip(),
                "r": {"x": round(r[0], 6), "y": round(r[1], 6), "z": round(r[2], 6)},
                "v": {"x": round(v[0], 6), "y": round(v[1], 6), "z": round(v[2], 6)},
            })

        i += 3
        if max_objects and len(objects) >= max_objects:
            break

    return objects


def load_omm_json(filepath: str, max_objects: int = None, epoch: datetime = None):
    """Load CelesTrak OMM JSON format and convert to ECI.

    OMM JSON format from:
      https://celestrak.org/NORAD/elements/gp.php?GROUP=...&FORMAT=json

    Returns: list of dicts
    """
    with open(filepath, "r") as f:
        omm_data = json.load(f)

    objects = []
    for entry in omm_data:
        line1 = entry.get("TLE_LINE1", "")
        line2 = entry.get("TLE_LINE2", "")
        name = entry.get("OBJECT_NAME", "UNKNOWN")

        if not line1 or not line2:
            continue

        r, v = tle_to_eci_sgp4(line1, line2, epoch)
        if r is not None:
            norad_id = entry.get("NORAD_CAT_ID", "00000")
            obj_type = "DEBRIS" if entry.get("OBJECT_TYPE", "") == "DEBRIS" else "SATELLITE"
            obj_id = f"{'DEB' if obj_type == 'DEBRIS' else 'SAT'}-{norad_id}"

            objects.append({
                "id": obj_id,
                "type": obj_type,
                "name": name,
                "r": {"x": round(r[0], 6), "y": round(r[1], 6), "z": round(r[2], 6)},
                "v": {"x": round(v[0], 6), "y": round(v[1], 6), "z": round(v[2], 6)},
            })

        if max_objects and len(objects) >= max_objects:
            break

    return objects
