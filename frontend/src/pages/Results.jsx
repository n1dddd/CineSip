import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getGameState } from '../services/api';

export default function Results() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const state = await getGameState(code);
        const ps = state.players || [];
        const logs = state.drink_logs || [];

        const pd = {};
        for (const l of logs) pd[l.player_id] = (pd[l.player_id] || 0) + 1;

        const td = { 0: 0, 1: 0 };
        for (const l of logs) {
          const p = ps.find(pl => pl.id === l.player_id);
          if (p) td[p.team] = (td[p.team] || 0) + 1;
        }

        const t0 = td[0] || 0;
        const t1 = td[1] || 0;
        const maxD = Math.max(t0, t1, 1);

        setStats({
          game: state.game,
          players: ps.map(p => ({ ...p, drinks: pd[p.id] || 0 })).sort((a, b) => b.drinks - a.drinks),
          team0: t0,
          team1: t1,
          maxDrinks: maxD,
          winner: t0 >= t1 ? 0 : 1,
        });
      } catch (e) {
        console.error(e);
      }
      setLoading(false);
    })();
  }, [code]);

  if (loading) return <div className="flex-1 flex items-center justify-center"><div className="loading-spinner">Crunching the numbers...</div></div>;
  if (!stats) return <div className="flex-1 flex items-center justify-center"><div className="loading-spinner">Failed to load results</div></div>;

  const rankColor = (i) => {
    if (i === 0) return 'text-yellow-500 text-lg';
    if (i === 1) return 'text-neutral-100';
    if (i === 2) return 'text-orange-500';
    return 'text-text-muted';
  };

  return (
    <div className="flex-1 flex flex-col gap-6">
      <h1 className="text-center text-3xl font-bold">🏆 Game Over!</h1>

      <div className={`winner-banner ${stats.winner === 0 ? 'team-a' : 'team-b'}`}>
        <h2 className="text-2xl font-bold">{stats.winner === 0 ? '🔵 Team Blue' : '🔴 Team Red'} Wins!</h2>
        <p className="text-text-secondary mt-2">{stats.winner === 0 ? stats.team0 : stats.team1} drinks — true dedication</p>
      </div>

      <div>
        <h3 className="section-title">Team Drinks</h3>
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-sm min-w-16">🔵 Blue</span>
            <div className="bar-track">
              <div className="bar-fill team-a" style={{ width: `${(stats.team0 / stats.maxDrinks) * 100}%` }}>
                {stats.team0}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-semibold text-sm min-w-16">🔴 Red</span>
            <div className="bar-track">
              <div className="bar-fill team-b" style={{ width: `${(stats.team1 / stats.maxDrinks) * 100}%` }}>
                {stats.team1}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div>
        <h3 className="section-title">Player Leaderboard</h3>
        {stats.players.length > 0 ? (
          <ol className="flex flex-col gap-2 list-none">
            {stats.players.map((p, i) => (
              <li key={p.id} className="card flex items-center gap-3" style={{ padding: '12px' }}>
                <span className={`font-mono font-bold text-center w-6 ${rankColor(i)}`}>{i + 1}</span>
                <span className="flex-1 font-medium">{p.name}</span>
                <span className="font-mono font-bold text-orange-500">🍺 {p.drinks}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="empty-state">No players</p>
        )}
      </div>

      <button className="btn btn-primary btn-full btn-lg" onClick={() => navigate('/')}>
        🔄 Play Again
      </button>
    </div>
  );
}