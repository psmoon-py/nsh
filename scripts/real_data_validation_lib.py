from __future__ import annotations

import json
import math
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import COLLISION_THRESHOLD, WARNING_THRESHOLD_RED, WARNING_THRESHOLD_YELLOW

try:
    from sgp4.api import Satrec, jday  # type: ignore
except Exception as exc:  # pragma: no cover - runtime dependency check
    Satrec = None
    jday = None
    SGP4_IMPORT_ERROR = exc
else:  # pragma: no cover - runtime dependency check
    SGP4_IMPORT_ERROR = None


@dataclass
class TLETriple:
    name: str
    line1: str
    line2: str


@dataclass
class OracleEvent:
    sat_id: str
    deb_id: str
    tca_seconds: float
    miss_distance_km: float
    relative_speed_kms: float
    risk_level: str


@dataclass
class ValidationSummary:
    mode: str
    epoch: str
    satellites_loaded: int
    debris_loaded: int
    snapshot_satellites: int
    snapshot_debris: int
    backend_cdm_count: int
    oracle_pairs_scanned: int
    oracle_positive_count: int
    oracle_recall: Optional[float]
    matched_oracle_pairs: int
    seeded_cases_run: int
    seeded_cases_with_initial_cdm: int
    seeded_cases_avoided: int
    seeded_total_maneuvers: int
    seeded_total_collisions: int
    wall_clock_seconds: float


class LiveAPIClient:
    def __init__(self, api_base: str) -> None:
        self.api_base = api_base.rstrip("/")

    def get_json(self, path: str) -> Dict[str, Any]:
        url = self.api_base + path
        with urllib.request.urlopen(url, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = self.api_base + path
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))


class InProcessAPIClient:
    def __init__(self) -> None:
        from fastapi.testclient import TestClient  # local import so scripts still work without pytest
        from backend.main import app

        self.client = TestClient(app)

    def get_json(self, path: str) -> Dict[str, Any]:
        resp = self.client.get(path)
        resp.raise_for_status()
        return resp.json()

    def post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()


def require_sgp4() -> None:
    if Satrec is None or jday is None:
        raise RuntimeError(
            "sgp4 is required for the real-data validation suite. "
            f"Import failed with: {SGP4_IMPORT_ERROR!r}"
        )


