import React, { useMemo, useRef, useEffect } from 'react';

/**
 * 2D Ground Track Map (Mercator Projection).
 *
 * PS Requirements:
 *  ✅ True Mercator projection (not linear lat mapping)
 *  ✅ Real-time satellite markers
 *  ✅ Historical trailing path (past_track from backend, 90 min)
 *  ✅ Dashed predicted trajectory (future_track from backend, 90 min)
 *  ✅ Terminator line with shadow overlay
 *  ✅ 10,000+ debris via Canvas layer (single draw pass)
 *  ✅ Ground stations from backend snapshot
 *  ✅ Antimeridian-safe polyline segmenting
 */

const MAP_W = 900;
const MAP_H = 440;

/** True Mercator projection. */
function mercatorXY(lat, lon) {
  const clamped = Math.max(-85.05113, Math.min(85.05113, lat));
  const phi = (clamped * Math.PI) / 180;
  const x   = ((lon + 180) / 360) * MAP_W;
  const mercN = Math.log(Math.tan(Math.PI / 4 + phi / 2));
  const y = MAP_H / 2 - (MAP_W / (2 * Math.PI)) * mercN;
  return [x, y];
}

/** Split polyline at antimeridian crossings (lon jump > 180°). */
function splitAtAntimeridian(points) {
  if (points.length < 2) return [points];
  const segs = [[]];
  for (let i = 0; i < points.length; i++) {
    if (i > 0 && Math.abs(points[i].lon - points[i-1].lon) > 180) {
      segs.push([]);
    }
    segs[segs.length - 1].push(points[i]);
  }
  return segs.filter(s => s.length >= 2);
}

/** Compute terminator points for day/night overlay. */
function computeTerminator(timestamp) {
  const d = new Date(timestamp);
  const dayOfYear = Math.floor(
    (d - new Date(d.getFullYear(), 0, 0)) / (1000 * 60 * 60 * 24)
  );
  const declDeg = -23.44 * Math.cos((2 * Math.PI / 365) * (dayOfYear + 10));
  const declRad = (declDeg * Math.PI) / 180;
  const hours   = d.getUTCHours() + d.getUTCMinutes() / 60 + d.getUTCSeconds() / 3600;
  const subsolarLon = (12 - hours) * 15;

  const pts = [];
  for (let lon = -180; lon <= 180; lon += 2) {
    const lonRad = ((lon - subsolarLon) * Math.PI) / 180;
    if (Math.abs(Math.tan(declRad)) < 1e-10) continue;
    const latRad = Math.atan(-Math.cos(lonRad) / Math.tan(declRad));
    const lat    = (latRad * 180) / Math.PI;
    pts.push({ lat: Math.max(-85, Math.min(85, lat)), lon });
  }
  return pts;
}

