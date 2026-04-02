import React, { useMemo } from 'react';

const INITIAL_FUEL = 50.0;

function getFuelClass(fuel) {
  const pct = fuel / INITIAL_FUEL;
  if (pct > 0.8)  return 'fuel-cell--full';
  if (pct > 0.5)  return 'fuel-cell--good';
  if (pct > 0.25) return 'fuel-cell--mid';
  if (pct > 0.05) return 'fuel-cell--low';
  return 'fuel-cell--critical';
}

function getFuelColor(fuel) {
  const pct = fuel / INITIAL_FUEL;
  if (pct > 0.8)  return '#00e676';
  if (pct > 0.5)  return '#2ecc71';
  if (pct > 0.25) return '#ffab00';
  if (pct > 0.05) return '#e67e22';
  return '#ff3b3b';
}

/**
 * Fleet Fuel Heatmap + real ΔV efficiency chart from backend metrics_history.
 *
 * FIX: removed fake per-satellite maneuver estimate (estManeuvers = fuelUsed / 1.2).
 * Now uses actual cumulative data from metrics_history.
 */
export default function FuelHeatmap({
  satellites = [], selectedSat, onSelectSat,
  totalCollisionsAvoided = 0, totalFuelConsumed = 0,
  metricsHistory = [],
}) {
  if (satellites.length === 0) {
    return (
      <div className="empty-state" style={{ height: 80 }}>
        <div className="empty-state__text">No satellites loaded</div>
      </div>
    );
  }

  // Build efficiency curve from metrics_history
  const efficiencyData = useMemo(() => {
    if (metricsHistory.length < 2) return null;
    const initial = metricsHistory[0]?.fleet_fuel_kg || (satellites.length * INITIAL_FUEL);
    return metricsHistory.map((m) => ({
      fuelConsumed: Math.max(0, initial - (m.fleet_fuel_kg || 0)),
      evasions:     m.collisions_avoided || 0,
    }));
  }, [metricsHistory, satellites.length]);

  return (
    <div>
      {/* ─── Fuel Grid ─── */}
      <div className="fuel-grid">
        {satellites.map((sat) => {
          const fuel      = sat.fuel_kg || 0;
          const pct       = Math.round((fuel / INITIAL_FUEL) * 100);
          const isSelected = sat.id === selectedSat;
          return (
            <div
              key={sat.id}
              className={`fuel-cell ${getFuelClass(fuel)}`}
              style={{ outline: isSelected ? '2px solid #00e5ff' : 'none', outlineOffset: -1 }}
              title={`${sat.id}: ${fuel.toFixed(1)} kg (${pct}%)`}
              onClick={() => onSelectSat(sat.id)}
            >
              {pct}
            </div>
          );
        })}
      </div>

      {/* ─── Mini bar chart ─── */}
      <div style={{ marginTop: 8, display: 'flex', alignItems: 'flex-end', gap: 1, height: 28 }}>
        {satellites.map((sat) => {
          const pct = (sat.fuel_kg || 0) / INITIAL_FUEL;
          return (
            <div key={sat.id} style={{
              flex: 1,
              height: `${Math.max(3, pct * 100)}%`,
              background: getFuelColor(sat.fuel_kg || 0),
              opacity: sat.id === selectedSat ? 1 : 0.55,
              borderRadius: '1px 1px 0 0',
              cursor: 'pointer', transition: 'opacity 0.15s',
            }} onClick={() => onSelectSat(sat.id)} title={`${sat.id}: ${(sat.fuel_kg||0).toFixed(1)} kg`} />
          );
        })}
      </div>

      {/* ─── Summary ─── */}
      <div style={{
        marginTop: 5, display: 'flex', justifyContent: 'space-between',
        fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-dim)',
      }}>
        <span>Min: {Math.min(...satellites.map(s => s.fuel_kg||0)).toFixed(1)} kg</span>
        <span>Avg: {(satellites.reduce((a,s)=>a+(s.fuel_kg||0),0)/satellites.length).toFixed(1)} kg</span>
        <span>Max: {Math.max(...satellites.map(s => s.fuel_kg||0)).toFixed(1)} kg</span>
      </div>

      {/* ─── ΔV Cost Analysis (real backend data) ─── */}
      <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: 8, textTransform: 'uppercase',
          letterSpacing: 1.5, color: 'var(--text-dim)', marginBottom: 6,
        }}>
          ΔV Cost Analysis
        </div>

        {efficiencyData && efficiencyData.length >= 2 ? (
          <svg viewBox="0 0 280 75" style={{ width: '100%', height: 'auto' }}>
            {/* Axes */}
            <line x1={30} y1={65} x2={270} y2={65} stroke="#1e2a3e" strokeWidth={0.6} />
            <line x1={30} y1={10} x2={30}  y2={65} stroke="#1e2a3e" strokeWidth={0.6} />

            {/* Axis labels */}
            <text x={150} y={74} fill="#3a4a62" fontSize={6}
              fontFamily="'JetBrains Mono', monospace" textAnchor="middle">
              Fleet Fuel Consumed (kg)
            </text>
            <text x={5} y={38} fill="#3a4a62" fontSize={6}
              fontFamily="'JetBrains Mono', monospace"
              transform="rotate(-90 5 38)" textAnchor="middle">
              Evasions
            </text>

            {/* Efficiency curve */}
            {(() => {
              const maxFuel  = Math.max(...efficiencyData.map(d => d.fuelConsumed), 1);
              const maxEvas  = Math.max(...efficiencyData.map(d => d.evasions), 1);
              const pts = efficiencyData.map(d => {
                const x = 30 + (d.fuelConsumed / maxFuel) * 240;
                const y = 65 - (d.evasions / maxEvas) * 52;
                return `${Math.min(x,268)},${Math.max(y,12)}`;
              }).join(' ');
              return (
                <>
                  <polyline points={pts} fill="none"
                    stroke="var(--cyan)" strokeWidth={1.2} opacity={0.6} />
                  {efficiencyData.filter((_, i) => i % 10 === 0).map((d, i) => {
                    const x = 30 + (d.fuelConsumed / maxFuel) * 240;
                    const y = 65 - (d.evasions / maxEvas) * 52;
                    return (
                      <circle key={i} cx={Math.min(x,268)} cy={Math.max(y,12)}
                        r={1.5} fill="var(--cyan)" opacity={0.7} />
                    );
                  })}
                </>
              );
            })()}

            {/* Grid lines */}
            {[0.25, 0.5, 0.75].map(f => (
              <line key={f} x1={30} y1={65 - f*52} x2={270} y2={65 - f*52}
                stroke="#1e2a3e" strokeWidth={0.3} strokeDasharray="2 4" />
            ))}
          </svg>
        ) : (
          /* Fallback scatter for current state */
          <svg viewBox="0 0 280 75" style={{ width: '100%', height: 'auto' }}>
            <line x1={30} y1={65} x2={270} y2={65} stroke="#1e2a3e" strokeWidth={0.6} />
            <line x1={30} y1={10} x2={30}  y2={65} stroke="#1e2a3e" strokeWidth={0.6} />
            <text x={150} y={74} fill="#3a4a62" fontSize={6}
              fontFamily="'JetBrains Mono', monospace" textAnchor="middle">
              Fleet Fuel Consumed (kg)
            </text>
            {satellites.map((sat) => {
              const fuelUsed = INITIAL_FUEL - (sat.fuel_kg || 0);
              const x = 30 + (fuelUsed / Math.max(INITIAL_FUEL * 0.5, 1)) * 240;
              const color = getFuelColor(sat.fuel_kg || 0);
              return (
                <circle key={sat.id}
                  cx={Math.min(x, 268)} cy={37}
                  r={sat.id === selectedSat ? 4 : 2}
                  fill={color} opacity={0.7}
                  onClick={() => onSelectSat(sat.id)}
                  style={{ cursor: 'pointer' }}
                />
              );
            })}
          </svg>
        )}

        <div style={{
          display: 'flex', justifyContent: 'space-between', marginTop: 3,
          fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-dim)',
        }}>
          <span style={{ color: 'var(--cyan)' }}>ΔV: {totalFuelConsumed.toFixed(1)} kg</span>
          <span style={{ color: 'var(--green)' }}>✓ {totalCollisionsAvoided} avoided</span>
        </div>
      </div>
    </div>
  );
}
