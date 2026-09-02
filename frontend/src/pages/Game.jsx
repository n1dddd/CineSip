import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import usePlayerStore from '../store/playerStore';
import useGameStore from '../store/gameStore';
import { getGameState, logDrink } from '../services/api';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function Game() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { player, players } = usePlayerStore();
  const { rules, drinkCounts, logDrink: trackDrink } = useGameStore();
  const [game, setGame] = useState(null);
  const [alert, setAlert] = useState(null);

  const myTeam = players.find(p => p.id === player?.id)?.team ?? 0;
  const myRules = rules.filter(r => r.team === myTeam);
  const otherRules = rules.filter(r => r.team !== myTeam);

  const refresh = useCallback(async () => {
    try {
      const state = await getGameState(code);
      setGame(state.game);
      if (state.game?.status === 'finished') {
        navigate(`/results/${code}`, { replace: true });
      }
    } catch (e) {
      console.error(e);
    }
  }, [code, navigate]);

  useEffect(() => {
    refresh();
    const i = setInterval(refresh, 3000);
    return () => clearInterval(i);
  }, [refresh]);

  const handleDrink = async (rule) => {
    if (!player?.id) return;
    try {
      await logDrink(game.id, player.id, rule.id);
      trackDrink(player.id, rule.team);
      setAlert({ team: rule.team, text: rule.description });
      setTimeout(() => setAlert(null), 3000);
    } catch (e) {
      console.error(e);
    }
  };

  if (!game) return <div className="flex-1 flex items-center justify-center"><div className="loading-spinner">Loading game...</div></div>;

  return (
    <div className="flex-1 flex flex-col gap-6">
      {alert && (
        <div className={`drink-alert ${alert.team === 0 ? 'team-a' : 'team-b'}`}>
          🍻 DRINK! — {alert.text}
        </div>
      )}

      <div className="flex justify-between items-center">
        <button className="btn-back" onClick={() => navigate(`/lobby/${code}`)}>← Lobby</button>
        <h2 className="text-gradient text-lg text-center">{game.movie_title}</h2>
        <div className="w-16" />
      </div>

      <div className="flex flex-col gap-4">
        {/* My Team */}
        <div className={`team-panel ${myTeam === 0 ? 'team-a' : 'team-b'}`}>
          <div className="team-header">
            <h3 className="font-semibold">{myTeam === 0 ? '🔵 Your Team (Blue)' : '🔴 Your Team (Red)'}</h3>
            <span className="font-mono text-lg font-bold text-orange-500">🍺 {drinkCounts[myTeam] || 0}</span>
          </div>
          <div className="flex flex-col gap-2">
            {myRules.map(rule => (
              <div key={rule.id} className="rule-row" onClick={() => handleDrink(rule)}>
                <span className="flex-1">{rule.description}</span>
                <span className="font-mono text-xs text-text-muted min-w-6 text-center">{rule.trigger_count || 0}x</span>
                <button className="drink-hit" onClick={e => { e.stopPropagation(); handleDrink(rule); }}>🍻</button>
              </div>
            ))}
            {myRules.length === 0 && <p className="empty-state">No rules assigned</p>}
          </div>
        </div>

        {/* Other Team */}
        <div className="team-panel opacity-70">
          <div className="team-header">
            <h3 className="font-semibold">{myTeam !== 0 ? '🔵 Team Blue' : '🔴 Team Red'}</h3>
            <span className="font-mono text-lg font-bold text-orange-500">🍺 {drinkCounts[myTeam === 0 ? 1 : 0] || 0}</span>
          </div>
          <div className="flex flex-col gap-2">
            {otherRules.map(rule => (
              <div key={rule.id} className="rule-row">
                <span className="flex-1">{rule.description}</span>
                <span className="font-mono text-xs text-text-muted min-w-6 text-center">{rule.trigger_count || 0}x</span>
              </div>
            ))}
            {otherRules.length === 0 && <p className="empty-state">No rules assigned</p>}
          </div>
        </div>
      </div>

      <div>
        <h3 className="section-title">Players Online</h3>
        <div className="grid grid-cols-2 gap-2">
          {players.map(p => (
            <div key={p.id} className={`player-badge ${p.team === 0 ? 'team-a' : 'team-b'}`}>
              <div className="avatar">{p.name[0].toUpperCase()}</div>
              <span className="flex-1 font-medium truncate">{p.name}</span>
            </div>
          ))}
        </div>
      </div>

      <button
        className="btn btn-secondary btn-full"
        onClick={async () => {
          await fetch(`${API_BASE}/api/games/${game.id}/finish`, { method: 'POST' });
          navigate(`/results/${code}`, { replace: true });
        }}
      >
        🏁 End Game
      </button>
    </div>
  );
}