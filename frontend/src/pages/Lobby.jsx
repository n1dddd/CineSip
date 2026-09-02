import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import usePlayerStore from '../store/playerStore';
import useGameStore from '../store/gameStore';
import { getGameState, startGame, searchMovies, selectMovie } from '../services/api';

export default function Lobby() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { player, players, setPlayers } = usePlayerStore();
  const { rules, setRules } = useGameStore();
  const isHost = player?.isHost || false;

  const [game, setGame] = useState(null);
  const [copied, setCopied] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState('');
  const debounce = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const s = await getGameState(code);
      setGame(s.game);
      setPlayers(s.players || []);
      setRules(s.rules || []);
      if (s.game?.status === 'active') navigate(`/game/${code}`, { replace: true });
    } catch {
      /* transient poll failure — next tick retries */
    }
  }, [code, navigate, setPlayers, setRules]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    if (!isHost) return;
    if (query.trim().length < 2) { setResults([]); return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      setSearching(true);
      try {
        setResults((await searchMovies(query.trim())).slice(0, 6));
      } catch {
        setError('Search is unavailable right now');
      }
      setSearching(false);
    }, 350);
    return () => clearTimeout(debounce.current);
  }, [query, isHost]);

  const pick = async (movie) => {
    setWriting(true);
    setError('');
    setResults([]);
    setQuery('');
    try {
      await selectMovie(game.id, movie.id, movie.title);
      await refresh();
    } catch {
      setError('Could not write rules for that title. Try another.');
    }
    setWriting(false);
  };

  const copy = () => {
    navigator.clipboard?.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const begin = async () => {
    try {
      await startGame(game.id);
      navigate(`/game/${code}`, { replace: true });
    } catch {
      setError('Could not start the game');
    }
  };

  if (!game) return <div className="loading-note">Loading lobby…</div>;

  const teamA = players.filter((p) => p.team === 0);
  const teamB = players.filter((p) => p.team === 1);
  const hasMovie = Boolean(game.movie_title);
  const ready = players.length >= 2 && rules.length > 0;

  return (
    <div className="flex-1 flex flex-col" style={{ gap: 26 }}>
      <button className="btn btn-ghost" onClick={() => navigate('/')}>← Leave</button>

      <div className="ticket" onClick={copy}>
        <p className="eyebrow">Room code</p>
        <code className="ticket-code">{code}</code>
        <p className="ticket-hint">{copied ? 'Copied to clipboard' : 'Tap to copy · share with the room'}</p>
        <div className="ticket-perf"><span>Admit {players.length}</span></div>
      </div>

      {/* Feature */}
      <section>
        <p className="section-label">Tonight's feature</p>

        {hasMovie ? (
          <div className="now-playing">
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="now-playing-title">{game.movie_title}</div>
              <div className="now-playing-meta">
                {writing
                  ? 'Writing rules…'
                  : rules.length > 0
                    ? `${rules.length} rules · ${rules.length / 2} per team`
                    : 'No rules yet'}
              </div>
            </div>
            {writing && <div className="pulse-dot" style={{ marginTop: 7 }} />}
          </div>
        ) : !isHost ? (
          <p className="empty-note">Waiting for the host to choose a film…</p>
        ) : null}

        {isHost && !writing && (
          <div style={{ marginTop: hasMovie ? 12 : 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <input
              className="input"
              placeholder={hasMovie ? 'Change the film…' : 'Search a film or series'}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoComplete="off"
            />
            {searching && <p className="empty-note" style={{ padding: '4px 0' }}>Searching…</p>}
            {results.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {results.map((m) => (
                  <button key={m.id} className="result" onClick={() => pick(m)}>
                    {m.poster?.startsWith('http')
                      ? <img className="result-poster" src={m.poster} alt="" loading="lazy" />
                      : <div className="result-poster">◍</div>}
                    <div style={{ minWidth: 0 }}>
                      <div className="result-title">{m.title}</div>
                      <div className="result-year">{m.year}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Teams */}
      <section>
        <p className="section-label">Teams</p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div className="team team-a" style={{ padding: '13px 15px' }}>
            <div className="team-name">Amber</div>
            <div className="team-tally" style={{ marginTop: 4 }}>
              {teamA.length}<span className="team-tally-unit">player{teamA.length === 1 ? '' : 's'}</span>
            </div>
          </div>
          <div className="team team-b" style={{ padding: '13px 15px' }}>
            <div className="team-name">Teal</div>
            <div className="team-tally" style={{ marginTop: 4 }}>
              {teamB.length}<span className="team-tally-unit">player{teamB.length === 1 ? '' : 's'}</span>
            </div>
          </div>
        </div>
      </section>

      {/* Players */}
      <section>
        <p className="section-label">In the room</p>
        {players.length > 0 ? (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 7 }}>
            {players.map((p) => (
              <div key={p.id} className={`player ${p.team === 0 ? 'player-a' : 'player-b'}`}>
                <div className="player-mark">{p.name[0].toUpperCase()}</div>
                <span className="player-name">{p.name}</span>
                {p.is_host && <span className="player-host">Host</span>}
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-note">Nobody here yet</p>
        )}
      </section>

      {error && <p className="error-note">{error}</p>}

      {isHost && (
        <button className="btn btn-primary btn-full" onClick={begin} disabled={!ready || writing}>
          {players.length < 2
            ? 'Waiting for one more player'
            : rules.length === 0
              ? 'Choose a film first'
              : 'Begin'}
        </button>
      )}
    </div>
  );
}
