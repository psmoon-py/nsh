import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = '/api';
const POLL_INTERVAL = 2000; // 2 seconds

/**
 * Polls GET /api/visualization/snapshot every POLL_INTERVAL ms.
 * Uses request locking and AbortController to prevent overlapping fetches.
 * Returns { data, loading, error, refresh }
 */
export default function useSnapshot() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const intervalRef  = useRef(null);
  const inFlightRef  = useRef(false);
  const abortRef     = useRef(null);
  const pausedRef    = useRef(false);

  const fetchSnapshot = useCallback(async () => {
    if (inFlightRef.current || pausedRef.current) return;

    // Abort any lingering previous request
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch (_) {}
    }
    const controller = new AbortController();
    abortRef.current = controller;
    inFlightRef.current = true;

    try {
      const res = await fetch(`${API_BASE}/visualization/snapshot`, {
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError(err.message);
      }
    } finally {
      inFlightRef.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSnapshot();
    intervalRef.current = setInterval(fetchSnapshot, POLL_INTERVAL);
    return () => {
      clearInterval(intervalRef.current);
      if (abortRef.current) {
        try { abortRef.current.abort(); } catch (_) {}
      }
    };
  }, [fetchSnapshot]);

  return { data, loading, error, refresh: fetchSnapshot };
}

/**
 * Post a simulation step. Pauses polling during the request.
 */
export async function postSimulateStep(stepSeconds = 60, pauseRef = null) {
  try {
    const res = await fetch(`${API_BASE}/simulate/step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step_seconds: stepSeconds }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('postSimulateStep failed:', err);
    return null;
  }
}

export async function postTelemetry(timestamp, objects) {
  const res = await fetch(`${API_BASE}/telemetry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ timestamp, objects }),
  });
  return res.json();
}

export async function postManeuver(satelliteId, maneuverSequence) {
  const res = await fetch(`${API_BASE}/maneuver/schedule`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ satelliteId, maneuver_sequence: maneuverSequence }),
  });
  return res.json();
}
