import React from 'react';

export default function StatusBar({
  timestamp, satCount, debrisCount, nominalCount,
  cdmCount, criticalCount, totalFuel,
  simSpeed, onSimSpeedChange, onAdvance,
  loading, error,
  fleetUptimeExp, totalManeuvers, totalCollisionsAvoided,
}) {
  const timeStr = timestamp !== '—'
    ? new Date(timestamp).toISOString().replace('T', '  ').replace('.000Z', ' UTC')
    : '—';

  return (
    <div className="status-bar">
      {/* Logo + Title */}
      <div className="status-bar__logo">
        <div className="status-bar__logo-icon">
          <svg viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2a10 10 0 100 20 10 10 0 000-20zm0 2a8 8 0 110 16 8 8 0 010-16z" opacity="0.3" />
            <ellipse cx="12" cy="12" rx="10" ry="4" fill="none" stroke="currentColor" strokeWidth="0.7" opacity="0.5" />
          </svg>
        </div>
        <div>
          <div className="status-bar__title">Project AETHER</div>
          <div className="status-bar__subtitle">Autonomous Constellation Manager</div>
        </div>
      </div>

      {/* Metrics */}
      <div className="status-bar__metrics">
        <div className="metric">
          <span className="metric__label">Satellites</span>
          <span className="metric__value">{satCount}</span>
        </div>
        <div className="metric">
          <span className="metric__label">Nominal</span>
          <span className="metric__value metric__value--green">{nominalCount}</span>
        </div>
        <div className="metric">
          <span className="metric__label">Debris</span>
          <span className="metric__value">{debrisCount.toLocaleString()}</span>
        </div>
        <div className="metric">
          <span className="metric__label">CDMs</span>
          <span className={`metric__value ${cdmCount > 0 ? 'metric__value--amber' : 'metric__value--green'}`}>
            {cdmCount}
          </span>
        </div>
        <div className="metric">
          <span className="metric__label">Critical</span>
          <span className={`metric__value ${criticalCount > 0 ? 'metric__value--red' : 'metric__value--green'}`}>
            {criticalCount}
          </span>
        </div>
        <div className="metric">
          <span className="metric__label">Uptime</span>
          <span className="metric__value metric__value--green">
            {fleetUptimeExp != null ? `${(fleetUptimeExp * 100).toFixed(1)}%` : '—'}
          </span>
        </div>
        <div className="metric">
          <span className="metric__label">Avoided</span>
          <span className="metric__value metric__value--green">{totalCollisionsAvoided}</span>
        </div>

        {/* Sim controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 12 }}>
          <select
            value={simSpeed}
            onChange={(e) => onSimSpeedChange(Number(e.target.value))}
            style={{
              background: 'var(--surface-raised)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-mono)', fontSize: 10,
              padding: '3px 6px', borderRadius: 3, cursor: 'pointer',
            }}
          >
            <option value={10}>+10s</option>
            <option value={60}>+1m</option>
            <option value={300}>+5m</option>
            <option value={600}>+10m</option>
            <option value={3600}>+1h</option>
            <option value={86400}>+24h</option>
          </select>
          <button
            onClick={onAdvance}
            disabled={loading}
            style={{
              background: loading ? 'var(--surface-raised)' : 'var(--cyan)',
              color: loading ? 'var(--text-dim)' : '#000',
              border: 'none', padding: '5px 14px', borderRadius: 3,
              fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 10,
              textTransform: 'uppercase', letterSpacing: 1.5,
              cursor: loading ? 'wait' : 'pointer',
              transition: 'all 0.15s',
            }}
          >
            {loading ? '⟳' : '▶'} {loading ? 'RUNNING' : 'ADVANCE'}
          </button>
        </div>
      </div>

      {/* Sim Time */}
      <div className="status-bar__time">
        <div className="status-bar__sim-time">{timeStr}</div>
        <div className="status-bar__sim-label">
          Simulation Epoch
          {error && <span style={{ color: 'var(--red)', marginLeft: 8 }}>● OFFLINE</span>}
        </div>
      </div>
    </div>
  );
}
