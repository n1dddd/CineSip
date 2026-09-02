import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import usePlayerStore from '../store/playerStore';
import useGameStore from '../store/gameStore';
import { getGameState, startGame } from '../services/api';

export default function Lobby() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { player, players, setPlayers } = usePlayerStore();
  const { setRules } = useGameStore();
  const isHost = player?.isHost || false;
  const [game, setGame] = useState(null);
  const [copied, setCopied] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const state = await getGameState(code);
      setGame(state.game);
      setPlayers(state.players || []);
      setRules(state.rules || []);
      if (state.game?.status === 'active') {
        navigate(`/game/${code}`, { replace: true });
      }
    } catch (e) {
      console.error('Lobby refresh failed', e);
    }
  }, [code, navigate]);

  useEffect(() => {
    refresh();
    const i = setInterval(refresh, 2000);
    return () => clearInterval(i);
  }, [refresh]);

  const copyCode = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleStart = async () => {
    try {
      await startGame(game.id);
      navigate(`/game/${code}`, { replace: true });
    } catch (e) {
      console.error('Start failed', e);
    }
  };

  if (!game) return <div className="flex-1 flex items-center justify-center"><div className="loading-spinner">Loading lobby...</div></div>;

  const teamA = players.filter(p => p.team === 0);
  const teamB = players.filter(p => p.team === 1);

  return (
    <div className="flex-1 flex flex-col gap-6">
      <button className="btn-back" onClick={() => navigate('/')}>← Back</button>

      <div className="text-center py-4">
        <h3 className="text-text-secondary text-sm font-semibold uppercase tracking-wider mb-2">Room Code</h3>
        <code
          className="block font-mono text-3xl tracking-[0.3em] text-cyan-500 select-all cursor-pointer"
          style={{ textShadow: '0 0 10px rgba(0,229,255,0.25)' }}
          onClick={copyCode}
        >
          {code}
        </code>
        <p className="text-xs text-text-muted mt-2">{copied ? '✓ Copied!' : 'Tap to copy — share with friends'}</p>
      </div>

      <h2 className="text-center text-text-primary">{game.movie_title || 'No movie selected yet'}</h2>

      <div>
        <h3 className="section-title">Teams</h3>
        <div className="flex gap-3">
          <div className="team-panel team-a text-center">
            <h3 className="text-cyan-500 font-semibold">🔵 Team Blue</h3>
            <p className="text-text-muted text-sm mt-1">{teamA.length} players</p>
          </div>
          <div className="team-panel team-b text-center">
            <h3 className="text-pink-500 font-semibold">🔴 Team Red</h3>
            <p className="text-text-muted text-sm mt-1">{teamB.length} players</p>
          </div>
        </div>
      </div>

      <div>
        <h3 className="section-title">Players ({players.length})</h3>
        {players.length > 0 ? (
          <div className="grid grid-cols-2 gap-2">
            {players.map(p => (
              <div key={p.id} className={`player-badge ${p.team === 0 ? 'team-a' : 'team-b'}`}>
                <div className="avatar">{p.name[0].toUpperCase()}</div>
                <span className="flex-1 font-medium truncate">{p.name}</span>
                {p.is_host && <span>👑</span>}
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-state">Waiting for players to join...</p>
        )}
      </div>

      {isHost && (
        <button
          className="btn btn-primary btn-full btn-lg"
          onClick={handleStart}
          disabled={players.length < 2}
        >
          {players.length < 2 ? 'Need at least 2 players' : '🍻 Start the Game!'}
        </button>
      )}
    </div>
  );
}