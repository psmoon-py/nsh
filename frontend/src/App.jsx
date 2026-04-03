import React, { useState, useCallback, useMemo } from 'react';
import useSnapshot, { postSimulateStep } from './hooks/useSnapshot';
import Globe3D from './components/Globe3D';
import GroundTrack2D from './components/GroundTrack2D';
import BullseyePlot from './components/BullseyePlot';
import ManeuverGantt from './components/ManeuverGantt';
import FuelHeatmap from './components/FuelHeatmap';
import SatellitePanel from './components/SatellitePanel';
import CDMList from './components/CDMList';
import './styles/dashboard.css';

const STEP_OPTIONS = [
  { label: '+10s', value: 10 },
  { label: '+1m', value: 60 },
  { label: '+5m', value: 300 },
  { label: '+10m', value: 600 },
  { label: '+1h', value: 3600 },
  { label: '+24h', value: 86400 },
];

export default function App() {
  const { data, loading, error, refresh } = useSnapshot();
  const [selectedSat, setSelectedSat] = useState(null);
  const [simSpeed, setSimSpeed] = useState(86400);
  const [viewMode, setViewMode] = useState('2d');
  const [activeTab, setActiveTab] = useState('ground');
  const [advancing, setAdvancing] = useState(false);

  const handleAdvance = useCallback(async () => {
    if (advancing) return;
    setAdvancing(true);
    try {
      await postSimulateStep(simSpeed);
      await refresh();
    } finally {
      setAdvancing(false);
    }
  }, [simSpeed, refresh, advancing]);

  const satellites = data?.satellites || [];
  const debrisCloud = data?.debris_cloud || [];
  const cdmWarnings = data?.cdm_warnings || [];
  const maneuverQueue = data?.maneuver_queue || [];
  const timestamp = data?.timestamp || '—';
  const groundStations = data?.ground_stations || [];
  const metricsHistory = data?.metrics_history || [];

  const selectedSatData = selectedSat
    ? satellites.find((s) => s.id === selectedSat)
    : null;

  const nominalCount = satellites.filter((s) => s.status === 'NOMINAL').length;
  const criticalCdms = cdmWarnings.filter((c) => c.risk_level === 'CRITICAL').length;
  const totalFuel = satellites.reduce((sum, s) => sum + (s.fuel_kg || 0), 0);
  const totalFuelUsed = Math.max(0, satellites.length * 50 - totalFuel);
  const selectedSatCdms = selectedSat ? cdmWarnings.filter((c) => c.sat_id === selectedSat) : [];

  const leftSat = selectedSatData || satellites[0] || null;

  const resultsSummary = useMemo(() => {
    const src = leftSat;
    if (!src) return null;
    return {
      lat: src.lat,
      lon: src.lon,
      fuel: src.fuel_kg,
      alt: src.alt,
    };
  }, [leftSat]);

  return (
    <div className="sim-shell">
      <div className="sim-brand">• Orbital Insight — Simulator</div>

      <aside className="sim-rail sim-rail--left">
        <section className="sim-card">
          <div className="sim-card__title">Selection</div>
          {leftSat ? (
            <>
              <div className="selection-grid">
                <div className="selection-kv">
                  <span className="selection-kv__label">SATELLITE</span>
                  <span className="selection-kv__value">{leftSat.id}</span>
                </div>
                <div className="selection-kv">
                  <span className="selection-kv__label">STATUS</span>
                  <span className="selection-kv__value">{leftSat.status}</span>
                </div>
                <div className="selection-kv">
                  <span className="selection-kv__label">LOS</span>
                  <span className="selection-kv__value">{leftSat.los_now ? 'LINK' : 'BLACKOUT'}</span>
                </div>
              </div>
              <div className="selection-kv selection-kv--full">
                <span className="selection-kv__label">POSITION</span>
                <span className="selection-kv__value">{leftSat.lat?.toFixed(2)}° · {leftSat.lon?.toFixed(2)}°</span>
              </div>
              <button className="ghost-btn" onClick={() => setSelectedSat(null)}>CLEAR SELECTION</button>
              <p className="helper-copy">Click a satellite in the main view to inspect health, warnings, and maneuver state.</p>
            </>
          ) : (
            <div className="empty-state"><div className="empty-state__text">No satellite selected</div></div>
          )}
        </section>

        <section className="sim-card">
          <div className="sim-card__title">Simulation</div>
          <label className="input-label">Step size</label>
          <select className="sim-select" value={simSpeed} onChange={(e) => setSimSpeed(Number(e.target.value))}>
            {STEP_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>

          <div className="mode-switch">
            <button className={viewMode === '3d' ? 'is-active' : ''} onClick={() => setViewMode('3d')}>3D Globe</button>
            <button className={viewMode === '2d' ? 'is-active' : ''} onClick={() => setViewMode('2d')}>2D Map</button>
          </div>

          <button className="primary-btn" disabled={loading || advancing} onClick={handleAdvance}>
            {loading || advancing ? 'RUNNING' : 'ADVANCE'}
          </button>

          <div className="mini-stats">
            <div><span>TIMESTAMP</span><strong>{timestamp !== '—' ? new Date(timestamp).toISOString().replace('T', ' ').replace('.000Z', '') : '—'}</strong></div>
            <div><span>SATELLITES</span><strong>{satellites.length}</strong></div>
            <div><span>DEBRIS</span><strong>{debrisCloud.length.toLocaleString()}</strong></div>
          </div>
        </section>

        <section className="sim-card">
          <div className="sim-card__title">Fleet</div>
          <div className="mini-stats">
            <div><span>NOMINAL</span><strong>{nominalCount}</strong></div>
            <div><span>CRITICAL</span><strong>{criticalCdms}</strong></div>
            <div><span>FUEL TOTAL</span><strong>{totalFuel.toFixed(1)} kg</strong></div>
            <div><span>UPTIME</span><strong>{data?.fleet_uptime_exp != null ? `${(data.fleet_uptime_exp * 100).toFixed(1)}%` : '—'}</strong></div>
          </div>
        </section>
      </aside>

      <main className="sim-viewport">
        <div className="sim-tabs">
          <button className={activeTab === 'bullseye' ? 'is-active' : ''} onClick={() => setActiveTab('bullseye')}>Bullseye</button>
          <button className={activeTab === 'ground' ? 'is-active' : ''} onClick={() => setActiveTab('ground')}>Ground Track</button>
          <button className={activeTab === 'timeline' ? 'is-active' : ''} onClick={() => setActiveTab('timeline')}>Timeline</button>
          <button className={activeTab === 'fleet' ? 'is-active' : ''} onClick={() => setActiveTab('fleet')}>Fleet</button>
        </div>

        <div className="sim-stage">
          {viewMode === '2d' ? (
            <GroundTrack2D
              satellites={satellites}
              debrisCloud={debrisCloud}
              timestamp={timestamp}
              selectedSat={selectedSat}
              onSelectSat={setSelectedSat}
              groundStations={groundStations}
              cdmWarnings={cdmWarnings}
            />
          ) : (
            <Globe3D
              satellites={satellites}
              debrisCloud={debrisCloud}
              cdmWarnings={cdmWarnings}
              selectedSat={selectedSat}
              onSelectSat={setSelectedSat}
              timestamp={timestamp}
            />
          )}

          <div className="stage-overlay-card">
            {activeTab === 'bullseye' && <BullseyePlot cdmWarnings={cdmWarnings} selectedSat={selectedSat} />}
            {activeTab === 'ground' && (
              <div className="overlay-copy">
                <div className="overlay-copy__title">Operational ground track</div>
                <div className="overlay-copy__body">Live orbit positions, forecast paths, ground stations, and conjunction geometry are rendered directly on the map. Select a satellite to inspect its past and future track.</div>
              </div>
            )}
            {activeTab === 'timeline' && <ManeuverGantt maneuvers={maneuverQueue} satellites={satellites} timestamp={timestamp} />}
            {activeTab === 'fleet' && (
              <FuelHeatmap
                satellites={satellites}
                selectedSat={selectedSat}
                onSelectSat={setSelectedSat}
                totalCollisionsAvoided={data?.total_collisions_avoided || 0}
                totalFuelConsumed={totalFuelUsed}
                metricsHistory={metricsHistory}
              />
            )}
          </div>
        </div>
      </main>

      <aside className="sim-rail sim-rail--right">
        <section className="sim-card">
          <div className="sim-card__title">Results</div>
          {resultsSummary ? (
            <div className="result-copy">
              <div>Lat <strong>{resultsSummary.lat?.toFixed(2)}°</strong> · Lon <strong>{resultsSummary.lon?.toFixed(2)}°</strong></div>
              <div>Fuel <strong>{resultsSummary.fuel?.toFixed(2)} kg</strong> · Alt <strong>{resultsSummary.alt?.toFixed(0)} km</strong></div>
            </div>
          ) : <div className="empty-state"><div className="empty-state__text">No active satellite</div></div>}
        </section>

        <section className="sim-card">
          <div className="sim-card__title">Warnings</div>
          <CDMList warnings={cdmWarnings} onSelectSat={setSelectedSat} />
        </section>

        <section className="sim-card">
          <div className="sim-card__title">Satellite Detail</div>
          <SatellitePanel satellite={selectedSatData} />
        </section>

        <section className="sim-card">
          <div className="sim-card__title">Selected Satellite Threats</div>
          <CDMList warnings={selectedSatCdms} onSelectSat={setSelectedSat} />
        </section>

        <div className="cta-row">
          <a className="nav-cta nav-cta--ghost" href="/belts">GO TO BELTS</a>
          <a className="nav-cta" href="/dashboard">GO TO DASHBOARD</a>
        </div>
      </aside>
    </div>
  );
}
