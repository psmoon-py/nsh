import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import './styles/impacts-frontend.css';
import DashboardPage from './pages/DashboardPage';
import SimulatorPage from './pages/SimulatorPage';
import BeltsPage from './pages/BeltsPage';

function normalizePath(pathname) {
  const path = pathname.replace(/\/+$/, '') || '/';
  return path;
}

function resolvePage(pathname) {
  const path = normalizePath(pathname);
  if (path === '/' || path === '/dashboard') return <DashboardPage />;
  if (path === '/simulator') return <SimulatorPage />;
  if (path === '/belts') return <BeltsPage />;
  return <DashboardPage />;
}

function App() {
  return resolvePage(window.location.pathname);
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);