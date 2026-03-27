"""Pydantic models for API request/response validation."""
from pydantic import BaseModel
from typing import List, Optional, Any


class Vector3(BaseModel):
    x: float
    y: float
    z: float

class SpaceObject(BaseModel):
    id: str
    type: str = "DEBRIS"
    r: Vector3
    v: Vector3

class TelemetryInput(BaseModel):
    timestamp: str
    objects: List[SpaceObject]

class TelemetryResponse(BaseModel):
    status: str
    processed_count: int
    active_cdm_warnings: int

class BurnCommand(BaseModel):
    burn_id: str
    burnTime: str
    deltaV_vector: Vector3

class ManeuverInput(BaseModel):
    satelliteId: str
    maneuver_sequence: List[BurnCommand]

class ManeuverResponse(BaseModel):
    status: str
    validation: dict

class SimulateStepInput(BaseModel):
    step_seconds: int

class SimulateStepResponse(BaseModel):
    status: str
    new_timestamp: str
    collisions_detected: int
    maneuvers_executed: int
