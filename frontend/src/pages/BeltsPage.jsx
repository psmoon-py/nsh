import React, { useMemo, useState } from 'react';
import useSnapshot from '../hooks/useSnapshot';
import OrbitalBeltsScene from '../components/OrbitalBeltsScene';

const BAND_INFO = {
  LEO: {
    region: 'Low Earth Orbit',
    typical: 'Operational constellations + dense debris',
    size: '160 km – 2,000 km altitude',
    density: 'Highest traffic and conjunction pressure',
    notes: 'Main challenge regime for the hackathon ACM',
  },
  MEO: {
    region: 'Medium Earth Orbit',
    typical: 'Navigation and relay corridors',
    size: '2,000 km – 35,000 km altitude',
    density: 'Moderate traffic, long-period objects',
    notes: 'Useful for transfer-risk awareness',
  },
  HIGH: {
    region: 'High Altitude / GEO transfer',
    typical: 'Sparse objects with long persistence',
    size: '35,000 km+',
    density: 'Low volume but prolonged residency',
    notes: 'Illustrative strategic shell view',
  },
};

export default function BeltsPage() {
  const { data } = useSnapshot();
  const [band, setBand] = useState('LEO');
  const [camera, setCamera] = useState('Orbit (persp)');
  const satellites = data?.satellites || [];
  const debrisCloud = data?.debris_cloud || [];

  const counts = useMemo(() => {
    let leo = 0, meo = 0, high = 0;
    debrisCloud.forEach((d) => {
      const alt = d[3] || 0;
      if (alt < 2000) leo += 1;
      else if (alt < 35000) meo += 1;
      else high += 1;
    });
    return { leo, meo, high };
  }, [debrisCloud]);

  const info = BAND_INFO[band];

  return (
    <div className="impacts-page belts-page">
      <main className="belts-scene-wrap">
        <OrbitalBeltsScene satellites={satellites} debrisCloud={debrisCloud} selectedBand={band} />
      </main>

      <div className="belts-info-box">
        <div className="live">SELECTION</div>
        <h2>{info.region}</h2>
        <div className="belts-kv">
          <div>Region</div><div>{info.region}</div>
          <div>Typical composition</div><div>{info.typical}</div>
          <div>Typical size</div><div>{info.size}</div>
          <div>Typical density</div><div>{info.density}</div>
          <div>Notes</div><div>{info.notes}</div>
        </div>
      </div>

      <div className="belts-controls">
        <div className="belts-controls__section">
          <h3>View</h3>
          <label>Camera</label>
          <select value={camera} onChange={(e) => setCamera(e.target.value)}>
            <option>Orbit (persp)</option>
            <option>High inclination</option>
            <option>Polar sweep</option>
          </select>
        </div>

        <div className="belts-controls__section">
          <h3>Layers</h3>
          <button className={band === 'LEO' ? 'is-active' : ''} onClick={() => setBand('LEO')}>LEO · {counts.leo}</button>
          <button className={band === 'MEO' ? 'is-active' : ''} onClick={() => setBand('MEO')}>MEO · {counts.meo}</button>
          <button className={band === 'HIGH' ? 'is-active' : ''} onClick={() => setBand('HIGH')}>HIGH · {counts.high}</button>
        </div>

        <div className="belts-controls__section">
          <h3>Fleet</h3>
          <div className="belts-stat">Satellites: <strong>{satellites.length}</strong></div>
          <div className="belts-stat">Debris shown: <strong>{Math.min(debrisCloud.length, 4000)}</strong></div>
        </div>
      </div>

      <a className="impacts-nav-btn" href="/dashboard">GO TO DASHBOARD</a>
    </div>
  );
}
