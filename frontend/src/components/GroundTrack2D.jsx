import React, { useMemo } from 'react';

/**
 * 2D Ground Track Map (Mercator Projection)
 *
 * PS Requirements:
 *  ✅ Real-time location markers for the entire active constellation
 *  ✅ Historical trailing path (last 90 min, solid line)
 *  ✅ Dashed predicted trajectory (next 90 min)
 *  ✅ Terminator line (day/night boundary) with shadow overlay
 */

const MAP_W = 800;
const MAP_H = 400;

// Ground stations from PS spec
const GROUND_STATIONS = [
  { id: 'GS-001', name: 'ISTRAC',      lat: 13.0333,  lon: 77.5167  },
  { id: 'GS-002', name: 'Svalbard',    lat: 78.2297,  lon: 15.4077  },
  { id: 'GS-003', name: 'Goldstone',   lat: 35.4266,  lon: -116.89  },
  { id: 'GS-004', name: 'Pta Arenas',  lat: -53.15,   lon: -70.9167 },
  { id: 'GS-005', name: 'IIT Delhi',   lat: 28.545,   lon: 77.1926  },
  { id: 'GS-006', name: 'McMurdo',     lat: -77.8463, lon: 166.6682 },
];

/** Mercator projection: lat/lon → SVG x/y */
function latLonToXY(lat, lon) {
  const x = ((lon + 180) / 360) * MAP_W;
  const y = ((90 - lat) / 180) * MAP_H;
  return [x, y];
}

/**
 * Compute terminator line points (day/night boundary).
 * Based on solar declination and subsolar longitude.
 */
function computeTerminator(timestamp) {
  const d = new Date(timestamp);
  const dayOfYear = Math.floor(
    (d - new Date(d.getFullYear(), 0, 0)) / (1000 * 60 * 60 * 24)
  );

  // Solar declination (approximate)
  const declDeg = -23.44 * Math.cos((2 * Math.PI / 365) * (dayOfYear + 10));
  const declRad = (declDeg * Math.PI) / 180;

  // Subsolar longitude
  const hours = d.getUTCHours() + d.getUTCMinutes() / 60 + d.getUTCSeconds() / 3600;
  const subsolarLon = (12 - hours) * 15;

  const terminatorPoints = [];
  for (let lon = -180; lon <= 180; lon += 2) {
    const lonRad = ((lon - subsolarLon) * Math.PI) / 180;
    const latRad = Math.atan(-Math.cos(lonRad) / Math.tan(declRad));
    const lat = (latRad * 180) / Math.PI;
    const [x, y] = latLonToXY(Math.max(-89, Math.min(89, lat)), lon);
    terminatorPoints.push([x, y]);
  }
  return terminatorPoints;
}

/**
 * Generate approximate ground track from current lat/lon.
 * For proper 90-min trails the backend would need historical data.
 * This approximates based on orbital mechanics constants.
 */
function generateTrail(lat, lon, minutes, isForward = false) {
  const orbitalPeriod = 95.5; // ~95.5 min for 550 km orbit
  const inclination   = 53.0; // Walker Delta constellation inclination
  // Earth rotates ~360°/1436 min relative to ECI
  const earthRotRate  = 360 / 1436;
  const lonPerMin     = 360 / orbitalPeriod; // ground track speed

  const points = [];
  for (let t = 0; t <= minutes; t += 2) {
    const sign       = isForward ? 1 : -1;
    const meanAnomaly = (sign * t * 360) / orbitalPeriod;
    const trailLat   = inclination * Math.sin(
      (meanAnomaly * Math.PI) / 180 + Math.asin(lat / inclination) || 0
    );
    let trailLon = lon + sign * t * (lonPerMin - earthRotRate);

    // Wrap longitude
    while (trailLon > 180)  trailLon -= 360;
    while (trailLon < -180) trailLon += 360;

    const clampedLat = Math.max(-85, Math.min(85, trailLat));
    points.push(latLonToXY(clampedLat, trailLon));
  }
  return points;
}

/**
 * Segment a polyline at antimeridian crossings (longitude jump > 180°).
 * Without this, ground tracks draw ugly horizontal lines across the map.
 */
function segmentPolyline(points) {
  const segments = [[]];
  for (let i = 0; i < points.length; i++) {
    if (i > 0) {
      const dx = Math.abs(points[i][0] - points[i-1][0]);
      if (dx > MAP_W * 0.4) {
        segments.push([]); // antimeridian crossing — start new segment
      }
    }
    segments[segments.length - 1].push(points[i]);
  }
  return segments.filter(s => s.length > 1);
}

