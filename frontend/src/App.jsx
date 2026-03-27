import React, { useState, useCallback } from 'react';
import useSnapshot, { postSimulateStep } from './hooks/useSnapshot';
import StatusBar from './components/StatusBar';
import Globe3D from './components/Globe3D';
import BullseyePlot from './components/BullseyePlot';
import ManeuverGantt from './components/ManeuverGantt';
import FuelHeatmap from './components/FuelHeatmap';
import SatellitePanel from './components/SatellitePanel';
import CDMList from './components/CDMList';

export default function App() {
  const { data, loading, error, refresh } = useSnapshot();
  const [selectedSat, setSelectedSat] = useState(null);
  const [simSpeed, setSimSpeed] = useState(60); // seconds per tick

  const handleAdvance = useCallback(async () => {
    await postSimulateStep(simSpeed);
    refresh();
  }, [simSpeed, refresh]);

  const satellites = data?.satellites || [];
  const debrisCloud = data?.debris_cloud || [];
  const cdmWarnings = data?.cdm_warnings || [];
  const maneuverQueue = data?.maneuver_queue || [];
  const timestamp = data?.timestamp || '—';

  // Find selected satellite data
  const selectedSatData = selectedSat
    ? satellites.find((s) => s.id === selectedSat)
    : null;

  // Summary stats
  const nominalCount = satellites.filter((s) => s.status === 'NOMINAL').length;
  const criticalCdms = cdmWarnings.filter((c) => c.risk_level === 'CRITICAL').length;
  const totalFuel = satellites.reduce((sum, s) => sum + (s.fuel_kg || 0), 0);

  return (
    <div className="dashboard">
      {/* ---- Top Header ---- */}
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
        loading={loading}
        error={error}
      />

      {/* ---- Main Area: Globe + Bottom Panels ---- */}
      <div className="main-area">
        <div className="globe-container">
          <Globe3D
            satellites={satellites}
            debrisCloud={debrisCloud}
            cdmWarnings={cdmWarnings}
            selectedSat={selectedSat}
            onSelectSat={setSelectedSat}
          />
          <div className="globe-overlay">
            <span className="globe-overlay__badge globe-overlay__badge--live">
              LIVE TRACKING
            </span>
            <span className="globe-overlay__badge">
              {satellites.length} SAT &middot; {debrisCloud.length} DEB
            </span>
          </div>
        </div>

        <div className="bottom-panels">
          <div className="panel">
            <div className="panel__header">
              <span className="panel__title">Conjunction Bullseye</span>
              <span className="panel__tag">
                {selectedSat || 'Select a satellite'}
              </span>
            </div>
            <BullseyePlot
              cdmWarnings={cdmWarnings}
              selectedSat={selectedSat}
            />
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

      {/* ---- Sidebar ---- */}
      <div className="sidebar">
        {/* Fuel Heatmap */}
        <div className="panel">
          <div className="panel__header">
            <span className="panel__title">Fleet Fuel Status</span>
            <span className="panel__tag">
              {Math.round(totalFuel)} kg total
            </span>
          </div>
          <FuelHeatmap
            satellites={satellites}
            selectedSat={selectedSat}
            onSelectSat={setSelectedSat}
          />
        </div>

        {/* CDM List */}
        <div className="panel" style={{ flex: 1, minHeight: 0 }}>
          <div className="panel__header">
            <span className="panel__title">CDM Warnings</span>
            {criticalCdms > 0 ? (
              <span className="panel__tag panel__tag--critical">
                {criticalCdms} CRITICAL
              </span>
            ) : (
              <span className="panel__tag panel__tag--nominal">ALL CLEAR</span>
            )}
          </div>
          <CDMList warnings={cdmWarnings} onSelectSat={setSelectedSat} />
        </div>

        {/* Satellite Detail */}
        <div className="panel">
          <div className="panel__header">
            <span className="panel__title">Satellite Detail</span>
            {selectedSatData && (
              <span
                className={`panel__tag panel__tag--${
                  selectedSatData.status === 'NOMINAL' ? 'nominal' : 'warning'
                }`}
              >
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
