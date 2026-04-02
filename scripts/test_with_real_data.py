from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from real_data_validation_lib import run_validation_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real-data ACM validation suite")
    parser.add_argument("--mode", choices=["fixture", "local-files", "live"], default="fixture")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--in-process", action="store_true", help="Use FastAPI TestClient instead of a live server")
    parser.add_argument("--epoch", default="2026-03-28T12:00:00.000Z")
    parser.add_argument("--sat-limit", type=int, default=20)
    parser.add_argument("--debris-limit", type=int, default=500)
    parser.add_argument("--sat-file", type=Path)
    parser.add_argument("--debris-file", type=Path)
    parser.add_argument("--sat-groups", default="starlink")
    parser.add_argument("--debris-groups", default="fengyun-1c-debris,cosmos-2251-debris,iridium-33-debris")
    parser.add_argument("--oracle-sats", type=int, default=5)
    parser.add_argument("--oracle-debris", type=int, default=120)
    parser.add_argument("--oracle-pairs-per-sat", type=int, default=8)
    parser.add_argument("--horizon-hours", type=float, default=24.0)
    parser.add_argument("--seeded-cases", type=int, default=2)
    parser.add_argument("--seeded-step-seconds", type=int, default=30)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = run_validation_suite(
        mode=args.mode,
        api_base=args.api_base,
        in_process=args.in_process,
        epoch_str=args.epoch,
        sat_limit=args.sat_limit,
        debris_limit=args.debris_limit,
        sat_groups=[s.strip() for s in args.sat_groups.split(",") if s.strip()],
        debris_groups=[s.strip() for s in args.debris_groups.split(",") if s.strip()],
        sat_file=args.sat_file,
        debris_file=args.debris_file,
        oracle_sats=args.oracle_sats,
        oracle_debris=args.oracle_debris,
        oracle_pairs_per_sat=args.oracle_pairs_per_sat,
        horizon_hours=args.horizon_hours,
        seeded_cases=args.seeded_cases,
        seeded_step_seconds=args.seeded_step_seconds,
    )

    print(json.dumps(report, indent=2))
    if args.report_json:
        args.report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote report to {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
