import React, { useMemo } from 'react';

/**
 * Conjunction "Bullseye" Polar Plot.
 *
 * Center = selected satellite (or all satellites if none selected).
 * Radial distance = TCA (inner = imminent, outer = 24h).
 * Angle = real RTN-frame approach angle from backend (approach_angle_deg),
 *         NOT a hash — matches PS requirement for relative approach vector.
 * Color = risk level per PS thresholds.
 */

const RISK_COLORS = {
  CRITICAL: '#ff3b3b',
  RED:      '#ff3b3b',
  YELLOW:   '#ffab00',
  GREEN:    '#00e676',
};

const RING_LABELS = ['6h', '12h', '18h', '24h'];

export default function BullseyePlot({ cdmWarnings = [], selectedSat }) {
  const relevantWarnings = useMemo(() => {
    if (!selectedSat) return cdmWarnings.slice(0, 30);
    return cdmWarnings.filter((c) => c.sat_id === selectedSat);
  }, [cdmWarnings, selectedSat]);

  const size  = 220;
  const cx    = size / 2;
  const cy    = size / 2;
  const maxR  = size / 2 - 22;

  const points = useMemo(() => {
    return relevantWarnings.map((cdm) => {
      const tcaNorm = Math.min(cdm.tca_seconds / 86400, 1.0);
      const r       = tcaNorm * maxR;
      // Use real approach angle from backend (RTN frame T-N plane angle)
      const angleDeg = cdm.approach_angle_deg || 0;
      const angleRad = (angleDeg * Math.PI) / 180;
      const x = cx + r * Math.cos(angleRad);
      const y = cy + r * Math.sin(angleRad);
      return { ...cdm, x, y, dotR: Math.max(3, 7 - tcaNorm * 4.5) };
    });
  }, [relevantWarnings, cx, cy, maxR]);

  if (relevantWarnings.length === 0) {
    return (
      <div className="bullseye-container">
        <div className="empty-state" style={{ height: size }}>
          <div className="empty-state__icon">◎</div>
          <div className="empty-state__text">
            {selectedSat ? 'No conjunctions for this satellite' : 'Select a satellite to view proximity'}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bullseye-container">
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: '100%', maxHeight: 200 }}>
        {/* Background */}
        <circle cx={cx} cy={cy} r={maxR} fill="rgba(13,18,32,0.9)" />

        {/* Concentric time rings */}
        {[0.25, 0.5, 0.75, 1.0].map((rn, i) => (
          <g key={i}>
            <circle cx={cx} cy={cy} r={rn * maxR}
              fill="none" stroke="#1e2a3e" strokeWidth={0.5} strokeDasharray="3 4" />
            <text x={cx + rn * maxR + 3} y={cy - 3}
              fill="#3a4a62" fontSize={7} fontFamily="'JetBrains Mono', monospace">
              {RING_LABELS[i]}
            </text>
          </g>
        ))}

        {/* Cross hairs */}
        <line x1={cx - maxR} y1={cy} x2={cx + maxR} y2={cy} stroke="#1e2a3e" strokeWidth={0.4} />
        <line x1={cx} y1={cy - maxR} x2={cx} y2={cy + maxR} stroke="#1e2a3e" strokeWidth={0.4} />

        {/* Debris dots */}
        {points.map((pt, i) => (
          <g key={i}>
            {/* Glow halo for CRITICAL */}
            {(pt.risk_level === 'CRITICAL') && (
              <circle cx={pt.x} cy={pt.y} r={pt.dotR + 5}
                fill={RISK_COLORS.CRITICAL} opacity={0.15}>
                <animate attributeName="r"
                  values={`${pt.dotR+3};${pt.dotR+7};${pt.dotR+3}`}
                  dur="1.4s" repeatCount="indefinite" />
                <animate attributeName="opacity"
                  values="0.15;0.04;0.15"
                  dur="1.4s" repeatCount="indefinite" />
              </circle>
            )}
            <circle cx={pt.x} cy={pt.y} r={pt.dotR}
              fill={RISK_COLORS[pt.risk_level] || '#4a5a72'} opacity={0.9} />
            {/* Tooltip on hover (title element) */}
            <title>
              {pt.deb_id} · miss {pt.miss_distance_km?.toFixed(3)} km ·
              TCA {Math.round(pt.tca_seconds)}s ·
              {pt.relative_speed_kms?.toFixed(2)} km/s
            </title>
          </g>
        ))}

        {/* Centre satellite marker */}
        <circle cx={cx} cy={cy} r={5} fill="#00e5ff" />
        <circle cx={cx} cy={cy} r={9} fill="none" stroke="#00e5ff" strokeWidth={0.8} opacity={0.45} />

        {/* Approach angle reference arc label */}
        <text x={cx + maxR - 12} y={cy - maxR + 12}
          fill="#3a4a62" fontSize={6} fontFamily="'JetBrains Mono', monospace">
          T+
        </text>

        {/* Legend */}
        <g transform={`translate(8, ${size - 30})`}>
          {[
            { label: 'Critical', color: RISK_COLORS.CRITICAL },
            { label: 'Warning',  color: RISK_COLORS.YELLOW },
            { label: 'Safe',     color: RISK_COLORS.GREEN },
          ].map((item, i) => (
            <g key={i} transform={`translate(${i * 56}, 0)`}>
              <circle cx={4} cy={4} r={3} fill={item.color} />
              <text x={11} y={7} fill="#7a8ba5" fontSize={7}
                fontFamily="'JetBrains Mono', monospace">
                {item.label}
              </text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}