def parse_iso_z(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def parse_3le_text(text: str) -> List[TLETriple]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    out: List[TLETriple] = []
    i = 0
    while i + 2 < len(lines):
        name, line1, line2 = lines[i], lines[i + 1], lines[i + 2]
        if line1.startswith("1 ") and line2.startswith("2 "):
            out.append(TLETriple(name=name, line1=line1, line2=line2))
            i += 3
        else:
            i += 1
    return out


def load_tles_from_file(path: Path) -> List[TLETriple]:
    return parse_3le_text(path.read_text(encoding="utf-8"))


def download_group_tles(group: str, timeout: int = 45) -> List[TLETriple]:
    url = (
        "https://celestrak.org/NORAD/elements/gp.php?"
        + urllib.parse.urlencode({"GROUP": group, "FORMAT": "tle"})
    )
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    triples = parse_3le_text(text)
    if not triples:
        raise RuntimeError(f"No TLE triples parsed from CelesTrak group {group!r}")
    return triples


def state_from_tle(triple: TLETriple, epoch_dt: datetime) -> Tuple[np.ndarray, np.ndarray]:
    require_sgp4()
    sat = Satrec.twoline2rv(triple.line1, triple.line2)
    jd, fr = jday(
        epoch_dt.year,
        epoch_dt.month,
        epoch_dt.day,
        epoch_dt.hour,
        epoch_dt.minute,
        epoch_dt.second + epoch_dt.microsecond / 1e6,
    )
    error, r, v = sat.sgp4(jd, fr)
    if error != 0:
        raise RuntimeError(f"SGP4 propagation error {error} for {triple.name}")
    return np.array(r, dtype=float), np.array(v, dtype=float)


def telemetry_object(object_id: str, object_type: str, r: np.ndarray, v: np.ndarray) -> Dict[str, Any]:
    return {
        "id": object_id,
        "type": object_type,
        "r": {"x": float(r[0]), "y": float(r[1]), "z": float(r[2])},
        "v": {"x": float(v[0]), "y": float(v[1]), "z": float(v[2])},
    }


def _valid_radius(r: np.ndarray) -> bool:
    rmag = float(np.linalg.norm(r))
    return 6300.0 <= rmag <= 50000.0


def build_fixture_telemetry(
    sat_tles: Sequence[TLETriple],
    epoch_dt: datetime,
    sat_limit: int = 5,
    debris_per_sat: int = 4,
) -> Tuple[Dict[str, Any], Dict[str, TLETriple]]:
    """Offline smoke dataset.

    Satellites come from bundled public TLEs. Debris are deterministic perturbations
    of those real states. This mode is for offline smoke tests only. It is not the
    real-data oracle mode.
    """
    objects: List[Dict[str, Any]] = []
    tle_map: Dict[str, TLETriple] = {}

    sat_triples = list(sat_tles)[:sat_limit]
    for idx, triple in enumerate(sat_triples, start=1):
        r, v = state_from_tle(triple, epoch_dt)
        if not _valid_radius(r):
            continue
        sat_id = f"SAT-FIX-{idx:03d}"
        tle_map[sat_id] = triple
        objects.append(telemetry_object(sat_id, "SATELLITE", r, v))

        rhat = r / np.linalg.norm(r)
        hhat = np.cross(r, v)
        hhat = hhat / np.linalg.norm(hhat)
        that = np.cross(hhat, rhat)
        bases = [rhat, that, hhat, (rhat + that) / np.linalg.norm(rhat + that)]

        for j in range(debris_per_sat):
            basis = bases[j % len(bases)]
            offset_km = 80.0 + 35.0 * j
            dv_kms = 0.01 + 0.002 * j
            deb_r = r + basis * offset_km
            deb_v = v - basis * dv_kms
            deb_id = f"DEB-FIX-{idx:03d}-{j+1:02d}"
            objects.append(telemetry_object(deb_id, "DEBRIS", deb_r, deb_v))

    payload = {"timestamp": to_iso_z(epoch_dt), "objects": objects}
    return payload, tle_map


def build_live_telemetry(
    sat_tles: Sequence[TLETriple],
    deb_tles: Sequence[TLETriple],
    epoch_dt: datetime,
    sat_limit: int,
    debris_limit: int,
) -> Tuple[Dict[str, Any], Dict[str, TLETriple], Dict[str, TLETriple]]:
    objects: List[Dict[str, Any]] = []
    sat_map: Dict[str, TLETriple] = {}
    deb_map: Dict[str, TLETriple] = {}

    sat_count = 0
    for triple in sat_tles:
        if sat_count >= sat_limit:
            break
        try:
            r, v = state_from_tle(triple, epoch_dt)
        except Exception:
            continue
        if not _valid_radius(r):
            continue
        sat_count += 1
        object_id = f"SAT-REAL-{sat_count:03d}"
        sat_map[object_id] = triple
        objects.append(telemetry_object(object_id, "SATELLITE", r, v))

    deb_count = 0
    for triple in deb_tles:
        if deb_count >= debris_limit:
            break
        try:
            r, v = state_from_tle(triple, epoch_dt)
        except Exception:
            continue
        if not _valid_radius(r):
            continue
        deb_count += 1
        object_id = f"DEB-REAL-{deb_count:05d}"
        deb_map[object_id] = triple
        objects.append(telemetry_object(object_id, "DEBRIS", r, v))

    payload = {"timestamp": to_iso_z(epoch_dt), "objects": objects}
    return payload, sat_map, deb_map


def _vector_from_obj(obj: Dict[str, Any], key: str) -> np.ndarray:
    comp = obj[key]
    return np.array([comp["x"], comp["y"], comp["z"]], dtype=float)


def _payload_index(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {obj["id"]: obj for obj in payload["objects"]}


def pick_oracle_pairs(
    payload: Dict[str, Any],
    max_sats: int = 5,
    max_debris: int = 120,
    max_pairs_per_sat: int = 8,
) -> List[Tuple[str, str]]:
    index = _payload_index(payload)
    sat_ids = [obj["id"] for obj in payload["objects"] if obj["type"] == "SATELLITE"][:max_sats]
    deb_ids = [obj["id"] for obj in payload["objects"] if obj["type"] == "DEBRIS"][:max_debris]

    pairs: List[Tuple[str, str]] = []
    for sat_id in sat_ids:
        sat_obj = index[sat_id]
        sat_r = _vector_from_obj(sat_obj, "r")
        dists: List[Tuple[float, str]] = []
        for deb_id in deb_ids:
            deb_obj = index[deb_id]
            deb_r = _vector_from_obj(deb_obj, "r")
            dists.append((float(np.linalg.norm(deb_r - sat_r)), deb_id))
        dists.sort(key=lambda x: x[0])
        for _, deb_id in dists[:max_pairs_per_sat]:
            pairs.append((sat_id, deb_id))
    return pairs


def _risk_from_miss(miss_km: float) -> str:
    if miss_km <= COLLISION_THRESHOLD:
        return "CRITICAL"
    if miss_km <= WARNING_THRESHOLD_RED:
        return "RED"
    if miss_km <= WARNING_THRESHOLD_YELLOW:
        return "YELLOW"
    return "GREEN"


def oracle_min_miss_for_pair(
    sat_tle: TLETriple,
    deb_tle: TLETriple,
    epoch_dt: datetime,
    horizon_seconds: float = 24.0 * 3600.0,
    coarse_step_seconds: float = 60.0,
    fine_step_seconds: float = 1.0,
) -> OracleEvent:
    require_sgp4()
    satrec_a = Satrec.twoline2rv(sat_tle.line1, sat_tle.line2)
    satrec_b = Satrec.twoline2rv(deb_tle.line1, deb_tle.line2)

    best_t = 0.0
    best_miss = float("inf")
    best_rel_speed = 0.0

    def state_at(satrec: Any, when: datetime) -> Tuple[np.ndarray, np.ndarray]:
        jd, fr = jday(
            when.year,
            when.month,
            when.day,
            when.hour,
            when.minute,
            when.second + when.microsecond / 1e6,
        )
        err, r, v = satrec.sgp4(jd, fr)
        if err != 0:
            raise RuntimeError(f"SGP4 error {err}")
        return np.array(r, dtype=float), np.array(v, dtype=float)

    t = 0.0
    while t <= horizon_seconds + 1e-9:
        when = epoch_dt + timedelta(seconds=t)
        ra, va = state_at(satrec_a, when)
        rb, vb = state_at(satrec_b, when)
        miss = float(np.linalg.norm(rb - ra))
        if miss < best_miss:
            best_miss = miss
            best_t = t
            best_rel_speed = float(np.linalg.norm(vb - va))
        t += coarse_step_seconds

    fine_start = max(0.0, best_t - coarse_step_seconds)
    fine_end = min(horizon_seconds, best_t + coarse_step_seconds)
    t = fine_start
    while t <= fine_end + 1e-9:
        when = epoch_dt + timedelta(seconds=t)
        ra, va = state_at(satrec_a, when)
        rb, vb = state_at(satrec_b, when)
        miss = float(np.linalg.norm(rb - ra))
        if miss < best_miss:
            best_miss = miss
            best_t = t
            best_rel_speed = float(np.linalg.norm(vb - va))
        t += fine_step_seconds

    return OracleEvent(
        sat_id="",
        deb_id="",
        tca_seconds=float(best_t),
        miss_distance_km=float(best_miss),
        relative_speed_kms=float(best_rel_speed),
        risk_level=_risk_from_miss(float(best_miss)),
    )


def compare_backend_to_oracle(
    client: Any,
    payload: Dict[str, Any],
    sat_tles: Dict[str, TLETriple],
    deb_tles: Dict[str, TLETriple],
    epoch_dt: datetime,
    max_sats: int = 5,
    max_debris: int = 120,
    max_pairs_per_sat: int = 8,
    horizon_seconds: float = 24.0 * 3600.0,
) -> Dict[str, Any]:
    telemetry_resp = client.post_json("/api/telemetry", payload)
    snapshot = client.get_json("/api/visualization/snapshot")

    backend_cdms = snapshot.get("cdm_warnings", [])
    backend_by_pair = {(cdm["sat_id"], cdm["deb_id"]): cdm for cdm in backend_cdms}

    oracle_pairs = []
    for sat_id, deb_id in pick_oracle_pairs(payload, max_sats=max_sats, max_debris=max_debris, max_pairs_per_sat=max_pairs_per_sat):
        if sat_id not in sat_tles or deb_id not in deb_tles:
            continue
        oracle_event = oracle_min_miss_for_pair(
            sat_tles[sat_id],
            deb_tles[deb_id],
            epoch_dt=epoch_dt,
            horizon_seconds=horizon_seconds,
        )
        oracle_event.sat_id = sat_id
        oracle_event.deb_id = deb_id
        if oracle_event.risk_level != "GREEN":
            oracle_pairs.append(oracle_event)

    matched = 0
    tca_errors: List[float] = []
    miss_errors: List[float] = []
    for event in oracle_pairs:
        cdm = backend_by_pair.get((event.sat_id, event.deb_id))
        if cdm is None:
            continue
        matched += 1
        tca_errors.append(abs(float(cdm.get("tca_seconds", 0.0)) - event.tca_seconds))
        miss_errors.append(abs(float(cdm.get("miss_distance_km", 0.0)) - event.miss_distance_km))

    oracle_recall = None
    if oracle_pairs:
        oracle_recall = matched / len(oracle_pairs)

    return {
        "telemetry_response": telemetry_resp,
        "snapshot_satellites": len(snapshot.get("satellites", [])),
        "snapshot_debris": len(snapshot.get("debris_cloud", [])),
        "backend_cdm_count": len(backend_cdms),
        "oracle_pairs_scanned": max_sats * max_pairs_per_sat,
        "oracle_positive_count": len(oracle_pairs),
        "oracle_positive_pairs": [asdict(evt) for evt in oracle_pairs],
        "oracle_recall": oracle_recall,
        "matched_oracle_pairs": matched,
        "median_tca_error_s": float(np.median(tca_errors)) if tca_errors else None,
        "median_miss_error_km": float(np.median(miss_errors)) if miss_errors else None,
        "backend_pairs": list(backend_by_pair.keys()),
    }


def run_seeded_collision_campaign(
    client: Any,
    cases_to_run: int = 2,
    step_seconds: int = 30,
    max_steps: int = 80,
) -> Dict[str, Any]:
    from collision_case_builder import build_dynamic_collision_case

    snapshot = client.get_json("/api/visualization/snapshot")
    satellites = snapshot.get("satellites", [])
    if not satellites:
        raise RuntimeError("No satellites available in snapshot for seeded collision campaign")

    cases = []
    collisions = 0
    maneuvers = 0
    cases_with_initial_cdm = 0
    cases_avoided = 0

    for idx, sat in enumerate(satellites[:cases_to_run], start=1):
        case = build_dynamic_collision_case(sat, deb_id=f"DEB-VAL-COLL-{idx:03d}")
        inject_payload = {
            "timestamp": snapshot["timestamp"],
            "objects": [case.telemetry_object()],
        }
        client.post_json("/api/telemetry", inject_payload)
        after_inject = client.get_json("/api/visualization/snapshot")
        initial_cdms = [
            cdm for cdm in after_inject.get("cdm_warnings", [])
            if cdm.get("sat_id") == case.sat_id and cdm.get("deb_id") == case.deb_id
        ]
        if initial_cdms:
            cases_with_initial_cdm += 1

        steps_needed = min(max_steps, int(math.ceil((case.tca_seconds + 180.0) / step_seconds)))
        local_collisions = 0
        local_maneuvers = 0
        for _ in range(steps_needed):
            step_result = client.post_json("/api/simulate/step", {"step_seconds": step_seconds})
            local_collisions += int(step_result.get("collisions_detected", 0))
            local_maneuvers += int(step_result.get("maneuvers_executed", 0))

        collisions += local_collisions
        maneuvers += local_maneuvers
        if local_collisions == 0 and local_maneuvers >= 1:
            cases_avoided += 1

        cases.append({
            "sat_id": case.sat_id,
            "deb_id": case.deb_id,
            "target_tca_seconds": case.tca_seconds,
            "initial_miss_km": case.miss_distance_km,
            "initial_relative_speed_kms": case.relative_speed_kms,
            "initial_cdm_seen": bool(initial_cdms),
            "maneuvers_executed": local_maneuvers,
            "collisions_detected": local_collisions,
        })

    return {
        "cases": cases,
        "seeded_cases_run": len(cases),
        "seeded_cases_with_initial_cdm": cases_with_initial_cdm,
        "seeded_cases_avoided": cases_avoided,
        "seeded_total_maneuvers": maneuvers,
        "seeded_total_collisions": collisions,
    }


def load_fixture_satellite_tles() -> List[TLETriple]:
    fixture_path = REPO_ROOT / "tests" / "fixtures" / "public_sample_satellites.tle"
    return load_tles_from_file(fixture_path)


def run_validation_suite(
    *,
    mode: str,
    api_base: str = "http://localhost:8000",
    in_process: bool = False,
    epoch_str: str = "2026-03-28T12:00:00.000Z",
    sat_limit: int = 20,
    debris_limit: int = 500,
    sat_groups: Sequence[str] = ("starlink",),
    debris_groups: Sequence[str] = ("fengyun-1c-debris", "cosmos-2251-debris", "iridium-33-debris"),
    sat_file: Optional[Path] = None,
    debris_file: Optional[Path] = None,
    oracle_sats: int = 5,
    oracle_debris: int = 120,
    oracle_pairs_per_sat: int = 8,
    horizon_hours: float = 24.0,
    seeded_cases: int = 2,
    seeded_step_seconds: int = 30,
) -> Dict[str, Any]:
    require_sgp4()
    started = time.time()
    epoch_dt = parse_iso_z(epoch_str)
    client = InProcessAPIClient() if in_process else LiveAPIClient(api_base)

    if mode == "fixture":
        sat_tles = load_fixture_satellite_tles()
        payload, sat_map = build_fixture_telemetry(sat_tles, epoch_dt, sat_limit=min(sat_limit, 5))
        oracle_block = {
            "telemetry_response": client.post_json("/api/telemetry", payload),
            "snapshot_satellites": len(client.get_json("/api/visualization/snapshot").get("satellites", [])),
            "snapshot_debris": len(client.get_json("/api/visualization/snapshot").get("debris_cloud", [])),
            "backend_cdm_count": len(client.get_json("/api/visualization/snapshot").get("cdm_warnings", [])),
            "oracle_pairs_scanned": 0,
            "oracle_positive_count": 0,
            "oracle_positive_pairs": [],
            "oracle_recall": None,
            "matched_oracle_pairs": 0,
            "median_tca_error_s": None,
            "median_miss_error_km": None,
        }
        dataset_counts = {"satellites_loaded": len([o for o in payload["objects"] if o["type"] == "SATELLITE"]), "debris_loaded": len([o for o in payload["objects"] if o["type"] == "DEBRIS"])}
    elif mode == "local-files":
        if sat_file is None or debris_file is None:
            raise ValueError("sat_file and debris_file are required for local-files mode")
        sat_tles = load_tles_from_file(sat_file)
        deb_tles = load_tles_from_file(debris_file)
        payload, sat_map, deb_map = build_live_telemetry(sat_tles, deb_tles, epoch_dt, sat_limit=sat_limit, debris_limit=debris_limit)
        oracle_block = compare_backend_to_oracle(
            client,
            payload,
            sat_map,
            deb_map,
            epoch_dt,
            max_sats=oracle_sats,
            max_debris=oracle_debris,
            max_pairs_per_sat=oracle_pairs_per_sat,
            horizon_seconds=horizon_hours * 3600.0,
        )
        dataset_counts = {"satellites_loaded": len(sat_map), "debris_loaded": len(deb_map)}
    elif mode == "live":
        sat_tles: List[TLETriple] = []
        for group in sat_groups:
            sat_tles.extend(download_group_tles(group))
        deb_tles: List[TLETriple] = []
        for group in debris_groups:
            deb_tles.extend(download_group_tles(group))
        payload, sat_map, deb_map = build_live_telemetry(sat_tles, deb_tles, epoch_dt, sat_limit=sat_limit, debris_limit=debris_limit)
        oracle_block = compare_backend_to_oracle(
            client,
            payload,
            sat_map,
            deb_map,
            epoch_dt,
            max_sats=oracle_sats,
            max_debris=oracle_debris,
            max_pairs_per_sat=oracle_pairs_per_sat,
            horizon_seconds=horizon_hours * 3600.0,
        )
        dataset_counts = {"satellites_loaded": len(sat_map), "debris_loaded": len(deb_map)}
    else:
        raise ValueError(f"Unknown mode: {mode}")

    seeded_block = run_seeded_collision_campaign(
        client,
        cases_to_run=seeded_cases,
        step_seconds=seeded_step_seconds,
    )

    summary = ValidationSummary(
        mode=mode,
        epoch=epoch_str,
        satellites_loaded=dataset_counts["satellites_loaded"],
        debris_loaded=dataset_counts["debris_loaded"],
        snapshot_satellites=oracle_block["snapshot_satellites"],
        snapshot_debris=oracle_block["snapshot_debris"],
        backend_cdm_count=oracle_block["backend_cdm_count"],
        oracle_pairs_scanned=oracle_block["oracle_pairs_scanned"],
        oracle_positive_count=oracle_block["oracle_positive_count"],
        oracle_recall=oracle_block["oracle_recall"],
        matched_oracle_pairs=oracle_block["matched_oracle_pairs"],
        seeded_cases_run=seeded_block["seeded_cases_run"],
        seeded_cases_with_initial_cdm=seeded_block["seeded_cases_with_initial_cdm"],
        seeded_cases_avoided=seeded_block["seeded_cases_avoided"],
        seeded_total_maneuvers=seeded_block["seeded_total_maneuvers"],
        seeded_total_collisions=seeded_block["seeded_total_collisions"],
        wall_clock_seconds=float(time.time() - started),
    )

    return {
        "summary": asdict(summary),
        "oracle": oracle_block,
        "seeded": seeded_block,
    }