export default function GroundTrack2D({
  satellites = [],
  debrisCloud = [],
  timestamp,
  selectedSat,
  onSelectSat,
}) {
  const terminatorPoints = useMemo(() => {
    if (!timestamp || timestamp === '—') return [];
    return computeTerminator(timestamp);
  }, [timestamp]);

  // Build night-side polygon: terminator + map borders
  const nightPolygonPoints = useMemo(() => {
    if (terminatorPoints.length === 0) return '';
    const pts = terminatorPoints.map(([x, y]) => `${x},${y}`).join(' ');
    return `${pts} ${MAP_W},${MAP_H} 0,${MAP_H}`;
  }, [terminatorPoints]);

  // Terminator polyline segments (respects antimeridian)
  const terminatorSegs = useMemo(() => {
    return segmentPolyline(terminatorPoints);
  }, [terminatorPoints]);

  return (
    <div style={{ width: '100%', position: 'relative' }}>
      <svg
        viewBox={`0 0 ${MAP_W} ${MAP_H}`}
        style={{
          width: '100%',
          height: 'auto',
          borderRadius: 4,
          display: 'block',
          background: '#060d1e', // deep ocean color fallback
        }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          {/* Clip to map bounds */}
          <clipPath id="mapClip">
            <rect x={0} y={0} width={MAP_W} height={MAP_H} />
          </clipPath>
        </defs>

        {/* ── Earth texture background (daymap) ── */}
        <image
          href="/textures/earth_daymap.jpg"
          x={0} y={0}
          width={MAP_W} height={MAP_H}
          preserveAspectRatio="none"
          opacity={0.55}
          clipPath="url(#mapClip)"
        />

        {/* ── Dark ocean overlay ── */}
        <rect x={0} y={0} width={MAP_W} height={MAP_H}
          fill="rgba(4, 10, 24, 0.45)" />

        {/* ── Graticule (grid lines) ── */}
        {[-60, -30, 0, 30, 60].map((lat) => {
          const [, y] = latLonToXY(lat, 0);
          return (
            <line key={`lat-${lat}`}
              x1={0} y1={y} x2={MAP_W} y2={y}
              stroke="rgba(255,255,255,0.08)" strokeWidth={0.5}
              strokeDasharray="4 6"
            />
          );
        })}
        {[-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150].map((lon) => {
          const [x] = latLonToXY(0, lon);
          return (
            <line key={`lon-${lon}`}
              x1={x} y1={0} x2={x} y2={MAP_H}
              stroke="rgba(255,255,255,0.08)" strokeWidth={0.5}
              strokeDasharray="4 6"
            />
          );
        })}

        {/* ── Equator ── */}
        {(() => {
          const [, y] = latLonToXY(0, 0);
          return (
            <line x1={0} y1={y} x2={MAP_W} y2={y}
              stroke="rgba(255,255,255,0.18)" strokeWidth={0.8}
            />
          );
        })()}

        {/* ── Night side shadow (terminator) ── */}
        {nightPolygonPoints && (
          <polygon
            points={nightPolygonPoints}
            fill="rgba(0, 0, 20, 0.55)"
            clipPath="url(#mapClip)"
          />
        )}

        {/* ── Terminator line ── */}
        {terminatorSegs.map((seg, i) => (
          <polyline
            key={i}
            points={seg.map(([x, y]) => `${x},${y}`).join(' ')}
            fill="none"
            stroke="rgba(255, 200, 100, 0.6)"
            strokeWidth={1}
            strokeDasharray="6 4"
          />
        ))}

        {/* ── Terminator label ── */}
        {terminatorPoints.length > 0 && (
          <text x={MAP_W - 6} y={12} fill="rgba(255,200,100,0.5)"
            fontSize={7} fontFamily="'JetBrains Mono', monospace"
            textAnchor="end">
            ☀ Terminator
          </text>
        )}

        {/* ── Debris dots (first 3000, very faint) ── */}
        {debrisCloud.slice(0, 3000).map((d, i) => {
          const [, lat, lon] = d;
          if (lat == null || lon == null) return null;
          const [dx, dy] = latLonToXY(lat, lon);
          return (
            <circle key={i} cx={dx} cy={dy} r={0.7}
              fill="#ff4444" opacity={0.18} />
          );
        })}

        {/* ── Ground stations ── */}
        {GROUND_STATIONS.map((gs) => {
          const [x, y] = latLonToXY(gs.lat, gs.lon);
          return (
            <g key={gs.id}>
              {/* Diamond marker */}
              <rect
                x={x - 3.5} y={y - 3.5}
                width={7} height={7}
                fill="#ffab00"
                transform={`rotate(45 ${x} ${y})`}
                opacity={0.9}
              />
              {/* Coverage ring */}
              <circle cx={x} cy={y} r={12}
                fill="none" stroke="#ffab00"
                strokeWidth={0.5} opacity={0.2}
                strokeDasharray="2 3"
              />
              <text x={x + 7} y={y + 3}
                fill="#ffab00" fontSize={6.5} opacity={0.8}
                fontFamily="'JetBrains Mono', monospace">
                {gs.name}
              </text>
            </g>
          );
        })}

        {/* ── Satellite trails and markers ── */}
        {satellites.map((sat) => {
          if (sat.lat == null || sat.lon == null) return null;
          const [sx, sy] = latLonToXY(sat.lat, sat.lon);
          const isSelected = sat.id === selectedSat;
          const isNominal  = sat.status === 'NOMINAL';
          const color = isSelected ? '#00e5ff' : isNominal ? '#00e676' : '#ffab00';

          return (
            <g key={sat.id}
              onClick={() => onSelectSat(sat.id)}
              style={{ cursor: 'pointer' }}
            >
              {/* Historical trail (90 min, solid, only for selected) */}
              {isSelected && (() => {
                const trail = generateTrail(sat.lat, sat.lon, 90, false);
                const segs  = segmentPolyline(trail);
                return segs.map((seg, i) => (
                  <polyline key={`hist-${i}`}
                    points={seg.map(([x, y]) => `${x},${y}`).join(' ')}
                    fill="none" stroke={color}
                    strokeWidth={0.8} opacity={0.35}
                  />
                ));
              })()}

              {/* Predicted trajectory (90 min, dashed, only for selected) */}
              {isSelected && (() => {
                const trail = generateTrail(sat.lat, sat.lon, 90, true);
                const segs  = segmentPolyline(trail);
                return segs.map((seg, i) => (
                  <polyline key={`pred-${i}`}
                    points={seg.map(([x, y]) => `${x},${y}`).join(' ')}
                    fill="none" stroke={color}
                    strokeWidth={0.8} strokeDasharray="5 4" opacity={0.25}
                  />
                ));
              })()}

              {/* Satellite dot */}
              <circle cx={sx} cy={sy} r={isSelected ? 4.5 : 2.5}
                fill={color} opacity={0.92}
              />

              {/* Selection ring */}
              {isSelected && (
                <>
                  <circle cx={sx} cy={sy} r={8}
                    fill="none" stroke={color}
                    strokeWidth={0.7} opacity={0.5}
                  />
                  <text x={sx + 9} y={sy + 3}
                    fill={color} fontSize={7.5}
                    fontFamily="'JetBrains Mono', monospace"
                    fontWeight="600">
                    {sat.id}
                  </text>
                  <text x={sx + 9} y={sy + 12}
                    fill={color} fontSize={6}
                    fontFamily="'JetBrains Mono', monospace" opacity={0.7}>
                    {sat.fuel_kg?.toFixed(1)} kg · {sat.alt?.toFixed(0) || '550'} km
                  </text>
                </>
              )}
            </g>
          );
        })}

        {/* ── Axis labels ── */}
        <text x={3} y={MAP_H / 2 + 4}
          fill="rgba(255,255,255,0.2)" fontSize={7}
          fontFamily="'JetBrains Mono', monospace"
          transform={`rotate(-90 3 ${MAP_H / 2})`}>
          Latitude
        </text>
        <text x={MAP_W / 2} y={MAP_H - 3}
          fill="rgba(255,255,255,0.2)" fontSize={7}
          fontFamily="'JetBrains Mono', monospace" textAnchor="middle">
          Longitude
        </text>

        {/* ── Lat/lon graticule labels ── */}
        {[-60, -30, 30, 60].map((lat) => {
          const [, y] = latLonToXY(lat, 0);
          return (
            <text key={`llabel-${lat}`} x={3} y={y - 2}
              fill="rgba(255,255,255,0.25)" fontSize={6}
              fontFamily="'JetBrains Mono', monospace">
              {lat > 0 ? `+${lat}°` : `${lat}°`}
            </text>
          );
        })}

        {/* ── Legend ── */}
        <g transform={`translate(8, 8)`}>
          <rect x={0} y={0} width={80} height={36}
            fill="rgba(6,10,20,0.75)" rx={3}
            stroke="rgba(0,229,255,0.15)" strokeWidth={0.5}
          />
          {[
            { color: '#00e676', label: 'Nominal' },
            { color: '#ffab00', label: 'Off-slot' },
            { color: '#00e5ff', label: 'Selected' },
          ].map((item, i) => (
            <g key={i} transform={`translate(6, ${6 + i * 10})`}>
              <circle cx={3} cy={3} r={3} fill={item.color} />
              <text x={10} y={6}
                fill="rgba(255,255,255,0.6)" fontSize={6.5}
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
