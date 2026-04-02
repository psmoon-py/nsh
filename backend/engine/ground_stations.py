"""
Ground Station Line-of-Sight (LOS) calculations.

A maneuver command can ONLY be transmitted if the target satellite
has an unobstructed geometric line-of-sight to at least one active
Ground Station, accounting for:
  - Earth's curvature (spherical occlusion)
  - Station minimum elevation mask angle
  - 10-second signal latency

The PS states:
  "A maneuver command can only be successfully transmitted if the target
   satellite has an unobstructed geometric line-of-sight to at least one
   active Ground Station, taking into account the Earth's curvature and
   the station's minimum elevation mask angle."

Ground station data from ground_stations.csv:
  GS-001  ISTRAC_Bengaluru     13.0333   77.5167   820   5.0
  GS-002  Svalbard             78.2297   15.4077   400   5.0
  GS-003  Goldstone            35.4266  -116.89   1000  10.0
  GS-004  Punta_Arenas        -53.1500  -70.9167    30   5.0
  GS-005  IIT_Delhi            28.5450   77.1926   225  15.0
  GS-006  McMurdo             -77.8463  166.6682    10   5.0
"""
import csv
import os
import numpy as np
from backend.config import RE, SIGNAL_DELAY
from backend.physics.coordinates import (
    geodetic_to_ecef,
    eci_to_ecef,
    greenwich_sidereal_time,
)


class GroundStation:
    """Single ground station with precomputed ECEF position."""

    def __init__(self, station_id, name, lat_deg, lon_deg, elevation_m, min_elev_deg):
        self.station_id = station_id
        self.name = name
        self.lat_deg = lat_deg
        self.lon_deg = lon_deg
        self.elevation_m = elevation_m
        self.elevation_km = elevation_m / 1000.0
        self.min_elev_deg = min_elev_deg
        self.min_elev_rad = np.radians(min_elev_deg)

        # Precompute ECEF position (ground stations don't move in ECEF)
        self.ecef = geodetic_to_ecef(lat_deg, lon_deg, self.elevation_km)

        # Precompute the local "up" unit vector at the station (ECEF)
        self.up_hat = self.ecef / np.linalg.norm(self.ecef)