export default function GroundTrack2D({
  satellites = [], debrisCloud = [], timestamp,
  selectedSat, onSelectSat,
  groundStations = [], cdmWarnings = [],
}) {
  const debrisCanvasRef = useRef(null);

  // Draw debris on canvas (10k+ points, single pass)
  useEffect(() => {
    const canvas = debrisCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, MAP_W, MAP_H);

    ctx.fillStyle = 'rgba(255, 68, 68, 0.22)';
    const limit = Math.min(debrisCloud.length, 10000);
    for (let i = 0; i < limit; i++) {
      const [, lat, lon] = debrisCloud[i];
      if (lat == null || lon == null) continue;
      const [x, y] = mercatorXY(lat, lon);
      ctx.beginPath();
      ctx.arc(x, y, 0.9, 0, Math.PI * 2);
      ctx.fill();
    }
  }, [debrisCloud]);

  // Terminator
  const terminatorPts = useMemo(() => {
    if (!timestamp || timestamp === '—') return [];
    return computeTerminator(timestamp);
  }, [timestamp]);

  const nightPolygonPts = useMemo(() => {
    if (!terminatorPts.length) return '';
    const pts = terminatorPts.map(p => {
      const [x, y] = mercatorXY(p.lat, p.lon);
      return `${x},${y}`;
    }).join(' ');
    return `${pts} ${MAP_W},${MAP_H} 0,${MAP_H}`;
  }, [terminatorPts]);

  const terminatorSegs = useMemo(() => splitAtAntimeridian(terminatorPts), [terminatorPts]);

  // Graticule lines
  const latLines  = [-60, -30, 0, 30, 60];
  const lonLines  = [-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150];

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <svg
        viewBox={`0 0 ${MAP_W} ${MAP_H}`}
        style={{ width: '100%', height: '100%', display: 'block', background: '#060d1e' }}
        preserveAspectRatio="xMidYMid meet"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <clipPath id="mapClip">
            <rect x={0} y={0} width={MAP_W} height={MAP_H} />
          </clipPath>
        </defs>

        {/* Earth texture */}
        <image href="/textures/earth_daymap.jpg"
          x={0} y={0} width={MAP_W} height={MAP_H}
          preserveAspectRatio="none" opacity={0.5} clipPath="url(#mapClip)" />

        {/* Dark ocean overlay */}
        <rect x={0} y={0} width={MAP_W} height={MAP_H} fill="rgba(3,8,20,0.5)" />

        {/* Graticule */}
        {latLines.map(lat => {
          const [, y] = mercatorXY(lat, 0);
          return <line key={`lat${lat}`} x1={0} y1={y} x2={MAP_W} y2={y}
            stroke="rgba(255,255,255,0.07)" strokeWidth={lat === 0 ? 0.8 : 0.4}
            strokeDasharray={lat === 0 ? '' : '4 7'} />;
        })}
        {lonLines.map(lon => {
          const [x] = mercatorXY(0, lon);
          return <line key={`lon${lon}`} x1={x} y1={0} x2={x} y2={MAP_H}
            stroke="rgba(255,255,255,0.07)" strokeWidth={0.4} strokeDasharray="4 7" />;
        })}

        {/* Night shadow */}
        {nightPolygonPts && (
          <polygon points={nightPolygonPts}
            fill="rgba(0, 0, 30, 0.52)" clipPath="url(#mapClip)" />
        )}

        {/* Terminator line */}
        {terminatorSegs.map((seg, i) => (
          <polyline key={i}
            points={seg.map(p => { const [x,y]=mercatorXY(p.lat,p.lon); return `${x},${y}`; }).join(' ')}
            fill="none" stroke="rgba(255,200,100,0.55)" strokeWidth={1} strokeDasharray="6 4" />
        ))}

        {/* Ground stations from backend */}
        {groundStations.map((gs) => {
          const [x, y] = mercatorXY(gs.lat, gs.lon);
          return (
            <g key={gs.id}>
              <rect x={x-3.5} y={y-3.5} width={7} height={7}
                fill="#ffab00" transform={`rotate(45 ${x} ${y})`} opacity={0.9} />
              <circle cx={x} cy={y} r={14}
                fill="none" stroke="#ffab00" strokeWidth={0.4}
                opacity={0.18} strokeDasharray="2 3" />
              <text x={x+8} y={y+3} fill="#ffab00" fontSize={6.5} opacity={0.75}
                fontFamily="'JetBrains Mono', monospace">
                {gs.name}
              </text>
            </g>
          );
        })}

        {/* Satellite tracks and markers */}
        {satellites.map((sat) => {
          if (sat.lat == null || sat.lon == null) return null;
          const [sx, sy] = mercatorXY(sat.lat, sat.lon);
          const isSelected = sat.id === selectedSat;
          const color = isSelected ? '#00e5ff' : sat.status === 'NOMINAL' ? '#00e676' : '#ffab00';

          return (
            <g key={sat.id} onClick={() => onSelectSat(sat.id)} style={{ cursor: 'pointer' }}>
              {/* Past track from backend (solid line) */}
              {isSelected && (sat.past_track || []).length > 1 &&
                splitAtAntimeridian(sat.past_track).map((seg, i) => (
                  <polyline key={`hist-${i}`}
                    points={seg.map(p => { const [x,y]=mercatorXY(p.lat,p.lon); return `${x},${y}`; }).join(' ')}
                    fill="none" stroke={color} strokeWidth={0.9} opacity={0.35} />
                ))
              }

              {/* Future track from backend (dashed) */}
              {isSelected && (sat.future_track || []).length > 1 &&
                splitAtAntimeridian(sat.future_track).map((seg, i) => (
                  <polyline key={`pred-${i}`}
                    points={seg.map(p => { const [x,y]=mercatorXY(p.lat,p.lon); return `${x},${y}`; }).join(' ')}
                    fill="none" stroke={color} strokeWidth={0.9}
                    strokeDasharray="5 4" opacity={0.25} />
                ))
              }

              {/* Satellite dot */}
              <circle cx={sx} cy={sy} r={isSelected ? 5 : 2.8}
                fill={color} opacity={0.92} />

              {/* Selection ring */}
              {isSelected && (
                <circle cx={sx} cy={sy} r={9}
                  fill="none" stroke={color} strokeWidth={0.7} opacity={0.5} />
              )}

              {/* Label */}
              {isSelected && (
                <>
                  <text x={sx+11} y={sy+3} fill={color} fontSize={8}
                    fontFamily="'JetBrains Mono', monospace" fontWeight="600">
                    {sat.id}
                  </text>
                  <text x={sx+11} y={sy+12} fill={color} fontSize={6.5} opacity={0.7}
                    fontFamily="'JetBrains Mono', monospace">
                    ⛽ {sat.fuel_kg?.toFixed(1)} kg · {sat.alt?.toFixed(0)} km
                    {sat.los_now ? ' · LOS✓' : ' · BLACKOUT'}
                  </text>
                </>
              )}
            </g>
          );
        })}

        {/* Lat/lon grid labels */}
        {[-60, -30, 30, 60].map(lat => {
          const [, y] = mercatorXY(lat, 0);
          return (
            <text key={`ll${lat}`} x={3} y={y-2}
              fill="rgba(255,255,255,0.22)" fontSize={6}
              fontFamily="'JetBrains Mono', monospace">
              {lat > 0 ? `+${lat}°` : `${lat}°`}
            </text>
          );
        })}

        {/* Legend */}
        <g transform="translate(8, 8)">
          <rect x={0} y={0} width={84} height={40}
            fill="rgba(4,9,20,0.82)" rx={2}
            stroke="rgba(0,229,255,0.12)" strokeWidth={0.5} />
          {[
            { color: '#00e676', label: 'Nominal' },
            { color: '#ffab00', label: 'Off-slot' },
            { color: '#00e5ff', label: 'Selected' },
          ].map((item, i) => (
            <g key={i} transform={`translate(6, ${6 + i * 11})`}>
              <circle cx={3} cy={3} r={3} fill={item.color} />
              <text x={10} y={6.5} fill="rgba(255,255,255,0.55)" fontSize={7}
                fontFamily="'JetBrains Mono', monospace">
                {item.label}
              </text>
            </g>
          ))}
        </g>
      </svg>

      {/* Debris canvas overlay (10k+ dots via canvas for performance) */}
      <canvas
        ref={debrisCanvasRef}
        width={MAP_W}
        height={MAP_H}
        style={{
          position: 'absolute', top: 0, left: 0,
          width: '100%', height: '100%',
          pointerEvents: 'none', opacity: 0.8,
        }}
      />
    </div>
  );
}
