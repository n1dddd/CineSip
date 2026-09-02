import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import usePlayerStore from '../store/playerStore';
import useGameStore from '../store/gameStore';
import { getGameState, logDrink, finishGame } from '../services/api';

const TEAM_NAME = ['Amber', 'Teal'];

export default function Game() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { player, players, setPlayers } = usePlayerStore();
  const { rules, setRules } = useGameStore();

  const [game, setGame] = useState(null);
  const [logs, setLogs] = useState([]);
  const [callout, setCallout] = useState(null);
  const [ending, setEnding] = useState(false);

  const mine = players.find((p) => p.id === player?.id)?.team ?? 0;
  const theirs = mine === 0 ? 1 : 0;
  const myRules = rules.filter((r) => r.team === mine);
  const theirRules = rules.filter((r) => r.team !== mine);

  // Totals come from server logs so every phone agrees.
  const tally = useMemo(() => {
    const team = new Map(players.map((p) => [p.id, p.team]));
    const t = { 0: 0, 1: 0 };
    for (const l of logs) {
      const side = team.get(l.player_id);
      if (side === 0 || side === 1) t[side] += 1;
    }
    return t;
  }, [logs, players]);

  const refresh = useCallback(async () => {
    try {
      const s = await getGameState(code);
      setGame(s.game);
      setPlayers(s.players || []);
      setRules(s.rules || []);
      setLogs(s.drink_logs || []);
      if (s.game?.status === 'finished') navigate(`/results/${code}`, { replace: true });
    } catch {
      /* transient */
    }
  }, [code, navigate, setPlayers, setRules]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2500);
    return () => clearInterval(t);
  }, [refresh]);

  const sip = async (rule) => {
    if (!player?.id || !game) return;
    setCallout({ team: rule.team, text: rule.description });
    setTimeout(() => setCallout(null), 2800);
    try {
      await logDrink(game.id, player.id, rule.id);
      refresh();
    } catch {
      /* the call-out already fired; next poll reconciles */
    }
  };

  const end = async () => {
    setEnding(true);
    try {
      await finishGame(game.id);
      navigate(`/results/${code}`, { replace: true });
    } catch {
      setEnding(false);
    }
  };

  if (!game) return <div className="loading-note">Loading…</div>;

  return (
    <div className="flex-1 flex flex-col" style={{ gap: 22 }}>
      {callout && (
        <div className={`callout ${callout.team === 0 ? 'callout-a' : 'callout-b'}`}>
          <div className="callout-label">{TEAM_NAME[callout.team]} drinks</div>
          <div className="callout-text">{callout.text}</div>
        </div>
      )}

      <header style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ minWidth: 0 }}>
          <p className="eyebrow">Now playing</p>
          <h1 className="now-playing-title" style={{ marginTop: 3 }}>{game.movie_title}</h1>
        </div>
        <button className="btn btn-ghost" style={{ flexShrink: 0 }} onClick={() => navigate(`/lobby/${code}`)}>
          Lobby
        </button>
      </header>

      {/* Your rules — the working surface */}
      <section className={`team ${mine === 0 ? 'team-a' : 'team-b'}`}>
        <div className="team-head">
          <div>
            <div className="team-name">{TEAM_NAME[mine]} · your team</div>
          </div>
          <div className="team-tally">
            {tally[mine]}<span className="team-tally-unit">sips</span>
          </div>
        </div>
        <div className="rule-list">
          {myRules.map((r) => (
            <button key={r.id} className="rule-row" onClick={() => sip(r)}>
              <span className="rule-text">{r.description}</span>
              <span className="rule-count">{r.trigger_count || 0}</span>
              <span className="sip" aria-hidden="true">Sip</span>
            </button>
          ))}
          {myRules.length === 0 && <p className="empty-note">No rules assigned</p>}
        </div>
      </section>

      {/* Opposition — visible, deliberately quieter */}
      <section className={`team team-passive ${theirs === 0 ? 'team-a' : 'team-b'}`}>
        <div className="team-head">
          <div className="team-name">{TEAM_NAME[theirs]}</div>
          <div className="team-tally">
            {tally[theirs]}<span className="team-tally-unit">sips</span>
          </div>
        </div>
        <div className="rule-list">
          {theirRules.map((r) => (
            <div key={r.id} className="rule-row rule-row-passive">
              <span className="rule-text">{r.description}</span>
              <span className="rule-count">{r.trigger_count || 0}</span>
            </div>
          ))}
          {theirRules.length === 0 && <p className="empty-note">No rules assigned</p>}
        </div>
      </section>

      <button className="btn btn-secondary btn-full" onClick={end} disabled={ending}>
        {ending ? 'Ending…' : 'End the night'}
      </button>
    </div>
  );
}
