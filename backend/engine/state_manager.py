"""
Central state store for all satellites and debris.
Uses numpy arrays for vectorized operations.

Handles BOTH data formats:
  - Dict: {"r": {"x": 1.0, "y": 2.0, "z": 3.0}}  (from JSON files)
  - List: {"r": [1.0, 2.0, 3.0]}                    (potential alt format)
  - Pydantic model_dump: {"r": {"x": 1.0, ...}}     (from API telemetry)
"""
import numpy as np
import json
from datetime import datetime, timezone
from backend.config import DRY_MASS, INITIAL_FUEL, INITIAL_WET_MASS, SLOT_TOLERANCE


def _extract_vec3(obj, key):
    """Safely extract a 3-vector from either dict or list format."""
    val = obj[key]
    if isinstance(val, dict):
        return [val["x"], val["y"], val["z"]]
    elif isinstance(val, (list, tuple)):
        return [val[0], val[1], val[2]]
    elif isinstance(val, np.ndarray):
        return val.tolist()
    else:
        raise ValueError(f"Cannot parse {key}: {type(val)} = {val}")


class StateManager:
    def __init__(self):
        self.timestamp = datetime(2026, 3, 12, 8, 0, 0, tzinfo=timezone.utc)
        self.objects = {}
        self.ids = []
        self.sat_ids = []
        self.deb_ids = []
        self.positions = np.zeros((0, 3))
        self.velocities = np.zeros((0, 3))
        self._id_to_idx = {}
        self.nominal_slots = {}
        self.nominal_slot_vels = {}
        self.fuel = {}
        self.masses = {}
        self.last_burn_time = {}
        self.active_cdms = []
        self.maneuver_log = []

    def load_initial_data(self, sat_file, deb_file):
        with open(sat_file) as f:
            sats = json.load(f)
        with open(deb_file) as f:
            debs = json.load(f)
        all_objects = sats + debs
        n = len(all_objects)
        self.positions = np.zeros((n, 3))
        self.velocities = np.zeros((n, 3))
        self.ids = []
        self.sat_ids = []
        self.deb_ids = []
        self._id_to_idx = {}
        self.nominal_slots = {}
        self.nominal_slot_vels = {}
        self.fuel = {}
        self.masses = {}
        self.last_burn_time = {}

        for i, obj in enumerate(all_objects):
            oid = obj["id"]
            self.ids.append(oid)
            self._id_to_idx[oid] = i

            r = _extract_vec3(obj, "r")
            v = _extract_vec3(obj, "v")
            self.positions[i] = r
            self.velocities[i] = v

            if obj.get("type", "DEBRIS") == "SATELLITE":
                self.sat_ids.append(oid)
                self.objects[oid] = {"type": "SATELLITE", "status": "NOMINAL"}
                self.fuel[oid] = obj.get("fuel_kg", INITIAL_FUEL)
                self.masses[oid] = obj.get("mass_kg", INITIAL_WET_MASS)
                self.last_burn_time[oid] = None

                if "nominal_slot" in obj:
                    ns = obj["nominal_slot"]
                    if isinstance(ns, dict):
                        self.nominal_slots[oid] = np.array([ns["x"], ns["y"], ns["z"]])
                    else:
                        self.nominal_slots[oid] = np.array(ns[:3])
                else:
                    self.nominal_slots[oid] = np.array(r)

                self.nominal_slot_vels[oid] = np.array(v)
            else:
                self.deb_ids.append(oid)
                self.objects[oid] = {"type": "DEBRIS", "status": "ACTIVE"}

    def update_from_telemetry(self, timestamp_str, objects_list):
        self.timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        for obj in objects_list:
            oid = obj["id"]
            r = np.array(_extract_vec3(obj, "r"))
            v = np.array(_extract_vec3(obj, "v"))

            if oid in self._id_to_idx:
                idx = self._id_to_idx[oid]
                self.positions[idx] = r
                self.velocities[idx] = v
            else:
                idx = len(self.ids)
                self.ids.append(oid)
                self._id_to_idx[oid] = idx
                self.positions = np.vstack([self.positions, r.reshape(1, 3)])
                self.velocities = np.vstack([self.velocities, v.reshape(1, 3)])

                obj_type = obj.get("type", "DEBRIS")
                self.objects[oid] = {"type": obj_type, "status": "ACTIVE"}

                if obj_type == "SATELLITE":
                    self.sat_ids.append(oid)
                    self.fuel[oid] = obj.get("fuel_kg", INITIAL_FUEL)
                    self.masses[oid] = obj.get("mass_kg", INITIAL_WET_MASS)
                    self.last_burn_time[oid] = None
                    self.nominal_slots[oid] = r.copy()
                    self.nominal_slot_vels[oid] = v.copy()
                else:
                    self.deb_ids.append(oid)

    def get_satellite_indices(self):
        return [self._id_to_idx[sid] for sid in self.sat_ids if sid in self._id_to_idx]

    def get_debris_indices(self):
        return [self._id_to_idx[did] for did in self.deb_ids if did in self._id_to_idx]

    def get_state(self, obj_id):
        idx = self._id_to_idx[obj_id]
        return self.positions[idx].copy(), self.velocities[idx].copy()

    def check_slot_status(self, sat_id):
        if sat_id not in self.nominal_slots:
            return "NOMINAL"
        idx = self._id_to_idx[sat_id]
        current_r = self.positions[idx]
        nominal_r = self.nominal_slots[sat_id]
        distance = np.linalg.norm(current_r - nominal_r)
        return "NOMINAL" if distance <= SLOT_TOLERANCE else "OUT_OF_SLOT"
