import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import Home from './pages/Home';
import Lobby from './pages/Lobby';
import Game from './pages/Game';
import Results from './pages/Results';

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/lobby/:code" element={<Lobby />} />
          <Route path="/game/:code" element={<Game />} />
          <Route path="/results/:code" element={<Results />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
      <BottomNav />
    </BrowserRouter>
  );
}

/**
 * Only shown once a game exists, and every item goes somewhere real.
 * On the home screen there is nothing to navigate between, so it stays hidden.
 */
function BottomNav() {
  const { pathname } = useLocation();
  const navigate = useNavigate();

  const match = pathname.match(/^\/(lobby|game|results)\/([A-Z0-9]{6})/i);
  if (!match) return null;

  const [, section, code] = match;
  const items = [
    { key: 'lobby', label: 'Room', to: `/lobby/${code}` },
    { key: 'game', label: 'Rules', to: `/game/${code}` },
    { key: 'results', label: 'Score', to: `/results/${code}` },
  ];

  return (
    <nav className="bottom-nav">
      {items.map((item) => {
        const active = section.toLowerCase() === item.key;
        return (
          <button
            key={item.key}
            className={`nav-item ${active ? 'nav-item-active' : ''}`}
            onClick={() => navigate(item.to)}
            aria-current={active ? 'page' : undefined}
          >
            <span className="nav-dot" />
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
