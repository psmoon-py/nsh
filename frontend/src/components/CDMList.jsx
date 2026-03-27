import React from 'react';

function formatTCA(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatDistance(km) {
  if (km < 1) return `${(km * 1000).toFixed(0)}m`;
  return `${km.toFixed(2)} km`;
}

export default function CDMList({ warnings = [], onSelectSat }) {
  if (warnings.length === 0) {
    return (
      <div className="empty-state" style={{ height: 100 }}>
        <div className="empty-state__icon">✓</div>
        <div className="empty-state__text">No conjunction warnings</div>
      </div>
    );
  }

  return (
    <div className="cdm-list">
      {warnings.slice(0, 15).map((cdm, i) => {
        const risk = cdm.risk_level?.toLowerCase() || 'yellow';
        return (
          <div
            key={i}
            className={`cdm-item cdm-item--${risk}`}
            onClick={() => onSelectSat(cdm.sat_id)}
          >
            <div className={`cdm-item__dot cdm-item__dot--${risk}`} />
            <div className="cdm-item__info">
              <div className="cdm-item__pair">
                {cdm.sat_id} ↔ {cdm.deb_id}
              </div>
              <div className="cdm-item__detail">
                TCA: {formatTCA(cdm.tca_seconds)} &middot; Risk: {cdm.risk_level}
              </div>
            </div>
            <div
              className="cdm-item__distance"
              style={{
                color:
                  risk === 'critical' || risk === 'red'
                    ? 'var(--red)'
                    : risk === 'yellow'
                    ? 'var(--amber)'
                    : 'var(--green)',
              }}
            >
              {formatDistance(cdm.miss_distance_km)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
