import React from 'react';

const INITIAL_FUEL = 50.0;

function getFuelColor(pct) {
  if (pct > 0.6) return 'var(--green)';
  if (pct > 0.25) return 'var(--amber)';
  return 'var(--red)';
}

export default function SatellitePanel({ satellite }) {
  if (!satellite) {
    return (
      <div className="empty-state" style={{ height: 120 }}>
        <div className="empty-state__icon">🛰</div>
        <div className="empty-state__text">Click a satellite on the globe</div>
      </div>
    );
  }

  const fuelPct = (satellite.fuel_kg || 0) / INITIAL_FUEL;
  const fuelColor = getFuelColor(fuelPct);

  // Compute altitude from ECI if available
  let altitude = satellite.alt;
  if (!altitude && satellite.r) {
    const rMag = Math.sqrt(
      satellite.r.x ** 2 + satellite.r.y ** 2 + satellite.r.z ** 2
    );
    altitude = rMag - 6378.137;
  }

  return (
    <div className="sat-detail">
      {/* ID */}
      <div className="sat-detail__row">
        <span className="sat-detail__key">ID</span>
        <span className="sat-detail__val" style={{ color: 'var(--cyan)' }}>
          {satellite.id}
        </span>
      </div>

      {/* Status */}
      <div className="sat-detail__row">
        <span className="sat-detail__key">Status</span>
        <span
          className="sat-detail__val"
          style={{
            color:
              satellite.status === 'NOMINAL' ? 'var(--green)' : 'var(--amber)',
          }}
        >
          {satellite.status}
        </span>
      </div>

      {/* Position */}
      <div className="sat-detail__row">
        <span className="sat-detail__key">Lat / Lon</span>
        <span className="sat-detail__val">
          {satellite.lat?.toFixed(2)}° / {satellite.lon?.toFixed(2)}°
        </span>
      </div>

      {/* Altitude */}
      <div className="sat-detail__row">
        <span className="sat-detail__key">Altitude</span>
        <span className="sat-detail__val">
          {altitude != null ? `${altitude.toFixed(1)} km` : '—'}
        </span>
      </div>

      {/* ECI Position if available */}
      {satellite.r && (
        <div className="sat-detail__row">
          <span className="sat-detail__key">ECI (km)</span>
          <span className="sat-detail__val" style={{ fontSize: 10 }}>
            [{satellite.r.x?.toFixed(1)}, {satellite.r.y?.toFixed(1)},{' '}
            {satellite.r.z?.toFixed(1)}]
          </span>
        </div>
      )}

      {/* Fuel */}
      <div style={{ marginTop: 4 }}>
        <div className="sat-detail__row">
          <span className="sat-detail__key">Propellant</span>
          <span className="sat-detail__val" style={{ color: fuelColor }}>
            {(satellite.fuel_kg || 0).toFixed(2)} kg ({Math.round(fuelPct * 100)}%)
          </span>
        </div>
        <div className="sat-detail__fuel-bar">
          <div
            className="sat-detail__fuel-fill"
            style={{
              width: `${Math.max(1, fuelPct * 100)}%`,
              background: fuelColor,
            }}
          />
        </div>
      </div>

      {/* Fuel warning */}
      {fuelPct <= 0.05 && (
        <div
          style={{
            marginTop: 6,
            padding: '4px 8px',
            background: 'var(--red-glow)',
            border: '1px solid var(--red-dim)',
            borderRadius: 4,
            fontSize: 9,
            fontFamily: "var(--font-mono)",
            color: 'var(--red)',
            textAlign: 'center',
          }}
        >
          ⚠ EOL THRESHOLD — GRAVEYARD ORBIT REQUIRED
        </div>
      )}

      {/* Mass budget */}
      <div className="sat-detail__row" style={{ marginTop: 4 }}>
        <span className="sat-detail__key">Dry Mass</span>
        <span className="sat-detail__val">500.0 kg</span>
      </div>
      <div className="sat-detail__row">
        <span className="sat-detail__key">Wet Mass</span>
        <span className="sat-detail__val">
          {(500.0 + (satellite.fuel_kg || 0)).toFixed(2)} kg
        </span>
      </div>
      <div className="sat-detail__row">
        <span className="sat-detail__key">Isp</span>
        <span className="sat-detail__val">300.0 s</span>
      </div>
    </div>
  );
}
