import React, { useMemo } from 'react';

/**
 * 2D Ground Track Map (Mercator Projection)
 * 
 * PS Requirements:
 * - Real-time location markers for the entire active constellation
 * - Historical trailing path representing the last 90 minutes of orbit
 * - Dashed predicted trajectory line for the next 90 minutes
 * - Dynamic shadow overlay representing the "Terminator Line"
 */

const MAP_W = 800;
const MAP_H = 400;
const RE = 6378.137;

// Ground stations from PS
const GROUND_STATIONS = [
  { id: 'GS-001', name: 'ISTRAC', lat: 13.0333, lon: 77.5167 },
  { id: 'GS-002', name: 'Svalbard', lat: 78.2297, lon: 15.4077 },
  { id: 'GS-003', name: 'Goldstone', lat: 35.4266, lon: -116.89 },
  { id: 'GS-004', name: 'Punta Arenas', lat: -53.15, lon: -70.9167 },
  { id: 'GS-005', name: 'IIT Delhi', lat: 28.545, lon: 77.1926 },
  { id: 'GS-006', name: 'McMurdo', lat: -77.8463, lon: 166.6682 },
];

/**
 * Mercator projection: lat/lon → SVG x/y
 */
function latLonToXY(lat, lon) {
  const x = ((lon + 180) / 360) * MAP_W;
  const y = ((90 - lat) / 180) * MAP_H;
  return [x, y];
}

/**
 * Compute approximate terminator line (day/night boundary).
 * Uses solar declination and hour angle at the given timestamp.
 */
function computeTerminator(timestamp) {
  const d = new Date(timestamp);
  const dayOfYear = Math.floor(
    (d - new Date(d.getFullYear(), 0, 0)) / (1000 * 60 * 60 * 24)
  );
  
  // Solar declination (approximate)
  const declination = -23.44 * Math.cos((2 * Math.PI / 365) * (dayOfYear + 10));
  const declRad = (declination * Math.PI) / 180;
  
  // Subsolar longitude (based on time of day)
  const hours = d.getUTCHours() + d.getUTCMinutes() / 60 + d.getUTCSeconds() / 3600;
  const subsolarLon = (12 - hours) * 15; // 15°/hour
  
  // Generate terminator points
  const points = [];
  for (let lon = -180; lon <= 180; lon += 2) {
    const lonRad = ((lon - subsolarLon) * Math.PI) / 180;
    const latRad = Math.atan(-Math.cos(lonRad) / Math.tan(declRad));
    const lat = (latRad * 180) / Math.PI;
    const [x, y] = latLonToXY(lat, lon);
    points.push(`${x},${y}`);
  }
  
  return points.join(' ');
}

/**
 * Generate a simple ground track trail from a satellite's current position.
 * Approximates the orbital path by shifting in longitude over time.
 * For a more accurate trail, the backend would need to provide historical positions.
 */
function generateTrail(lat, lon, minutes, isForward = false) {
  const points = [];
  const orbitalPeriod = 90; // ~90 min for LEO
  const lonShiftPerMin = 360 / orbitalPeriod; // degrees longitude per minute (ground track)
  const incl = 53; // approximate inclination in degrees
  
  for (let t = 0; t <= minutes; t += 2) {
    const tFrac = t / orbitalPeriod;
    const sign = isForward ? 1 : -1;
    
    // Approximate sinusoidal ground track
    const meanAnomaly = (sign * t * 360) / orbitalPeriod;
    const trailLat = incl * Math.sin((meanAnomaly * Math.PI) / 180 + (lat * Math.PI) / 180);
    let trailLon = lon + sign * t * (360 / orbitalPeriod) * (1 - 1/15.58); // account for Earth rotation
    
    // Wrap longitude
    while (trailLon > 180) trailLon -= 360;
    while (trailLon < -180) trailLon += 360;
    
    const clampedLat = Math.max(-85, Math.min(85, trailLat));
    points.push(latLonToXY(clampedLat, trailLon));
  }
  
  return points;
}

