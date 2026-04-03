"""Small in-process backend stress run for hackathon confidence."""
from __future__ import annotations

import importlib
import time
from fastapi.testclient import TestClient


def main():
    import backend.main as backend_main
    backend_main = importlib.reload(backend_main)
    backend_main.reset_world(load_defaults=True)
    client = TestClient(backend_main.app)

    steps = [60, 300, 600, 1800]
    print('== Backend stress smoke ==')
    for step in steps:
        t0 = time.perf_counter()
        resp = client.post('/api/simulate/step', json={'step_seconds': step})
        resp.raise_for_status()
        dt = time.perf_counter() - t0
        data = resp.json()
        print(f'step={step:4d}s -> wall={dt:.3f}s collisions={data.get("collisions_detected", 0)} maneuvers={data.get("maneuvers_executed", 0)}')

    snap = client.get('/api/visualization/snapshot')
    snap.raise_for_status()
    js = snap.json()
    print(f'snapshot: sats={len(js.get("satellites", []))} debris={len(js.get("debris_cloud", []))} cdms={len(js.get("cdm_warnings", []))}')


if __name__ == '__main__':
    main()
