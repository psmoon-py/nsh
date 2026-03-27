import React from 'react';

const INITIAL_FUEL = 50.0; // kg

function getFuelClass(fuel) {
  const pct = fuel / INITIAL_FUEL;
  if (pct > 0.8) return 'fuel-cell--full';
  if (pct > 0.5) return 'fuel-cell--good';
  if (pct > 0.25) return 'fuel-cell--mid';
  if (pct > 0.05) return 'fuel-cell--low';
  return 'fuel-cell--critical';
}

function getFuelColor(fuel) {
  const pct = fuel / INITIAL_FUEL;
  if (pct > 0.8) return '#00e676';
  if (pct > 0.5) return '#2ecc71';
  if (pct > 0.25) return '#ffab00';
  if (pct > 0.05) return '#e67e22';
  return '#ff3d4a';
}

export default function FuelHeatmap({ satellites = [], selectedSat, onSelectSat }) {
  if (satellites.length === 0) {
    return (
      <div className="empty-state" style={{ height: 80 }}>
        <div className="empty-state__text">No satellites loaded</div>
      </div>
    );
  }

  return (
    <div>
      <div className="fuel-grid">
        {satellites.map((sat) => {
          const fuel = sat.fuel_kg || 0;
          const pct = Math.round((fuel / INITIAL_FUEL) * 100);
          const isSelected = sat.id === selectedSat;

          return (
            <div
              key={sat.id}
              className={`fuel-cell ${getFuelClass(fuel)}`}
              style={{
                outline: isSelected ? '2px solid #00e5ff' : 'none',
                outlineOffset: -1,
              }}
              title={`${sat.id}: ${fuel.toFixed(1)} kg (${pct}%)`}
              onClick={() => onSelectSat(sat.id)}
            >
              {pct}
            </div>
          );
        })}
      </div>

      {/* Mini bar chart: fuel distribution */}
      <div style={{ marginTop: 10, display: 'flex', alignItems: 'flex-end', gap: 1, height: 30 }}>
        {satellites.map((sat) => {
          const pct = (sat.fuel_kg || 0) / INITIAL_FUEL;
          return (
            <div
              key={sat.id}
              style={{
                flex: 1,
                height: `${Math.max(2, pct * 100)}%`,
                background: getFuelColor(sat.fuel_kg || 0),
                opacity: sat.id === selectedSat ? 1 : 0.5,
                borderRadius: '2px 2px 0 0',
                cursor: 'pointer',
                transition: 'opacity 0.15s',
              }}
              onClick={() => onSelectSat(sat.id)}
              title={`${sat.id}: ${(sat.fuel_kg || 0).toFixed(1)} kg`}
            />
          );
        })}
      </div>

      {/* Summary line */}
      <div
        style={{
          marginTop: 6,
          display: 'flex',
          justifyContent: 'space-between',
          fontFamily: "var(--font-mono)",
          fontSize: 9,
          color: 'var(--text-dim)',
        }}
      >
        <span>
          Min: {Math.min(...satellites.map((s) => s.fuel_kg || 0)).toFixed(1)} kg
        </span>
        <span>
          Avg: {(satellites.reduce((a, s) => a + (s.fuel_kg || 0), 0) / satellites.length).toFixed(1)} kg
        </span>
        <span>
          Max: {Math.max(...satellites.map((s) => s.fuel_kg || 0)).toFixed(1)} kg
        </span>
      </div>
    </div>
  );
}
