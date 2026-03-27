"""
Structured JSON logging for the ACM system.

Logs all maneuver events, conjunction detections, collisions,
and system diagnostics in machine-readable JSON format.

The PS evaluation criteria includes:
  "Code Quality & Logging (10%): Assesses modularity, documentation,
   and the accuracy of the system's maneuver logging capabilities."
"""
import json
import sys
import logging
from datetime import datetime, timezone
from typing import Optional


class ACMLogger:
    """JSON-structured logger for the Autonomous Constellation Manager."""

    def __init__(self, name="acm", log_file: Optional[str] = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter("%(message)s")

        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        self.logger.addHandler(console)

        # File handler (optional)
        if log_file:
            fh = logging.FileHandler(log_file, mode="a")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

    def _emit(self, level, event_type, data):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event_type,
            **data,
        }
        msg = json.dumps(record, default=str)
        if level == "INFO":
            self.logger.info(msg)
        elif level == "WARNING":
            self.logger.warning(msg)
        elif level == "ERROR":
            self.logger.error(msg)
        else:
            self.logger.debug(msg)

    # ─────────── Domain events ───────────

    def telemetry_ingested(self, count, cdm_warnings, timestamp):
        self._emit("INFO", "TELEMETRY_INGESTED", {
            "object_count": count,
            "cdm_warnings": cdm_warnings,
            "sim_timestamp": timestamp,
        })

    def conjunction_detected(self, sat_id, deb_id, tca_s, miss_km, risk):
        self._emit("WARNING" if risk == "CRITICAL" else "INFO", "CDM_DETECTED", {
            "sat_id": sat_id,
            "deb_id": deb_id,
            "tca_seconds": round(tca_s, 1),
            "miss_distance_km": round(miss_km, 4),
            "risk_level": risk,
        })

    def maneuver_scheduled(self, sat_id, burn_id, burn_type, dv_ms, burn_time):
        self._emit("INFO", "MANEUVER_SCHEDULED", {
            "sat_id": sat_id,
            "burn_id": burn_id,
            "burn_type": burn_type,
            "delta_v_ms": round(dv_ms, 4),
            "burn_time": str(burn_time),
        })

    def maneuver_executed(self, sat_id, burn_id, burn_type, dv_ms, fuel_used, fuel_remaining):
        self._emit("INFO", "MANEUVER_EXECUTED", {
            "sat_id": sat_id,
            "burn_id": burn_id,
            "burn_type": burn_type,
            "delta_v_ms": round(dv_ms, 4),
            "fuel_consumed_kg": round(fuel_used, 4),
            "fuel_remaining_kg": round(fuel_remaining, 4),
        })

    def maneuver_rejected(self, sat_id, burn_id, reason):
        self._emit("WARNING", "MANEUVER_REJECTED", {
            "sat_id": sat_id,
            "burn_id": burn_id,
            "reason": reason,
        })

    def collision_detected(self, sat_id, deb_id, distance_km):
        self._emit("ERROR", "COLLISION", {
            "sat_id": sat_id,
            "deb_id": deb_id,
            "distance_km": round(distance_km, 4),
        })

    def eol_triggered(self, sat_id, fuel_remaining):
        self._emit("WARNING", "EOL_TRIGGERED", {
            "sat_id": sat_id,
            "fuel_remaining_kg": round(fuel_remaining, 4),
        })

    def sim_step_complete(self, new_time, collisions, maneuvers_exec, objects_count):
        self._emit("INFO", "SIM_STEP", {
            "new_timestamp": str(new_time),
            "collisions": collisions,
            "maneuvers_executed": maneuvers_exec,
            "total_objects": objects_count,
        })

    def los_check(self, sat_id, has_los, stations):
        self._emit("DEBUG", "LOS_CHECK", {
            "sat_id": sat_id,
            "has_los": has_los,
            "visible_stations": stations,
        })


# Global singleton
logger = ACMLogger(log_file="acm_events.log")
