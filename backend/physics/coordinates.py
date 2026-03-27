"""
Coordinate frame transformations: ECI (J2000) ↔ ECEF ↔ Geodetic (lat/lon/alt)
"""
import numpy as np
from backend.config import RE, EARTH_ROTATION_RATE


def greenwich_sidereal_time(timestamp_unix):
    """Compute Greenwich Mean Sidereal Time (GMST) in radians."""
    jd = timestamp_unix / 86400.0 + 2440587.5
    T = (jd - 2451545.0) / 36525.0
    gmst_deg = 280.46061837 + 360.98564736629 * (jd - 2451545.0) \
               + 0.000387933 * T**2 - T**3 / 38710000.0
    return np.radians(gmst_deg % 360.0)


def eci_to_ecef(r_eci, timestamp_unix):
    """Rotate ECI position to ECEF using Earth's rotation."""
    theta = greenwich_sidereal_time(timestamp_unix)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    x_ecef = cos_t * r_eci[0] + sin_t * r_eci[1]
    y_ecef = -sin_t * r_eci[0] + cos_t * r_eci[1]
    z_ecef = r_eci[2]
    return np.array([x_ecef, y_ecef, z_ecef])


def ecef_to_geodetic(r_ecef):
    """Convert ECEF to geodetic (lat_deg, lon_deg, alt_km)."""
    x, y, z = r_ecef
    lon = np.degrees(np.arctan2(y, x))
    p = np.sqrt(x**2 + y**2)
    lat = np.arctan2(z, p)
    f = 1.0 / 298.257223563
    e2 = 2 * f - f**2
    for _ in range(5):
        sin_lat = np.sin(lat)
        N = RE / np.sqrt(1 - e2 * sin_lat**2)
        lat = np.arctan2(z + e2 * N * sin_lat, p)
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    N = RE / np.sqrt(1 - e2 * sin_lat**2)
    alt = p / cos_lat - N if abs(cos_lat) > 1e-10 else abs(z) - RE * (1 - e2)
    return np.degrees(lat), lon, alt


def eci_to_lla(r_eci, timestamp_unix):
    """ECI position → (latitude, longitude, altitude)."""
    r_ecef = eci_to_ecef(r_eci, timestamp_unix)
    return ecef_to_geodetic(r_ecef)


def geodetic_to_ecef(lat_deg, lon_deg, alt_km):
    """Convert geodetic (lat/lon/alt) to ECEF position vector."""
    lat = np.radians(lat_deg)
    lon = np.radians(lon_deg)
    f = 1.0 / 298.257223563
    e2 = 2 * f - f**2
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    N = RE / np.sqrt(1 - e2 * sin_lat**2)
    x = (N + alt_km) * cos_lat * np.cos(lon)
    y = (N + alt_km) * cos_lat * np.sin(lon)
    z = (N * (1 - e2) + alt_km) * sin_lat
    return np.array([x, y, z])
