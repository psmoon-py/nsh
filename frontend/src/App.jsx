import React, { useState, useCallback } from 'react';
import useSnapshot, { postSimulateStep } from './hooks/useSnapshot';
import StatusBar from './components/StatusBar';
import Globe3D from './components/Globe3D';
import GroundTrack2D from './components/GroundTrack2D';
import BullseyePlot from './components/BullseyePlot';
import ManeuverGantt from './components/ManeuverGantt';
import FuelHeatmap from './components/FuelHeatmap';
import SatellitePanel from './components/SatellitePanel';
import CDMList from './components/CDMList';
import './styles/dashboard.css';

export default function App() {
  const { data, loading, error, refresh } = useSnapshot();
  const [selectedSat, setSelectedSat] = useState(null);
  const [simSpeed, setSimSpeed]     = useState(60);
  // Default to 2D map (operational view per blueprint)
  const [viewMode, setViewMode]     = useState('2d');
  const [advancing, setAdvancing]   = useState(false);

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

  const satellites    = data?.satellites    || [];
  const debrisCloud   = data?.debris_cloud  || [];
  const cdmWarnings   = data?.cdm_warnings  || [];
  const maneuverQueue = data?.maneuver_queue || [];
  const timestamp     = data?.timestamp     || '—';
  const groundStations = data?.ground_stations || [];
  const metricsHistory = data?.metrics_history || [];

  const selectedSatData = selectedSat
    ? satellites.find((s) => s.id === selectedSat)
    : null;

  const nominalCount  = satellites.filter((s) => s.status === 'NOMINAL').length;
  const criticalCdms  = cdmWarnings.filter((c) => c.risk_level === 'CRITICAL').length;
  const totalFuel     = satellites.reduce((sum, s) => sum + (s.fuel_kg || 0), 0);

  // CDMs affecting selected satellite (for overlay strip)
  const selectedSatCdms = selectedSat
    ? cdmWarnings.filter((c) => c.sat_id === selectedSat)
    : [];

  return (
    <div className="dashboard">
      {/* ─── Header ─── */}
      <StatusBar
        timestamp={timestamp}
        satCount={satellites.length}
        debrisCount={debrisCloud.length}
        nominalCount={nominalCount}
        cdmCount={cdmWarnings.length}
        criticalCount={criticalCdms}
        totalFuel={totalFuel}
        simSpeed={simSpeed}
        onSimSpeedChange={setSimSpeed}
        onAdvance={handleAdvance}
        loading={loading || advancing}
        error={error}
        fleetUptimeExp={data?.fleet_uptime_exp}
        totalManeuvers={data?.total_maneuvers_executed || 0}
        totalCollisionsAvoided={data?.total_collisions_avoided || 0}
      />

      {/* ─── Main Area ─── */}
      <div className="main-area">
        <div className="globe-container">
          {/* View toggle */}
          <div className="view-toggle">
            <button
              onClick={() => setViewMode('2d')}
              style={{
                background: viewMode === '2d' ? 'var(--cyan)' : 'transparent',
                color: viewMode === '2d' ? '#000' : 'var(--text-dim)',
                fontWeight: viewMode === '2d' ? 700 : 400,
              }}
            >
              2D MAP
            </button>
            <button
              onClick={() => setViewMode('3d')}
              style={{
                background: viewMode === '3d' ? 'var(--cyan)' : 'transparent',
                color: viewMode === '3d' ? '#000' : 'var(--text-dim)',
                fontWeight: viewMode === '3d' ? 700 : 400,
              }}
            >
              3D GLOBE
            </button>
          </div>

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

          {/* Bottom-left status badges */}
          <div className="globe-overlay">
            <span className="globe-overlay__badge globe-overlay__badge--live">
              LIVE TRACKING
            </span>
            <span className="globe-overlay__badge">
              {satellites.length} SAT &middot; {debrisCloud.length} DEB
            </span>
            {selectedSatCdms.length > 0 && (
              <span className="globe-overlay__badge" style={{
                borderColor: 'var(--red-dim)', color: 'var(--red)',
              }}>
                ⚠ {selectedSatCdms.length} CDM{selectedSatCdms.length > 1 ? 's' : ''}
              </span>
            )}
          </div>

          {/* Selected satellite quick strip */}
          {selectedSatData && (
            <div style={{
              position: 'absolute', top: 44, left: 10, right: 10,
              display: 'flex', gap: 8, zIndex: 15, pointerEvents: 'none',
            }}>
              <div style={{
                background: 'rgba(9,13,24,0.92)',
                border: '1px solid var(--cyan-dim)',
                borderRadius: 3, padding: '3px 10px',
                fontFamily: 'var(--font-mono)', fontSize: 9,
                color: 'var(--cyan)', letterSpacing: 1, backdropFilter: 'blur(8px)',
              }}>
                {selectedSatData.id} &nbsp;|&nbsp; ⛽ {selectedSatData.fuel_kg?.toFixed(1)} kg
                &nbsp;|&nbsp; {selectedSatData.status}
                &nbsp;|&nbsp; LOS: {selectedSatData.los_now ? '✓' : '✗'}
              </div>
            </div>
          )}
        </div>

        <div className="bottom-panels">
          <div className="panel">
            <div className="panel__header">
              <span className="panel__title">Conjunction Bullseye</span>
              <span className="panel__tag">
                {selectedSat || 'Select satellite'}
              </span>
            </div>
            <BullseyePlot cdmWarnings={cdmWarnings} selectedSat={selectedSat} />
          </div>
          <div className="panel">
            <div className="panel__header">
              <span className="panel__title">Maneuver Timeline</span>
              <span className="panel__tag">{maneuverQueue.length} queued</span>
            </div>
            <ManeuverGantt
              maneuvers={maneuverQueue}
              satellites={satellites}
              timestamp={timestamp}
            />
          </div>
        </div>
      </div>

      {/* ─── Sidebar ─── */}
      <div className="sidebar">
        <div className="panel">
          <div className="panel__header">
            <span className="panel__title">Fleet Fuel Status</span>
            <span className="panel__tag">{Math.round(totalFuel)} kg total</span>
          </div>
          <FuelHeatmap
            satellites={satellites}
            selectedSat={selectedSat}
            onSelectSat={setSelectedSat}
            totalCollisionsAvoided={data?.total_collisions_avoided || 0}
            totalFuelConsumed={(50 * satellites.length) - totalFuel}
            metricsHistory={metricsHistory}
          />
        </div>

        <div className="panel" style={{ flex: 1, minHeight: 0 }}>
          <div className="panel__header">
            <span className="panel__title">CDM Warnings</span>
            {criticalCdms > 0 ? (
              <span className="panel__tag panel__tag--critical">{criticalCdms} CRITICAL</span>
            ) : (
              <span className="panel__tag panel__tag--nominal">ALL CLEAR</span>
            )}
          </div>
          <CDMList warnings={cdmWarnings} onSelectSat={setSelectedSat} />
        </div>

        <div className="panel">
          <div className="panel__header">
            <span className="panel__title">Satellite Detail</span>
            {selectedSatData && (
              <span className={`panel__tag panel__tag--${
                selectedSatData.status === 'NOMINAL' ? 'nominal' : 'warning'
              }`}>
                {selectedSatData.status}
              </span>
            )}
          </div>
          <SatellitePanel satellite={selectedSatData} />
        </div>
      </div>
    </div>
  );
}
