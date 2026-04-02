"""
Station-Keeping Manager — monitors satellite drift from nominal slots
and triggers recovery maneuvers when needed.

Uptime is scored BOTH as raw fraction AND exponential decay score (per PS).
Recovery burns are guarded: won't fire while active threat CDM is present.
"""
import numpy as np
from datetime import datetime, timezone, timedelta
from backend.config import (
    SLOT_TOLERANCE, COOLDOWN_SECONDS, SIGNAL_DELAY, UPTIME_DECAY_TAU_SECONDS
)


class StationKeepingManager:
    """Monitors constellation slot compliance and schedules recovery burns."""

    def __init__(self, state_manager, scheduler):
        self.sm = state_manager
        self.scheduler = scheduler
        self.outage_log = {}       # sat_id -> [(start, end), ...]
        self._currently_out = {}   # sat_id -> outage_start_time

    def update_all_statuses(self):
        """Check every satellite's slot compliance. Called each sim step."""
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
                if sat_id in self._currently_out:
                    start = self._currently_out.pop(sat_id)
                    if sat_id not in self.outage_log:
                        self.outage_log[sat_id] = []
                    self.outage_log[sat_id].append((start, now))
            else:
                self.sm.objects[sat_id]["status"] = "OUT_OF_SLOT"
                if sat_id not in self._currently_out:
                    self._currently_out[sat_id] = now

            self.sm.objects[sat_id]["drift_km"] = round(float(drift), 3)

    def get_drift(self, sat_id: str) -> float:
        if sat_id not in self.sm.nominal_slots:
            return 0.0
        idx = self.sm._id_to_idx[sat_id]
        return float(np.linalg.norm(
            self.sm.positions[idx] - self.sm.nominal_slots[sat_id]
        ))

    def _total_outage_seconds(self, sat_id: str, window_seconds: float = 86400) -> float:
        """Compute total out-of-slot time in seconds within the window."""
        now = self.sm.timestamp
        window_start = now - timedelta(seconds=window_seconds)
        total = 0.0

        for start, end in self.outage_log.get(sat_id, []):
            s = max(start, window_start)
            e = min(end, now)
            if e > s:
                total += (e - s).total_seconds()

        if sat_id in self._currently_out:
            s = max(self._currently_out[sat_id], window_start)
            total += (now - s).total_seconds()

        return total

    def get_uptime_fraction(self, sat_id: str, window_seconds: float = 86400) -> float:
        """Raw uptime fraction 0.0–1.0."""
        total_outage = self._total_outage_seconds(sat_id, window_seconds)
        return round(max(0.0, window_seconds - total_outage) / window_seconds, 4)

    def get_uptime_exponential_score(self, sat_id: str, window_seconds: float = 86400) -> float:
        """Exponential uptime score (per PS: 'degrades exponentially').

        score = exp(-total_outage / UPTIME_DECAY_TAU_SECONDS)
        Perfect in-slot = 1.0, large outage → 0.
        """
        total_outage = self._total_outage_seconds(sat_id, window_seconds)
        return round(float(np.exp(-total_outage / UPTIME_DECAY_TAU_SECONDS)), 4)

    def get_fleet_uptime(self) -> float:
        """Average raw uptime across all satellites."""
        if not self.sm.sat_ids:
            return 1.0
        return round(
            sum(self.get_uptime_fraction(sid) for sid in self.sm.sat_ids) / len(self.sm.sat_ids),
            4
        )

    def get_fleet_uptime_exponential_score(self) -> float:
        """Average exponential uptime score across all satellites."""
        if not self.sm.sat_ids:
            return 1.0
        return round(
            sum(self.get_uptime_exponential_score(sid) for sid in self.sm.sat_ids) / len(self.sm.sat_ids),
            4
        )

    def trigger_recovery_if_needed(self, sat_id: str):
        """Schedule recovery burn for out-of-slot satellite.

        Guards:
          - Must be OUT_OF_SLOT
          - No pending RECOVERY or EVASION
          - No active CRITICAL/RED CDM for this satellite (wait for threat to pass)
          - Cooldown elapsed
        """
        from backend.engine.scheduler import ManeuverCommand

        status = self.sm.objects.get(sat_id, {}).get("status", "NOMINAL")
        if status == "NOMINAL":
            return

        # Guard: active threat still present for this satellite
        active_threat = any(
            c.get("sat_id") == sat_id
            and c.get("risk_level") in ("CRITICAL", "RED")
            for c in self.sm.active_cdms
        )
        if active_threat:
            return

        # Guard: pending maneuver
        pending = self.scheduler.get_pending_for_satellite(sat_id)
        if any(c.burn_type in ("RECOVERY", "EVASION") for c in pending):
            return

        # Guard: cooldown
        last_burn = self.sm.last_burn_time.get(sat_id)
        if last_burn is not None:
            gap = (self.sm.timestamp - last_burn).total_seconds()
            if gap < COOLDOWN_SECONDS:
                return

        # Use pending_recovery_intent if available
        intent = self.sm.objects.get(sat_id, {}).get("pending_recovery_intent")
        if intent is not None:
            self.sm.objects[sat_id].pop("pending_recovery_intent", None)

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
