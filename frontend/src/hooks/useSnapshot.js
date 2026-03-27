import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = '/api';
const POLL_INTERVAL = 2000; // 2 seconds

/**
 * Polls GET /api/visualization/snapshot every POLL_INTERVAL ms.
 * Returns { data, loading, error, refresh }
 */
export default function useSnapshot() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const fetchSnapshot = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/visualization/snapshot`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      // Don't clear existing data on error — keep last good state
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSnapshot();
    intervalRef.current = setInterval(fetchSnapshot, POLL_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [fetchSnapshot]);

  return { data, loading, error, refresh: fetchSnapshot };
}

/**
 * Post a simulation step command.
 */
export async function postSimulateStep(stepSeconds = 60) {
  const res = await fetch(`${API_BASE}/simulate/step`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ step_seconds: stepSeconds }),
  });
  return res.json();
}

/**
 * Post telemetry data.
 */
export async function postTelemetry(timestamp, objects) {
  const res = await fetch(`${API_BASE}/telemetry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ timestamp, objects }),
  });
  return res.json();
}

/**
 * Schedule a maneuver.
 */
export async function postManeuver(satelliteId, maneuverSequence) {
  const res = await fetch(`${API_BASE}/maneuver/schedule`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ satelliteId, maneuver_sequence: maneuverSequence }),
  });
  return res.json();
}
