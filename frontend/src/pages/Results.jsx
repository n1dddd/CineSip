import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getGameState } from '../services/api';

const TEAM_NAME = ['Amber', 'Teal'];

export default function Results() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const s = await getGameState(code);
        const ps = s.players || [];
        const logs = s.drink_logs || [];

        const per = {};
        for (const l of logs) per[l.player_id] = (per[l.player_id] || 0) + 1;

        const team = { 0: 0, 1: 0 };
        for (const l of logs) {
          const p = ps.find((x) => x.id === l.player_id);
          if (p) team[p.team] += 1;
        }

        setStats({
          movie: s.game?.movie_title,
          standings: ps
            .map((p) => ({ ...p, sips: per[p.id] || 0 }))
            .sort((a, b) => b.sips - a.sips),
          a: team[0],
          b: team[1],
          max: Math.max(team[0], team[1], 1),
          total: logs.length,
          winner: team[0] === team[1] ? null : (team[0] > team[1] ? 0 : 1),
        });
      } catch {
        /* handled by null state */
      }
      setLoading(false);
    })();
  }, [code]);

  if (loading) return <div className="loading-note">Counting the damage…</div>;
  if (!stats) return <div className="loading-note">Couldn't load the results</div>;

  const tie = stats.winner === null;

  return (
    <div className="flex-1 flex flex-col" style={{ gap: 26 }}>
      <header>
        <p className="eyebrow">Final call</p>
        {stats.movie && (
          <h1 className="now-playing-title" style={{ marginTop: 4 }}>{stats.movie}</h1>
        )}
      </header>

      <div className={`verdict ${tie ? '' : stats.winner === 0 ? 'verdict-a' : 'verdict-b'}`}>
        <p className="eyebrow">{tie ? 'Dead heat' : 'Most committed'}</p>
        <div className="verdict-team">{tie ? 'A draw' : TEAM_NAME[stats.winner]}</div>
        <p className="verdict-line">
          {stats.total} sip{stats.total === 1 ? '' : 's'} across the film
        </p>
      </div>

      <section>
        <p className="section-label">By team</p>
        <div className="bar-row bar-row-a">
          <span className="bar-name">Amber</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(stats.a / stats.max) * 100}%` }} />
          </div>
          <span className="bar-value">{stats.a}</span>
        </div>
        <div className="bar-row bar-row-b">
          <span className="bar-name">Teal</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(stats.b / stats.max) * 100}%` }} />
          </div>
          <span className="bar-value">{stats.b}</span>
        </div>
      </section>

      <section>
        <p className="section-label">Standings</p>
        {stats.standings.length > 0 ? (
          <div>
            {stats.standings.map((p, i) => (
              <div key={p.id} className={`standing ${i === 0 && p.sips > 0 ? 'standing-lead' : ''}`}>
                <span className="standing-rank">{i + 1}</span>
                <span className="standing-name">{p.name}</span>
                <span className="standing-count">{p.sips}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-note">Nobody drank. Suspicious.</p>
        )}
      </section>

      <button className="btn btn-primary btn-full" onClick={() => navigate('/')}>
        Another round
      </button>
    </div>
  );
}