class GroundStationNetwork:
    """
    Manages all ground stations and computes visibility windows.

    Elevation angle geometry:
    ────────────────────────────
    Given satellite ECEF position r_sat and station ECEF position r_gs:

      relative_pos = r_sat - r_gs
      slant_range  = |relative_pos|
      sin(elev)    = dot(relative_pos, up_hat) / slant_range

    The satellite is visible iff:
      elevation >= min_elevation_angle  (station-specific)

    This naturally accounts for Earth curvature because:
    - If the satellite is below the local horizon, the dot product
      with the station's "up" direction will be negative or small
    - The min elevation mask further restricts visibility
    """

    def __init__(self):
        self.stations = []

    def load_from_csv(self, csv_path):
        """Load ground station data from the provided CSV."""
        self.stations = []
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                gs = GroundStation(
                    station_id=row["Station_ID"].strip(),
                    name=row["Station_Name"].strip(),
                    lat_deg=float(row["Latitude"]),
                    lon_deg=float(row["Longitude"]),
                    elevation_m=float(row["Elevation_m"]),
                    min_elev_deg=float(row["Min_Elevation_Angle_deg"]),
                )
                self.stations.append(gs)

    def load_defaults(self):
        """Hardcoded fallback matching the problem statement CSV."""
        defaults = [
            ("GS-001", "ISTRAC_Bengaluru",      13.0333,   77.5167, 820,  5.0),
            ("GS-002", "Svalbard_Sat_Station",   78.2297,   15.4077, 400,  5.0),
            ("GS-003", "Goldstone_Tracking",     35.4266, -116.8900, 1000, 10.0),
            ("GS-004", "Punta_Arenas",          -53.1500,  -70.9167, 30,   5.0),
            ("GS-005", "IIT_Delhi_Ground_Node",  28.5450,   77.1926, 225,  15.0),
            ("GS-006", "McMurdo_Station",       -77.8463,  166.6682, 10,   5.0),
        ]
        self.stations = []
        for sid, name, lat, lon, elev, min_e in defaults:
            self.stations.append(
                GroundStation(sid, name, lat, lon, elev, min_e)
            )

    # ─────────────────────────────────────────────────────
    # Core visibility check
    # ─────────────────────────────────────────────────────

    def compute_elevation(self, sat_ecef, station):
        """Compute elevation angle (radians) of satellite as seen from station.

        Returns:
            float: Elevation angle in radians. Negative means below horizon.
        """
        relative = sat_ecef - station.ecef
        slant_range = np.linalg.norm(relative)
        if slant_range < 1e-6:
            return np.pi / 2  # Satellite is at the station (degenerate)

        sin_elev = np.dot(relative, station.up_hat) / slant_range
        # Clamp for numerical safety
        sin_elev = np.clip(sin_elev, -1.0, 1.0)
        return np.arcsin(sin_elev)

    def is_visible_from_station(self, sat_ecef, station):
        """Check if a satellite is visible from a specific station."""
        elev = self.compute_elevation(sat_ecef, station)
        return elev >= station.min_elev_rad

    def has_los_any_station(self, sat_eci, timestamp_unix):
        """Check if satellite has LOS to ANY ground station.

        This is the key function called by the maneuver scheduler.

        Args:
            sat_eci: np.array [x, y, z] in ECI (km)
            timestamp_unix: float, seconds since epoch

        Returns:
            (bool, list): (has_los, list_of_visible_station_ids)
        """
        sat_ecef = eci_to_ecef(sat_eci, timestamp_unix)
        visible_stations = []
        for gs in self.stations:
            if self.is_visible_from_station(sat_ecef, gs):
                visible_stations.append(gs.station_id)

        return len(visible_stations) > 0, visible_stations

    def get_best_station(self, sat_eci, timestamp_unix):
        """Return the ground station with the highest elevation angle.

        Useful for choosing the best uplink path.

        Returns:
            (station_id, elevation_deg) or (None, -90) if no LOS
        """
        sat_ecef = eci_to_ecef(sat_eci, timestamp_unix)
        best_id = None
        best_elev = -np.pi / 2

        for gs in self.stations:
            elev = self.compute_elevation(sat_ecef, gs)
            if elev >= gs.min_elev_rad and elev > best_elev:
                best_elev = elev
                best_id = gs.station_id

        return best_id, np.degrees(best_elev)

    # ─────────────────────────────────────────────────────
    # Visibility window prediction
    # ─────────────────────────────────────────────────────

    def predict_visibility_windows(
        self, sat_eci, sat_veci, timestamp_unix, horizon_seconds=7200, step_seconds=30
    ):
        """Predict future visibility windows for a satellite.

        Propagates the satellite forward and checks LOS at each step.
        Used for "blind conjunction" handling: if a conjunction is predicted
        during a blackout, we must pre-upload commands while in contact.

        Args:
            sat_eci: current position (km)
            sat_veci: current velocity (km/s)
            timestamp_unix: current time
            horizon_seconds: how far to look ahead (default 2 hours)
            step_seconds: check interval (default 30s)

        Returns:
            list of dicts: [{start_s, end_s, station_id}, ...]
        """
        from backend.physics.propagator import propagate_single
        from backend.config import RK4_TIMESTEP

        windows = []
        current_window = None
        n_steps = int(horizon_seconds / step_seconds)

        sx, sy, sz = sat_eci
        svx, svy, svz = sat_veci

        for step in range(n_steps + 1):
            t = step * step_seconds
            ts = timestamp_unix + t
            pos = np.array([sx, sy, sz])

            has_los, visible = self.has_los_any_station(pos, ts)

            if has_los:
                if current_window is None:
                    current_window = {
                        "start_s": t,
                        "station_ids": visible,
                    }
                else:
                    # Merge visible stations
                    for sid in visible:
                        if sid not in current_window["station_ids"]:
                            current_window["station_ids"].append(sid)
            else:
                if current_window is not None:
                    current_window["end_s"] = t
                    windows.append(current_window)
                    current_window = None

            # Propagate to next step
            if step < n_steps:
                sx, sy, sz, svx, svy, svz = propagate_single(
                    sx, sy, sz, svx, svy, svz, float(step_seconds), RK4_TIMESTEP
                )

        # Close any open window
        if current_window is not None:
            current_window["end_s"] = horizon_seconds
            windows.append(current_window)

        return windows

    def find_next_contact_window(self, sat_eci, sat_veci, timestamp_unix, max_wait=7200):
        """Find the next time the satellite will be in contact.

        Returns:
            (seconds_until_contact, duration_seconds, station_id) or (None, None, None)
        """
        windows = self.predict_visibility_windows(
            sat_eci, sat_veci, timestamp_unix, horizon_seconds=max_wait
        )
        if not windows:
            return None, None, None

        w = windows[0]
        return w["start_s"], w["end_s"] - w["start_s"], w["station_ids"][0]

    # ─────────────────────────────────────────────────────
    # Blackout zone detection
    # ─────────────────────────────────────────────────────

    def is_in_blackout(self, sat_eci, timestamp_unix):
        """Check if satellite is currently in a blackout zone (no LOS)."""
        has_los, _ = self.has_los_any_station(sat_eci, timestamp_unix)
        return not has_los


    def to_snapshot(self):
        """Serialize ground stations for snapshot API response."""
        return [
            {
                "id":           gs.station_id,
                "name":         gs.name,
                "lat":          gs.lat_deg,
                "lon":          gs.lon_deg,
                "min_elev_deg": gs.min_elev_deg,
            }
            for gs in self.stations
        ]
    def check_burn_uploadable(self, sat_eci, timestamp_unix, burn_time_unix):
        """Validate that a burn command can be uploaded to the satellite.

        Rules from the PS:
        1. Satellite must have LOS to at least one ground station NOW
           (at command upload time, not at burn time)
        2. Burn cannot be scheduled earlier than current time + 10s (signal delay)

        Returns:
            (bool, str): (is_valid, reason_if_invalid)
        """
        # Rule 2: Signal delay
        if burn_time_unix < timestamp_unix + SIGNAL_DELAY:
            return False, f"Burn too soon: must be >= {SIGNAL_DELAY}s from now"

        # Rule 1: LOS at upload time
        has_los, stations = self.has_los_any_station(sat_eci, timestamp_unix)
        if not has_los:
            return False, "No ground station LOS at upload time"

        return True, f"OK via {stations[0]}"
