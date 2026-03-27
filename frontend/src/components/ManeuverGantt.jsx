import React, { useMemo } from 'react';

const COOLDOWN_SECONDS = 600; // 10 minutes
const WINDOW_HOURS = 2;       // Display window: ±2 hours from now

/**
 * Maneuver Timeline (Gantt-style scheduler).
 * Shows burn start/end blocks and mandatory 600-second cooldowns.
 */
export default function ManeuverGantt({ maneuvers = [], satellites = [], timestamp }) {
  const now = timestamp ? new Date(timestamp).getTime() : Date.now();
  const windowStart = now - WINDOW_HOURS * 3600 * 1000;
  const windowEnd = now + WINDOW_HOURS * 3600 * 1000;
  const windowDuration = windowEnd - windowStart;

  // Group maneuvers by satellite
  const tracks = useMemo(() => {
    const groups = {};

    maneuvers.forEach((m) => {
      if (!groups[m.sat_id]) groups[m.sat_id] = [];
      const burnTime = new Date(m.burn_time).getTime();
      groups[m.sat_id].push({
        ...m,
        burnMs: burnTime,
        type: m.burn_id?.includes('RECOV') ? 'recovery' : 'evasion',
      });
    });

    // Create tracks for each satellite (show top 8 with maneuvers)
    return Object.entries(groups)
      .slice(0, 8)
      .map(([satId, burns]) => ({
        satId,
        burns: burns.sort((a, b) => a.burnMs - b.burnMs),
      }));
  }, [maneuvers]);

  const timeToPercent = (ms) => {
    return ((ms - windowStart) / windowDuration) * 100;
  };

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
      {/* Time axis labels */}
      <div style={{ display: 'flex', marginLeft: 84, marginBottom: 4 }}>
        {[-2, -1, 0, 1, 2].map((h) => {
          const pct = ((h + WINDOW_HOURS) / (WINDOW_HOURS * 2)) * 100;
          return (
            <span
              key={h}
              style={{
                position: 'relative',
                left: `${pct}%`,
                transform: 'translateX(-50%)',
                fontSize: 8,
                fontFamily: "var(--font-mono)",
                color: h === 0 ? 'var(--cyan)' : 'var(--text-dim)',
                whiteSpace: 'nowrap',
              }}
            >
              {h === 0 ? 'NOW' : `${h > 0 ? '+' : ''}${h}h`}
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
              <div
                style={{
                  position: 'absolute',
                  left: `${timeToPercent(now)}%`,
                  top: 0,
                  bottom: 0,
                  width: 1,
                  background: 'var(--cyan)',
                  opacity: 0.6,
                  zIndex: 5,
                }}
              />

              {track.burns.map((burn, i) => {
                const burnStart = burn.burnMs;
                const burnEnd = burnStart + 5000; // 5s burn duration (visual)
                const cooldownEnd = burnEnd + COOLDOWN_SECONDS * 1000;

                const burnLeft = Math.max(0, timeToPercent(burnStart));
                const burnWidth = Math.max(0.5, timeToPercent(burnEnd) - burnLeft);
                const coolLeft = Math.max(0, timeToPercent(burnEnd));
                const coolWidth = Math.max(0, Math.min(
                  timeToPercent(cooldownEnd) - coolLeft,
                  100 - coolLeft
                ));

                return (
                  <React.Fragment key={i}>
                    {/* Burn block */}
                    <div
                      className={`gantt-block gantt-block--${burn.type}`}
                      style={{ left: `${burnLeft}%`, width: `${Math.max(burnWidth, 1.5)}%` }}
                      title={`${burn.burn_id} @ ${new Date(burnStart).toISOString()}`}
                    >
                      {burnWidth > 4 ? (burn.type === 'evasion' ? 'EVD' : 'REC') : ''}
                    </div>

                    {/* Cooldown block */}
                    {coolWidth > 0 && (
                      <div
                        className="gantt-block gantt-block--cooldown"
                        style={{ left: `${coolLeft}%`, width: `${coolWidth}%` }}
                        title={`Cooldown: ${COOLDOWN_SECONDS}s`}
                      />
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div
        style={{
          display: 'flex',
          gap: 14,
          marginTop: 6,
          marginLeft: 84,
          fontSize: 8,
          fontFamily: "var(--font-mono)",
          color: 'var(--text-dim)',
        }}
      >
        <span>
          <span style={{ display: 'inline-block', width: 8, height: 8, background: 'var(--red)', borderRadius: 2, marginRight: 4, verticalAlign: 'middle' }} />
          Evasion
        </span>
        <span>
          <span style={{ display: 'inline-block', width: 8, height: 8, background: 'var(--cyan)', borderRadius: 2, marginRight: 4, verticalAlign: 'middle' }} />
          Recovery
        </span>
        <span>
          <span style={{ display: 'inline-block', width: 8, height: 8, background: 'var(--surface-hover)', borderRadius: 2, marginRight: 4, verticalAlign: 'middle', border: '1px solid var(--border)' }} />
          Cooldown
        </span>
      </div>
    </div>
  );
}
