"""
Station-Keeping Manager — monitors satellite drift from nominal slots
and triggers recovery maneuvers when needed.

From the PS:
  - "Drift Tolerance: A satellite is considered 'Nominal' as long as its
     true position remains within a 10 km spherical radius of its
     designated slot."
  - "Uptime Penalty: If a collision avoidance maneuver pushes the satellite
     outside this bounding box, the system logs a Service Outage. Your
     Uptime Score degrades exponentially for every second spent outside
     the box."
  - "Recovery Burn Requirement: Every evasion maneuver must be paired with
     a calculated recovery trajectory to return the satellite to its slot
     once the debris threat has safely passed."
"""
import numpy as np
from datetime import datetime, timezone, timedelta
from backend.config import SLOT_TOLERANCE, COOLDOWN_SECONDS, SIGNAL_DELAY


class StationKeepingManager:
    """Monitors constellation slot compliance and schedules recovery burns."""

    def __init__(self, state_manager, scheduler):
        self.sm = state_manager
        self.scheduler = scheduler

        # Track uptime per satellite
        # uptime_log[sat_id] = [(start_outage_time, end_outage_time), ...]
        self.outage_log = {}
        self._currently_out = {}  # sat_id → outage_start_time

    def update_all_statuses(self):
        """Check every satellite's slot compliance. Called each sim step.

        Updates the status field in state_manager and tracks outage windows.
        """
        now = self.sm.timestamp

        for sat_id in self.sm.sat_ids:
            if sat_id not in self.sm.nominal_slots:
                continue

            idx = self.sm._id_to_idx[sat_id]
            current_r = self.sm.positions[idx]
            nominal_r = self.sm.nominal_slots[sat_id]

            drift = np.linalg.norm(current_r - nominal_r)

            if drift <= SLOT_TOLERANCE:
                self.sm.objects[sat_id]["status"] = "NOMINAL"

                # If was out of slot, close the outage window
                if sat_id in self._currently_out:
                    start = self._currently_out.pop(sat_id)
                    if sat_id not in self.outage_log:
                        self.outage_log[sat_id] = []
                    self.outage_log[sat_id].append((start, now))
            else:
                self.sm.objects[sat_id]["status"] = "OUT_OF_SLOT"

                # Start tracking outage if not already
                if sat_id not in self._currently_out:
                    self._currently_out[sat_id] = now

            # Store drift distance for diagnostics
            self.sm.objects[sat_id]["drift_km"] = round(drift, 3)

    def get_drift(self, sat_id: str) -> float:
        """Get current drift distance from nominal slot in km."""
        if sat_id not in self.sm.nominal_slots:
            return 0.0
        idx = self.sm._id_to_idx[sat_id]
        current_r = self.sm.positions[idx]
        nominal_r = self.sm.nominal_slots[sat_id]
        return float(np.linalg.norm(current_r - nominal_r))

    def get_uptime_fraction(self, sat_id: str, window_seconds: float = 86400) -> float:
        """Compute uptime fraction for a satellite over the given window.

        Returns float 0.0–1.0 representing fraction of time in-slot.
        """
        if sat_id not in self.outage_log and sat_id not in self._currently_out:
            return 1.0

        total_outage = 0.0
        now = self.sm.timestamp

        # Completed outages
        for start, end in self.outage_log.get(sat_id, []):
            # Only count outages within the window
            window_start = now - timedelta(seconds=window_seconds)
            s = max(start, window_start)
            e = min(end, now)
            if e > s:
                total_outage += (e - s).total_seconds()

        # Ongoing outage
        if sat_id in self._currently_out:
            window_start = now - timedelta(seconds=window_seconds)
            s = max(self._currently_out[sat_id], window_start)
            total_outage += (now - s).total_seconds()

        uptime = max(0, window_seconds - total_outage) / window_seconds
        return round(uptime, 4)

    def get_fleet_uptime(self) -> float:
        """Average uptime across all satellites."""
        if not self.sm.sat_ids:
            return 1.0
        uptimes = [self.get_uptime_fraction(sid) for sid in self.sm.sat_ids]
        return round(sum(uptimes) / len(uptimes), 4)

    def trigger_recovery_if_needed(self, sat_id: str):
        """Check if a satellite is out-of-slot and has no pending recovery
        burn, then schedule one.

        Only triggers if:
        - Satellite is OUT_OF_SLOT
        - No pending RECOVERY or EVASION burn exists for this satellite
        - Cooldown has elapsed since last burn
        """
        from backend.engine.scheduler import ManeuverCommand

        status = self.sm.objects.get(sat_id, {}).get("status", "NOMINAL")
        if status == "NOMINAL":
            return

        # Check if recovery already queued
        pending = self.scheduler.get_pending_for_satellite(sat_id)
        has_recovery = any(c.burn_type == "RECOVERY" for c in pending)
        has_evasion = any(c.burn_type == "EVASION" for c in pending)

        if has_recovery or has_evasion:
            return  # Wait for existing maneuver to complete

        # Check cooldown
        last_burn = self.sm.last_burn_time.get(sat_id)
        if last_burn is not None:
            gap = (self.sm.timestamp - last_burn).total_seconds()
            if gap < COOLDOWN_SECONDS:
                return  # Still in cooldown

        # Compute recovery ΔV
        from backend.physics.maneuver import compute_recovery_dv

        sat_r, sat_v = self.sm.get_state(sat_id)
        nominal_r = self.sm.nominal_slots.get(sat_id)
        if nominal_r is None:
            return

        dv_eci = compute_recovery_dv(sat_r, sat_v, nominal_r)

        burn_time = self.sm.timestamp + timedelta(seconds=SIGNAL_DELAY + 5)

        cmd = ManeuverCommand(
            sat_id=sat_id,
            burn_id=self.scheduler._gen_burn_id("REC"),
            burn_time=burn_time,
            delta_v=dv_eci,
            burn_type="RECOVERY",
        )
        self.scheduler.schedule(cmd)

    def run_recovery_sweep(self):
        """Check all out-of-slot satellites and schedule recovery burns."""
        for sat_id in self.sm.sat_ids:
            self.trigger_recovery_if_needed(sat_id)
