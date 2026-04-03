import React, { useMemo } from 'react';

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
  return '#ff3b3b';
}

export default function FuelHeatmap({
  satellites = [], selectedSat, onSelectSat,
  totalCollisionsAvoided = 0, totalFuelConsumed = 0,
  metricsHistory = [],
}) {
  if (!satellites.length) {
    return <div className="empty-state"><div className="empty-state__text">No satellites loaded</div></div>;
  }

  const efficiencyData = useMemo(() => {
    if (metricsHistory.length < 2) return null;
    const initial = metricsHistory[0]?.fleet_fuel_kg || (satellites.length * INITIAL_FUEL);
    return metricsHistory.map((m) => ({
      fuelConsumed: Math.max(0, initial - (m.fleet_fuel_kg || 0)),
      evasions: m.collisions_avoided || 0,
    }));
  }, [metricsHistory, satellites.length]);

  const minFuel = Math.min(...satellites.map(s => s.fuel_kg || 0));
  const avgFuel = satellites.reduce((a, s) => a + (s.fuel_kg || 0), 0) / satellites.length;
  const maxFuel = Math.max(...satellites.map(s => s.fuel_kg || 0));

  return (
    <div className="fleet-pane">
      <div className="fleet-grid">
        {satellites.map((sat) => {
          const fuel = sat.fuel_kg || 0;
          const pct = Math.round((fuel / INITIAL_FUEL) * 100);
          const isSelected = sat.id === selectedSat;
          return (
            <button
              key={sat.id}
              type="button"
              className={`fuel-cell ${getFuelClass(fuel)} ${isSelected ? 'fuel-cell--selected' : ''}`}
              title={`${sat.id}: ${fuel.toFixed(2)} kg (${pct}%)`}
              onClick={() => onSelectSat?.(sat.id)}
            />
          );
        })}
      </div>

      <div className="fleet-summary-row">
        <span>Min: {minFuel.toFixed(1)} kg</span>
        <span>Avg: {avgFuel.toFixed(1)} kg</span>
        <span>Max: {maxFuel.toFixed(1)} kg</span>
      </div>

      <div className="fleet-chart-block">
        <div className="fleet-chart-title">Fuel consumed vs evasions</div>
        {efficiencyData && efficiencyData.length >= 2 ? (
          <svg viewBox="0 0 280 82" className="fleet-chart-svg">
            <line x1="30" y1="68" x2="270" y2="68" stroke="#1d2736" strokeWidth="0.8" />
            <line x1="30" y1="14" x2="30" y2="68" stroke="#1d2736" strokeWidth="0.8" />
            {(() => {
              const maxF = Math.max(...efficiencyData.map(d => d.fuelConsumed), 1);
              const maxE = Math.max(...efficiencyData.map(d => d.evasions), 1);
              const pts = efficiencyData.map(d => {
                const x = 30 + (d.fuelConsumed / maxF) * 240;
                const y = 68 - (d.evasions / maxE) * 50;
                return `${x},${y}`;
              }).join(' ');
              return <polyline points={pts} fill="none" stroke="#24D3FF" strokeWidth="1.2" opacity="0.85" />;
            })()}
          </svg>
        ) : (
          <div className="fleet-chart-empty">No maneuver history yet. Most satellites still show 100% because they start with the same initial propellant budget and have not spent fuel.</div>
        )}
        <div className="fleet-summary-row fleet-summary-row--footer">
          <span>ΔV: {totalFuelConsumed.toFixed(1)} kg</span>
          <span>✓ {totalCollisionsAvoided} avoided</span>
        </div>
      </div>
    </div>
  );
}
