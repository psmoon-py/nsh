import React, { useMemo } from 'react';

const COOLDOWN_SECONDS = 600;
const WINDOW_HOURS = 2;

/**
 * Maneuver Timeline (Gantt-style scheduler).
 *
 * Shows burn start/end blocks, 600s cooldown windows, and conflict flags.
 * Uses burn_duration_seconds from backend (impulsive = 1s nominal).
 * Dims past burns, brightens future.
 */
export default function ManeuverGantt({ maneuvers = [], satellites = [], timestamp }) {
  const now          = timestamp ? new Date(timestamp).getTime() : Date.now();
  const windowStart  = now - WINDOW_HOURS * 3600 * 1000;
  const windowEnd    = now + WINDOW_HOURS * 3600 * 1000;
  const windowDur    = windowEnd - windowStart;

  const tracks = useMemo(() => {
    const groups = {};
    maneuvers.forEach((m) => {
      if (!groups[m.sat_id]) groups[m.sat_id] = [];
      const burnMs = new Date(m.burn_time).getTime();
      groups[m.sat_id].push({
        ...m,
        burnMs,
        type: (m.burn_id?.includes('RECOV') || m.burn_type === 'RECOVERY') ? 'recovery' : 'evasion',
        isPast: burnMs < now,
      });
    });
    return Object.entries(groups)
      .slice(0, 8)
      .map(([satId, burns]) => ({
        satId,
        burns: burns.sort((a, b) => a.burnMs - b.burnMs),
      }));
  }, [maneuvers, now]);

  const t2pct = (ms) => ((ms - windowStart) / windowDur) * 100;

  if (tracks.length === 0) {
    return (
      <div className="empty-state" style={{ height: '100%' }}>
        <div className="empty-state__icon">⏱</div>
        <div className="empty-state__text">No maneuvers scheduled</div>
      </div>
    );
  }

  return (
    <div className="gantt-container" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Time axis */}
      <div style={{ display: 'flex', marginLeft: 84, marginBottom: 3, position: 'relative', height: 12 }}>
        {[-2, -1, 0, 1, 2].map((h) => {
          const pct = ((h + WINDOW_HOURS) / (WINDOW_HOURS * 2)) * 100;
          return (
            <span key={h} style={{
              position: 'absolute', left: `${pct}%`,
              transform: 'translateX(-50%)',
              fontSize: 7, fontFamily: 'var(--font-mono)',
              color: h === 0 ? 'var(--cyan)' : 'var(--text-dim)',
              whiteSpace: 'nowrap',
            }}>
              {h === 0 ? 'NOW' : `${h>0?'+':''}${h}h`}
            </span>
          );
        })}
      </div>

      {/* Tracks */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {tracks.map((track) => (
          <div className="gantt-track" key={track.satId}>
            <div className="gantt-track__label">{track.satId}</div>
            <div className="gantt-track__bar-area">
              {/* NOW marker */}
              <div style={{
                position: 'absolute', left: `${t2pct(now)}%`,
                top: 0, bottom: 0, width: 1,
                background: 'var(--cyan)', opacity: 0.6, zIndex: 5,
              }} />

              {track.burns.map((burn, i) => {
                const burnDur   = (burn.burn_duration_seconds || 1) * 1000;
                const burnStart = burn.burnMs;
                const burnEnd   = burnStart + burnDur;
                const coolEnd   = burnEnd + COOLDOWN_SECONDS * 1000;

                const burnLeft   = Math.max(0, t2pct(burnStart));
                const burnWidth  = Math.max(0.5, t2pct(burnEnd) - burnLeft);
                const coolLeft   = Math.max(0, t2pct(burnEnd));
                const coolWidth  = Math.max(0, Math.min(t2pct(coolEnd) - coolLeft, 100 - coolLeft));
                const pastOpacity = burn.isPast ? 0.4 : 1;

                const hasConflict = burn.blackout_overlap || burn.cooldown_conflict;

                return (
                  <React.Fragment key={i}>
                    <div
                      className={`gantt-block gantt-block--${burn.type}`}
                      style={{
                        left: `${burnLeft}%`, width: `${Math.max(burnWidth, 1.5)}%`,
                        opacity: pastOpacity,
                        outline: hasConflict ? '1px solid var(--red)' : 'none',
                      }}
                      title={`${burn.burn_id} @ ${new Date(burnStart).toISOString()} | ΔV: ${burn.dv_magnitude_ms?.toFixed(2)} m/s`}
                    >
                      {burnWidth > 4 ? (burn.type === 'evasion' ? 'EVD' : 'REC') : ''}
                    </div>
                    {coolWidth > 0 && (
                      <div className="gantt-block gantt-block--cooldown"
                        style={{ left: `${coolLeft}%`, width: `${coolWidth}%`, opacity: pastOpacity * 0.6 }}
                        title={`Cooldown: ${COOLDOWN_SECONDS}s`}
                      />
                    )}
                    {hasConflict && (
                      <div style={{
                        position: 'absolute', left: `${burnLeft}%`,
                        top: 0, bottom: 0, width: `${Math.max(burnWidth, 1.5)}%`,
                        background: 'repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(255,59,59,0.3) 3px, rgba(255,59,59,0.3) 6px)',
                        pointerEvents: 'none',
                      }} />
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div style={{
        display: 'flex', gap: 12, marginTop: 5, marginLeft: 84,
        fontFamily: 'var(--font-mono)', fontSize: 7, color: 'var(--text-dim)',
      }}>
        {[
          { color: 'var(--red)',   label: 'Evasion' },
          { color: 'var(--cyan)',  label: 'Recovery' },
          { color: 'var(--surface-hover)', label: 'Cooldown', border: true },
        ].map(({ color, label, border }) => (
          <span key={label}>
            <span style={{
              display: 'inline-block', width: 8, height: 8,
              background: color, borderRadius: 1, marginRight: 4,
              verticalAlign: 'middle',
              border: border ? '1px solid var(--border)' : 'none',
            }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
