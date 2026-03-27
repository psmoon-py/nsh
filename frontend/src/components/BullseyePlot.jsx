import React, { useMemo } from 'react';

/**
 * Conjunction "Bullseye" Polar Plot.
 * 
 * Center = selected satellite.
 * Radial distance = Time to Closest Approach (TCA) — inner ring = sooner.
 * Angle = derived from debris ID hash (pseudo-approach vector).
 * Color = risk level.
 */

const RISK_COLORS = {
  CRITICAL: '#ff3d4a',
  RED: '#ff3d4a',
  YELLOW: '#ffab00',
  GREEN: '#00e676',
};

const RING_RADII = [0.25, 0.5, 0.75, 1.0]; // Normalized
const RING_LABELS = ['6h', '12h', '18h', '24h'];

function hashToAngle(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  return (hash % 360) * (Math.PI / 180);
}

export default function BullseyePlot({ cdmWarnings = [], selectedSat }) {
  const relevantWarnings = useMemo(() => {
    if (!selectedSat) return cdmWarnings.slice(0, 30);
    return cdmWarnings.filter((c) => c.sat_id === selectedSat);
  }, [cdmWarnings, selectedSat]);

  const size = 220;
  const cx = size / 2;
  const cy = size / 2;
  const maxR = size / 2 - 20;

  const points = useMemo(() => {
    return relevantWarnings.map((cdm) => {
      // TCA 0–86400s → normalized 0–1 (0 = center = imminent)
      const tcaNorm = Math.min(cdm.tca_seconds / 86400, 1.0);
      const r = tcaNorm * maxR;
      const angle = hashToAngle(cdm.deb_id);
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      return { ...cdm, x, y, r: Math.max(3, 7 - tcaNorm * 5) };
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
        <circle cx={cx} cy={cy} r={maxR} fill="rgba(15, 21, 32, 0.8)" />

        {/* Concentric rings */}
        {RING_RADII.map((rn, i) => (
          <g key={i}>
            <circle
              cx={cx}
              cy={cy}
              r={rn * maxR}
              fill="none"
              stroke="#1e2a3e"
              strokeWidth={0.5}
              strokeDasharray="3 3"
            />
            <text
              x={cx + rn * maxR + 3}
              y={cy - 3}
              fill="#4a5a72"
              fontSize={7}
              fontFamily="'IBM Plex Mono', monospace"
            >
              {RING_LABELS[i]}
            </text>
          </g>
        ))}

        {/* Cross hairs */}
        <line x1={cx - maxR} y1={cy} x2={cx + maxR} y2={cy} stroke="#1e2a3e" strokeWidth={0.3} />
        <line x1={cx} y1={cy - maxR} x2={cx} y2={cy + maxR} stroke="#1e2a3e" strokeWidth={0.3} />

        {/* Debris dots */}
        {points.map((pt, i) => (
          <g key={i}>
            {/* Glow */}
            {pt.risk_level === 'CRITICAL' && (
              <circle
                cx={pt.x}
                cy={pt.y}
                r={pt.r + 4}
                fill={RISK_COLORS[pt.risk_level]}
                opacity={0.15}
              >
                <animate attributeName="r" values={`${pt.r + 2};${pt.r + 6};${pt.r + 2}`} dur="1.5s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.15;0.05;0.15" dur="1.5s" repeatCount="indefinite" />
              </circle>
            )}
            <circle
              cx={pt.x}
              cy={pt.y}
              r={pt.r}
              fill={RISK_COLORS[pt.risk_level] || '#4a5a72'}
              opacity={0.85}
            />
          </g>
        ))}

        {/* Center satellite marker */}
        <circle cx={cx} cy={cy} r={4} fill="#00e5ff" />
        <circle cx={cx} cy={cy} r={7} fill="none" stroke="#00e5ff" strokeWidth={0.8} opacity={0.5} />

        {/* Legend */}
        <g transform={`translate(8, ${size - 30})`}>
          {[
            { label: 'Critical', color: RISK_COLORS.CRITICAL },
            { label: 'Warning', color: RISK_COLORS.YELLOW },
            { label: 'Safe', color: RISK_COLORS.GREEN },
          ].map((item, i) => (
            <g key={i} transform={`translate(${i * 55}, 0)`}>
              <circle cx={4} cy={4} r={3} fill={item.color} />
              <text x={11} y={7} fill="#7a8ba5" fontSize={7} fontFamily="'IBM Plex Mono', monospace">
                {item.label}
              </text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}
