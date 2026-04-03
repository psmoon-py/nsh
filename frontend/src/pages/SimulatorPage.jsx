import React, { useMemo, useState, useCallback, useEffect } from 'react';
import useSnapshot, { postSimulateStep } from '../hooks/useSnapshot';
import Globe3D from '../components/Globe3D';
import GroundTrack2D from '../components/GroundTrack2D';
import SatellitePanel from '../components/SatellitePanel';
import CDMList from '../components/CDMList';
import FuelHeatmap from '../components/FuelHeatmap';
import BullseyePlot from '../components/BullseyePlot';
import ManeuverGantt from '../components/ManeuverGantt';

function metricValue(label, value, accent) {
  return (
    <div className="sim-mini-metric" key={label}>
      <span>{label}</span>
      <strong style={accent ? { color: accent } : undefined}>{value}</strong>
    </div>
  );
}

function SidebarSection({ title, accent = 'cyan', children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={`sim-section sim-section--${accent} ${open ? '' : 'is-collapsed'}`}>
      <button className="sim-section__header" onClick={() => setOpen((v) => !v)}>
        <span className="sim-section__chevron">▾</span>
        <span>{title}</span>
      </button>
      {open && <div className="sim-section__body">{children}</div>}
    </section>
  );
}

export default function SimulatorPage() {
  const { data, loading, error, refresh } = useSnapshot();
  const params = new URLSearchParams(window.location.search);
  const initialView = params.get('view') === '2d' ? '2d' : '3d';
  const initialPanel = params.get('panel') || 'bullseye';

  const [viewMode, setViewMode] = useState(initialView);
  const [drawer, setDrawer] = useState(initialPanel);
  const [selectedSat, setSelectedSat] = useState(null);
  const [stepSeconds, setStepSeconds] = useState(300);
  const [advancing, setAdvancing] = useState(false);

  const satellites = data?.satellites || [];
  const debrisCloud = data?.debris_cloud || [];
  const cdmWarnings = data?.cdm_warnings || [];
  const maneuverQueue = data?.maneuver_queue || [];
  const timestamp = data?.timestamp || '—';
  const groundStations = data?.ground_stations || [];
  const metricsHistory = data?.metrics_history || [];

  useEffect(() => {
    if (!selectedSat && satellites.length) setSelectedSat(satellites[0].id);
  }, [satellites, selectedSat]);

  const selectedSatData = useMemo(
    () => satellites.find((s) => s.id === selectedSat) || null,
    [satellites, selectedSat]
  );
  const selectedWarnings = useMemo(
    () => cdmWarnings.filter((c) => c.sat_id === selectedSat),
    [cdmWarnings, selectedSat]
  );

  const stats = useMemo(() => {
    const nominal = satellites.filter((s) => s.status === 'NOMINAL').length;
    const totalFuel = satellites.reduce((sum, s) => sum + (s.fuel_kg || 0), 0);
    const critical = cdmWarnings.filter((c) => c.risk_level === 'CRITICAL').length;
    return { nominal, totalFuel, critical };
  }, [satellites, cdmWarnings]);

  const handleAdvance = useCallback(async () => {
    if (advancing) return;
    setAdvancing(true);
    try {
      await postSimulateStep(stepSeconds);
      await refresh();
    } finally {
      setAdvancing(false);
    }
  }, [advancing, refresh, stepSeconds]);

  const DrawerContent = () => {
    switch (drawer) {
      case 'map':
        return (
          <GroundTrack2D
            satellites={satellites}
            debrisCloud={debrisCloud}
            timestamp={timestamp}
            selectedSat={selectedSat}
            onSelectSat={setSelectedSat}
            groundStations={groundStations}
            cdmWarnings={cdmWarnings}
          />
        );
      case 'timeline':
        return <ManeuverGantt maneuvers={maneuverQueue} satellites={satellites} timestamp={timestamp} />;
      case 'fleet':
        return (
          <FuelHeatmap
            satellites={satellites}
            selectedSat={selectedSat}
            onSelectSat={setSelectedSat}
            totalCollisionsAvoided={data?.total_collisions_avoided || 0}
            totalFuelConsumed={(50 * satellites.length) - stats.totalFuel}
            metricsHistory={metricsHistory}
          />
        );
      default:
        return <BullseyePlot cdmWarnings={cdmWarnings} selectedSat={selectedSat} />;
    }
  };

  return (
    <div className="impacts-page sim-page">
      <div className="sim-top-label">Orbital Insight — Simulator</div>

      <aside className="sim-rail sim-rail--left">
        <SidebarSection title="Selection" accent="cyan">
          <div className="sim-chip-grid sim-chip-grid--three">
            <div className="sim-chip"><span>Satellite</span><strong>{selectedSatData?.id || '—'}</strong></div>
            <div className="sim-chip"><span>Status</span><strong>{selectedSatData?.status || '—'}</strong></div>
            <div className="sim-chip"><span>LOS</span><strong>{selectedSatData?.los_now ? 'LINK' : 'BLACKOUT'}</strong></div>
          </div>
          <div className="sim-wide-chip">
            <span>Position</span>
            <strong>{selectedSatData ? `${selectedSatData.lat?.toFixed(2)}° · ${selectedSatData.lon?.toFixed(2)}°` : 'Click a satellite in scene'}</strong>
          </div>
          <button className="sim-ghost-btn" onClick={() => setSelectedSat(null)}>Clear selection</button>
          <p className="sim-note">Click a satellite in the main view to inspect its health, warnings, and maneuver state.</p>
        </SidebarSection>

        <SidebarSection title="Simulation" accent="violet">
          <div className="sim-slider-row">
            <label>Step size</label>
            <select value={stepSeconds} onChange={(e) => setStepSeconds(Number(e.target.value))}>
              <option value={10}>+10 s</option>
              <option value={60}>+1 min</option>
              <option value={300}>+5 min</option>
              <option value={600}>+10 min</option>
              <option value={3600}>+1 h</option>
              <option value={86400}>+24 h</option>
            </select>
          </div>
          <div className="sim-segmented">
            <button className={viewMode === '3d' ? 'is-active' : ''} onClick={() => setViewMode('3d')}>3D Globe</button>
            <button className={viewMode === '2d' ? 'is-active' : ''} onClick={() => setViewMode('2d')}>2D Map</button>
          </div>
          <div className="sim-btn-row">
            <button className="sim-primary-btn" onClick={handleAdvance} disabled={loading || advancing}>{advancing ? 'RUNNING' : 'ADVANCE'}</button>
          </div>
          <div className="sim-kv-list">
            {metricValue('Timestamp', timestamp !== '—' ? new Date(timestamp).toISOString().slice(0, 19).replace('T', ' ') : '—')}
            {metricValue('Satellites', satellites.length)}
            {metricValue('Debris', debrisCloud.length.toLocaleString())}
          </div>
        </SidebarSection>

        <SidebarSection title="Fleet" accent="orange">
          <div className="sim-kv-list compact">
            {metricValue('Nominal', stats.nominal, 'var(--green)')}
            {metricValue('Critical', stats.critical, stats.critical > 0 ? 'var(--red)' : 'var(--green)')}
            {metricValue('Fuel total', `${stats.totalFuel.toFixed(1)} kg`, 'var(--cyan-bright)')}
            {metricValue('Uptime', data?.fleet_uptime_exp != null ? `${(data.fleet_uptime_exp * 100).toFixed(1)}%` : '—')}
          </div>
        </SidebarSection>
      </aside>

      <main className="sim-viewport-wrap">
        <div className="sim-viewport">
          {viewMode === '3d' ? (
            <Globe3D
              satellites={satellites}
              debrisCloud={debrisCloud}
              cdmWarnings={cdmWarnings}
              selectedSat={selectedSat}
              onSelectSat={setSelectedSat}
              timestamp={timestamp}
            />
          ) : (
            <GroundTrack2D
              satellites={satellites}
              debrisCloud={debrisCloud}
              timestamp={timestamp}
              selectedSat={selectedSat}
              onSelectSat={setSelectedSat}
              groundStations={groundStations}
              cdmWarnings={cdmWarnings}
            />
          )}

          <div className="sim-overlay-badges">
            <span className="live">LIVE OPERATIONS</span>
            <span>{satellites.length} SAT</span>
            <span>{debrisCloud.length} DEB</span>
            <span>{cdmWarnings.length} CDM</span>
          </div>

          <div className="sim-bottom-drawer">
            <div className="sim-drawer-tabs">
              {[
                ['bullseye', 'Bullseye'],
                ['map', 'Ground Track'],
                ['timeline', 'Timeline'],
                ['fleet', 'Fleet'],
              ].map(([key, label]) => (
                <button key={key} className={drawer === key ? 'is-active' : ''} onClick={() => setDrawer(key)}>{label}</button>
              ))}
            </div>
            <div className="sim-drawer-body">
              <DrawerContent />
            </div>
          </div>
        </div>
      </main>

      <aside className="sim-rail sim-rail--right">
        <SidebarSection title="Results" accent="cyan">
          <div className="sim-results-overview">
            <div>Lat <strong>{selectedSatData?.lat?.toFixed(2) ?? '—'}°</strong> · Lon <strong>{selectedSatData?.lon?.toFixed(2) ?? '—'}°</strong></div>
            <div>Fuel <strong>{selectedSatData?.fuel_kg?.toFixed(2) ?? '—'} kg</strong> · Alt <strong>{selectedSatData?.alt?.toFixed(0) ?? '—'} km</strong></div>
          </div>
        </SidebarSection>

        <SidebarSection title="Warnings" accent="violet">
          <CDMList warnings={cdmWarnings} onSelectSat={setSelectedSat} />
        </SidebarSection>

        <SidebarSection title="Satellite Detail" accent="orange">
          <SatellitePanel satellite={selectedSatData} />
        </SidebarSection>

        <SidebarSection title="Selected Satellite Threats" accent="green" defaultOpen={false}>
          <CDMList warnings={selectedWarnings} onSelectSat={setSelectedSat} />
        </SidebarSection>
      </aside>

      <a className="impacts-nav-btn" href="/dashboard">GO TO DASHBOARD</a>
      <a className="impacts-nav-btn impacts-nav-btn--secondary" href="/belts">GO TO BELTS</a>
      {error && <div className="sim-error-banner">OFFLINE · {error}</div>}
    </div>
  );
}
