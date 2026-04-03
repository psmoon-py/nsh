import React from 'react';
import StarfieldBackground from '../components/StarfieldBackground';

const cards = [
  {
    href: '/simulator',
    title: 'Orbital Insight Simulator',
    subtitle: 'Live constellation, CDMs, fuel, and autonomous maneuvers',
    metaA: 'Primary scene · Earth + operations',
    metaB: 'Backend-driven · live API snapshot',
    background: 'linear-gradient(160deg, rgba(17,50,88,0.65), rgba(0,0,0,0.2)), url(/textures/earth_daymap.jpg)',
  },
  {
    href: '/belts',
    title: 'Orbital Belts Explorer',
    subtitle: 'Altitude shells, debris density, and constellation distribution',
    metaA: '3D shell view · Earth-centered',
    metaB: 'Impacts-style exploratory mode',
    background: 'linear-gradient(160deg, rgba(13,26,42,0.7), rgba(0,0,0,0.25)), radial-gradient(circle at 50% 50%, rgba(34,60,120,0.6), rgba(0,0,0,0.0) 60%)',
  },
  {
    href: '/simulator?view=2d',
    title: 'Ground Track Operations',
    subtitle: 'Mercator operational dashboard with tracks, terminator, and warnings',
    metaA: 'Required by problem statement',
    metaB: 'Canvas + SVG dense overlay',
    background: 'linear-gradient(160deg, rgba(35,56,78,0.75), rgba(0,0,0,0.3)), url(/textures/earth_daymap.jpg)',
  },
  {
    href: '/simulator?panel=timeline',
    title: 'Maneuver Timeline',
    subtitle: 'Burn windows, cooldowns, conflicts, and blackout logic',
    metaA: 'Gantt scheduler',
    metaB: 'Thruster-safe automated actions',
    background: 'linear-gradient(160deg, rgba(33,18,8,0.75), rgba(0,0,0,0.25)), radial-gradient(circle at 30% 30%, rgba(255,142,51,0.35), rgba(0,0,0,0.0) 45%)',
  },
  {
    href: '/simulator?panel=fleet',
    title: 'Fleet Resource Monitoring',
    subtitle: 'Fuel heatmaps, efficiency curve, uptime, and health view',
    metaA: '50+ satellites',
    metaB: '10,000+ debris-ready front end',
    background: 'linear-gradient(160deg, rgba(6,40,34,0.8), rgba(0,0,0,0.25)), radial-gradient(circle at 70% 40%, rgba(0,229,198,0.24), rgba(0,0,0,0.0) 44%)',
  },
];

export default function DashboardPage() {
  return (
    <div className="impacts-page impacts-dashboard-page">
      <StarfieldBackground density={180} speed={0.02} />
      <div className="impacts-now-showing">Orbital Insight — Dashboard</div>

      <main className="impacts-dashboard-shell">
        <div className="impacts-dashboard-brand">
          <div className="impacts-brand-mark">
            <span className="planet" />
            <span className="ring" />
            <span className="flare" />
          </div>
        </div>

        <section className="impacts-accordion" aria-label="Main modules">
          {cards.map((card, idx) => (
            <a key={idx} className="impacts-card" href={card.href}>
              <div className="impacts-card__bg" style={{ backgroundImage: card.background }} />
              <div className="impacts-card__content">
                <div className="impacts-card__number">0{idx + 1}</div>
                <h2 className="impacts-card__title">{card.title}</h2>
                <p className="impacts-card__subtitle">{card.subtitle}</p>
                <div className="impacts-card__specs">
                  <div><span>Mode</span><strong>{card.metaA}</strong></div>
                  <div><span>Focus</span><strong>{card.metaB}</strong></div>
                </div>
                <div className="impacts-card__cta">→</div>
              </div>
            </a>
          ))}
        </section>

        <section className="impacts-footer-grid">
          <div>
            <h3>About this build</h3>
            <p>Impacts-inspired layout adapted for the National Space Hackathon ACM problem.</p>
          </div>
          <div>
            <h3>Mission objective</h3>
            <p>Avoid conjunctions, preserve fuel, recover orbital slots, and surface decisions clearly.</p>
          </div>
          <div>
            <h3>Primary pages</h3>
            <p>Dashboard, Simulator, and Belts explorer.</p>
          </div>
        </section>
      </main>
    </div>
  );
}