export default function GroundTrack2D({
  satellites = [],
  debrisCloud = [],
  timestamp,
  selectedSat,
  onSelectSat,
}) {
  // Terminator line points
  const terminatorPoints = useMemo(() => {
    if (!timestamp || timestamp === '—') return '';
    return computeTerminator(timestamp);
  }, [timestamp]);

  // Build night-side polygon (from terminator down to bottom of map)
  const nightPolygon = useMemo(() => {
    if (!terminatorPoints) return '';
    // Close the polygon: terminator line + bottom of map
    return `${terminatorPoints} ${MAP_W},${MAP_H} 0,${MAP_H}`;
  }, [terminatorPoints]);

  return (
    <div className="groundtrack-container" style={{ width: '100%', position: 'relative' }}>
      <svg
        viewBox={`0 0 ${MAP_W} ${MAP_H}`}
        style={{ width: '100%', height: 'auto', background: '#0a1628', borderRadius: 4 }}
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Grid lines (graticule) */}
        {[-60, -30, 0, 30, 60].map((lat) => {
          const [, y] = latLonToXY(lat, 0);
          return (
            <line key={`lat-${lat}`}
              x1={0} y1={y} x2={MAP_W} y2={y}
              stroke="#1a2a40" strokeWidth={0.5} strokeDasharray="4 4"
            />
          );
        })}
        {[-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150].map((lon) => {
          const [x] = latLonToXY(0, lon);
          return (
            <line key={`lon-${lon}`}
              x1={x} y1={0} x2={x} y2={MAP_H}
              stroke="#1a2a40" strokeWidth={0.5} strokeDasharray="4 4"
            />
          );
        })}

        {/* Coastline approximation (simple rectangle outlines for continents) */}
        <rect x={latLonToXY(0, -130)[0]} y={latLonToXY(70, 0)[1]}
          width={latLonToXY(0, -60)[0] - latLonToXY(0, -130)[0]}
          height={latLonToXY(-55, 0)[1] - latLonToXY(70, 0)[1]}
          fill="none" stroke="#1e3a55" strokeWidth={0.8} rx={2}
        />
        <rect x={latLonToXY(0, -10)[0]} y={latLonToXY(60, 0)[1]}
          width={latLonToXY(0, 40)[0] - latLonToXY(0, -10)[0]}
          height={latLonToXY(35, 0)[1] - latLonToXY(60, 0)[1]}
          fill="none" stroke="#1e3a55" strokeWidth={0.8} rx={2}
        />
        <rect x={latLonToXY(0, -20)[0]} y={latLonToXY(35, 0)[1]}
          width={latLonToXY(0, 50)[0] - latLonToXY(0, -20)[0]}
          height={latLonToXY(-35, 0)[1] - latLonToXY(35, 0)[1]}
          fill="none" stroke="#1e3a55" strokeWidth={0.8} rx={2}
        />
        <rect x={latLonToXY(0, 60)[0]} y={latLonToXY(55, 0)[1]}
          width={latLonToXY(0, 150)[0] - latLonToXY(0, 60)[0]}
          height={latLonToXY(5, 0)[1] - latLonToXY(55, 0)[1]}
          fill="none" stroke="#1e3a55" strokeWidth={0.8} rx={2}
        />
        <rect x={latLonToXY(0, 110)[0]} y={latLonToXY(-10, 0)[1]}
          width={latLonToXY(0, 155)[0] - latLonToXY(0, 110)[0]}
          height={latLonToXY(-45, 0)[1] - latLonToXY(-10, 0)[1]}
          fill="none" stroke="#1e3a55" strokeWidth={0.8} rx={2}
        />

        {/* Terminator line (day/night boundary) */}
        {nightPolygon && (
          <polygon
            points={nightPolygon}
            fill="rgba(0, 0, 20, 0.4)"
            stroke="#334466"
            strokeWidth={1}
            strokeDasharray="6 3"
          />
        )}

        {/* Terminator label */}
        {terminatorPoints && (
          <text x={MAP_W - 80} y={15} fill="#334466" fontSize={8}
            fontFamily="'IBM Plex Mono', monospace">
            Terminator
          </text>
        )}

        {/* Ground stations */}
        {GROUND_STATIONS.map((gs) => {
          const [x, y] = latLonToXY(gs.lat, gs.lon);
          return (
            <g key={gs.id}>
              <rect x={x - 3} y={y - 3} width={6} height={6}
                fill="#ffab00" transform={`rotate(45 ${x} ${y})`} />
              <text x={x + 6} y={y + 3} fill="#ffab00" fontSize={6}
                fontFamily="'IBM Plex Mono', monospace" opacity={0.7}>
                {gs.name}
              </text>
            </g>
          );
        })}

        {/* Satellite trails and markers */}
        {satellites.map((sat) => {
          if (sat.lat == null || sat.lon == null) return null;
          const [sx, sy] = latLonToXY(sat.lat, sat.lon);
          const isSelected = sat.id === selectedSat;
          const isNominal = sat.status === 'NOMINAL';
          const color = isSelected ? '#00e5ff' : isNominal ? '#00e676' : '#ffab00';

          // Historical trail (90 min, solid)
          const histTrail = generateTrail(sat.lat, sat.lon, 90, false);
          const histPath = histTrail.map(([x, y]) => `${x},${y}`).join(' ');

          // Predicted trail (90 min, dashed)
          const predTrail = generateTrail(sat.lat, sat.lon, 90, true);
          const predPath = predTrail.map(([x, y]) => `${x},${y}`).join(' ');

          return (
            <g key={sat.id} onClick={() => onSelectSat(sat.id)} style={{ cursor: 'pointer' }}>
              {/* Historical trail (solid) */}
              {isSelected && histTrail.length > 1 && (
                <polyline
                  points={histPath}
                  fill="none"
                  stroke={color}
                  strokeWidth={1}
                  opacity={0.3}
                />
              )}

              {/* Predicted trajectory (dashed) */}
              {isSelected && predTrail.length > 1 && (
                <polyline
                  points={predPath}
                  fill="none"
                  stroke={color}
                  strokeWidth={1}
                  strokeDasharray="4 3"
                  opacity={0.25}
                />
              )}

              {/* Satellite marker */}
              <circle cx={sx} cy={sy} r={isSelected ? 4 : 2.5}
                fill={color} opacity={0.9} />

              {/* Selection ring */}
              {isSelected && (
                <circle cx={sx} cy={sy} r={7}
                  fill="none" stroke={color} strokeWidth={0.8} opacity={0.5} />
              )}

              {/* Label for selected */}
              {isSelected && (
                <text x={sx + 8} y={sy + 3} fill={color} fontSize={7}
                  fontFamily="'IBM Plex Mono', monospace">
                  {sat.id}
                </text>
              )}
            </g>
          );
        })}

        {/* Debris (tiny dots, only first 2000 for performance) */}
        {debrisCloud.slice(0, 2000).map((d, i) => {
          const [, lat, lon] = d;
          if (lat == null || lon == null) return null;
          const [dx, dy] = latLonToXY(lat, lon);
          return (
            <circle key={i} cx={dx} cy={dy} r={0.8}
              fill="#ff3d4a" opacity={0.15} />
          );
        })}

        {/* Axis labels */}
        <text x={4} y={MAP_H / 2} fill="#4a5a72" fontSize={7}
          fontFamily="'IBM Plex Mono', monospace" transform={`rotate(-90 4 ${MAP_H / 2})`}>
          Latitude
        </text>
        <text x={MAP_W / 2} y={MAP_H - 4} fill="#4a5a72" fontSize={7}
          fontFamily="'IBM Plex Mono', monospace" textAnchor="middle">
          Longitude
        </text>

        {/* Equator label */}
        <text x={MAP_W - 40} y={latLonToXY(0, 0)[1] - 3} fill="#1a2a40" fontSize={6}
          fontFamily="'IBM Plex Mono', monospace">
          Equator
        </text>
      </svg>
    </div>
  );
}
