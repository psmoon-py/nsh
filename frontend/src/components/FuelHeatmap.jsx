import React from 'react';

const INITIAL_FUEL = 50.0;

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

export default function FuelHeatmap({
  satellites = [], selectedSat, onSelectSat,
  totalCollisionsAvoided = 0, totalFuelConsumed = 0,
}) {
  if (satellites.length === 0) {
    return (
      <div className="empty-state" style={{ height: 80 }}>
        <div className="empty-state__text">No satellites loaded</div>
      </div>
    );
  }

  return (
    <div>
      {/* Fuel Grid Heatmap */}
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

      {/* Mini bar chart */}
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
                cursor: 'pointer', transition: 'opacity 0.15s',
              }}
              onClick={() => onSelectSat(sat.id)}
              title={`${sat.id}: ${(sat.fuel_kg || 0).toFixed(1)} kg`}
            />
          );
        })}
      </div>

      {/* Summary line */}
      <div style={{
        marginTop: 6, display: 'flex', justifyContent: 'space-between',
        fontFamily: "var(--font-mono)", fontSize: 9, color: 'var(--text-dim)',
      }}>
        <span>Min: {Math.min(...satellites.map((s) => s.fuel_kg || 0)).toFixed(1)} kg</span>
        <span>Avg: {(satellites.reduce((a, s) => a + (s.fuel_kg || 0), 0) / satellites.length).toFixed(1)} kg</span>
        <span>Max: {Math.max(...satellites.map((s) => s.fuel_kg || 0)).toFixed(1)} kg</span>
      </div>

      {/* ═══ Fuel Consumed vs Collisions Avoided (PS Required) ═══ */}
      <div style={{
        marginTop: 12, paddingTop: 10,
        borderTop: '1px solid var(--border)',
      }}>
        <div style={{
          fontSize: 9, textTransform: 'uppercase', letterSpacing: 1,
          color: 'var(--text-dim)', fontWeight: 600, marginBottom: 8,
        }}>
          ΔV Cost Analysis
        </div>

        {/* Simple scatter-style visualization */}
        <svg viewBox="0 0 280 80" style={{ width: '100%', height: 'auto' }}>
          {/* Axes */}
          <line x1={30} y1={70} x2={270} y2={70} stroke="#1e2a3e" strokeWidth={0.5} />
          <line x1={30} y1={10} x2={30} y2={70} stroke="#1e2a3e" strokeWidth={0.5} />

          {/* Axis labels */}
          <text x={150} y={79} fill="#4a5a72" fontSize={6}
            fontFamily="'IBM Plex Mono', monospace" textAnchor="middle">
            Fuel Consumed (kg)
          </text>
          <text x={5} y={40} fill="#4a5a72" fontSize={6}
            fontFamily="'IBM Plex Mono', monospace"
            transform="rotate(-90 5 40)" textAnchor="middle">
            Evasions
          </text>

          {/* Per-satellite dots: x = fuel consumed, y = number of maneuvers (estimated from fuel usage) */}
          {satellites.map((sat, i) => {
            const fuelUsed = INITIAL_FUEL - (sat.fuel_kg || 0);
            const maxFuelAxis = Math.max(INITIAL_FUEL * 0.5, 10);
            const x = 30 + (fuelUsed / maxFuelAxis) * 240;
            // Estimate maneuvers from fuel used (each evasion ~0.5-2 kg)
            const estManeuvers = Math.round(fuelUsed / 1.2);
            const maxManeuvers = 20;
            const y = 70 - (Math.min(estManeuvers, maxManeuvers) / maxManeuvers) * 55;

            const isSelected = sat.id === selectedSat;
            const isNominal = sat.status === 'NOMINAL';
            const color = isSelected ? '#00e5ff' : isNominal ? '#00e676' : '#ffab00';

            return (
              <g key={sat.id} onClick={() => onSelectSat(sat.id)} style={{ cursor: 'pointer' }}>
                <circle cx={Math.min(x, 268)} cy={Math.max(y, 12)} r={isSelected ? 4 : 2.5}
                  fill={color} opacity={0.8} />
                {isSelected && (
                  <text x={Math.min(x, 268) + 6} y={Math.max(y, 12) + 3}
                    fill={color} fontSize={5} fontFamily="'IBM Plex Mono', monospace">
                    {sat.id.replace('SAT-Alpha-', 'A')}
                  </text>
                )}
              </g>
            );
          })}

          {/* Grid lines */}
          {[0.25, 0.5, 0.75].map((frac) => (
            <line key={frac} x1={30} y1={70 - frac * 60} x2={270} y2={70 - frac * 60}
              stroke="#1e2a3e" strokeWidth={0.3} strokeDasharray="2 3" />
          ))}
        </svg>

        {/* Fleet summary */}
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-dim)',
          marginTop: 4,
        }}>
          <span>Fleet ΔV: {totalFuelConsumed.toFixed(1)} kg</span>
          <span>Evasions: {totalCollisionsAvoided}</span>
        </div>
      </div>
    </div>
  );
}
