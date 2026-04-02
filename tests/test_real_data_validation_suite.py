from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("sgp4")

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from real_data_validation_lib import load_fixture_satellite_tles, parse_iso_z, run_validation_suite


@pytest.mark.slow
def test_fixture_validation_suite_smoke() -> None:
    triples = load_fixture_satellite_tles()
    assert len(triples) >= 3

    report = run_validation_suite(
        mode="fixture",
        in_process=True,
        epoch_str="2026-03-28T12:00:00.000Z",
        sat_limit=3,
        seeded_cases=1,
        seeded_step_seconds=30,
    )

    summary = report["summary"]
    assert summary["satellites_loaded"] >= 3
    assert summary["debris_loaded"] >= 3
    assert summary["snapshot_satellites"] >= 3
    assert summary["seeded_cases_run"] == 1
    assert summary["seeded_cases_with_initial_cdm"] == 1
    assert summary["seeded_cases_avoided"] == 1
    assert summary["seeded_total_collisions"] == 0


def test_fixture_epoch_parser() -> None:
    dt = parse_iso_z("2026-03-28T12:00:00.000Z")
    assert dt.year == 2026
    assert dt.month == 3
    assert dt.day == 28
