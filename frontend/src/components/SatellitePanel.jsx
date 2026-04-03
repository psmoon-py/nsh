import React from 'react';

const INITIAL_FUEL = 50.0;

function getFuelColor(pct) {
  if (pct > 0.6) return 'var(--good)';
  if (pct > 0.25) return 'var(--accent-2)';
  return 'var(--danger)';
}

export default function SatellitePanel({ satellite }) {
  if (!satellite) {
    return (
      <div className="empty-state">
        <div className="empty-state__text">Select a satellite to inspect detailed state.</div>
      </div>
    );
  }

  const fuelPct = (satellite.fuel_kg || 0) / INITIAL_FUEL;
  const fuelColor = getFuelColor(fuelPct);

  let altitude = satellite.alt;
  if (!altitude && satellite.r) {
    const rMag = Math.sqrt(satellite.r.x ** 2 + satellite.r.y ** 2 + satellite.r.z ** 2);
    altitude = rMag - 6378.137;
  }

  return (
    <div className="sat-detail">
      <div className="sat-detail__row"><span className="sat-detail__key">ID</span><span className="sat-detail__val sat-detail__val--accent">{satellite.id}</span></div>
      <div className="sat-detail__row"><span className="sat-detail__key">Status</span><span className="sat-detail__val">{satellite.status}</span></div>
      <div className="sat-detail__row"><span className="sat-detail__key">Lat / Lon</span><span className="sat-detail__val">{satellite.lat?.toFixed(2)}° / {satellite.lon?.toFixed(2)}°</span></div>
      <div className="sat-detail__row"><span className="sat-detail__key">Altitude</span><span className="sat-detail__val">{altitude != null ? `${altitude.toFixed(1)} km` : '—'}</span></div>
      {satellite.r && (
        <div className="sat-detail__row sat-detail__row--stacked">
          <span className="sat-detail__key">ECI (km)</span>
          <span className="sat-detail__val sat-detail__val--mono">[{satellite.r.x?.toFixed(1)}, {satellite.r.y?.toFixed(1)}, {satellite.r.z?.toFixed(1)}]</span>
        </div>
      )}

      <div className="sat-detail__row"><span className="sat-detail__key">Propellant</span><span className="sat-detail__val" style={{ color: fuelColor }}>{(satellite.fuel_kg || 0).toFixed(2)} kg ({Math.round(fuelPct * 100)}%)</span></div>
      <div className="sat-detail__fuel-bar"><div className="sat-detail__fuel-fill" style={{ width: `${Math.max(1, fuelPct * 100)}%`, background: fuelColor }} /></div>

      {fuelPct <= 0.05 && <div className="sat-alert">EOL threshold reached. Graveyard transfer required.</div>}

      <div className="sat-detail__row"><span className="sat-detail__key">Dry Mass</span><span className="sat-detail__val">500.0 kg</span></div>
      <div className="sat-detail__row"><span className="sat-detail__key">Wet Mass</span><span className="sat-detail__val">{(500 + (satellite.fuel_kg || 0)).toFixed(2)} kg</span></div>
      <div className="sat-detail__row"><span className="sat-detail__key">Isp</span><span className="sat-detail__val">300.0 s</span></div>
    </div>
  );
}
