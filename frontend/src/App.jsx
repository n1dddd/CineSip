import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
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
        <BottomNav />
      </div>
    </BrowserRouter>
  );
}

function BottomNav() {
  const { pathname } = useLocation();
  const isGame = pathname.startsWith('/lobby') || pathname.startsWith('/game');
  const isResults = pathname.startsWith('/results');

  return (
    <nav className="bottom-nav">
      <a href="/" className={pathname === '/' ? 'active' : ''}>
        <span className="text-lg">🏠</span>
        Home
      </a>
      <a href="/" className={isGame ? 'active' : ''}>
        <span className="text-lg">🎬</span>
        Game
      </a>
      <a href="/" className={isResults ? 'active' : ''}>
        <span className="text-lg">📊</span>
        Results
      </a>
    </nav>
  );
}