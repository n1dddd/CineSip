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
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const debounceRef = useRef(null);

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
  }, [code, navigate, setPlayers, setRules]);

  useEffect(() => {
    refresh();
    const i = setInterval(refresh, 2000);
    return () => clearInterval(i);
  }, [refresh]);

  // Debounced TMDB search (host only)
  useEffect(() => {
    if (!isHost) return;
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        setResults((await searchMovies(query.trim())).slice(0, 6));
      } catch {
        setError('Movie search unavailable');
      }
      setSearching(false);
    }, 350);
    return () => clearTimeout(debounceRef.current);
  }, [query, isHost]);

  const handlePickMovie = async (movie) => {
    setGenerating(true);
    setError('');
    setResults([]);
    setQuery('');
    try {
      await selectMovie(game.id, movie.id, movie.title);
      await refresh();
    } catch (e) {
      setError('Could not generate rules. Try another title.');
    }
    setGenerating(false);
  };

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
      setError('Could not start the game');
    }
  };

  if (!game) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="loading-spinner">Loading lobby...</div>
      </div>
    );
  }

  const teamA = players.filter((p) => p.team === 0);
  const teamB = players.filter((p) => p.team === 1);
  const hasMovie = Boolean(game.movie_title);
  const hasRules = rules.length > 0;
  const canStart = players.length >= 2 && hasRules;

  return (
    <div className="flex-1 flex flex-col gap-6">
      <button className="btn-back" onClick={() => navigate('/')}>← Back</button>

      <div className="text-center py-4">
        <h3 className="section-title">Room Code</h3>
        <code
          className="block font-mono text-3xl tracking-[0.3em] text-cyan-500 select-all cursor-pointer"
          onClick={copyCode}
        >
          {code}
        </code>
        <p className="text-xs text-text-muted mt-2">
          {copied ? '✓ Copied!' : 'Tap to copy — share with friends'}
        </p>
      </div>

      {/* Movie selection */}
      <div>
        <h3 className="section-title">Movie</h3>

        {hasMovie ? (
          <div className="card flex items-center gap-3">
            <span className="text-2xl">🎬</span>
            <div className="flex-1 min-w-0">
              <div className="font-semibold truncate">{game.movie_title}</div>
              <div className="text-xs text-text-muted">
                {generating
                  ? 'Generating rules…'
                  : hasRules
                    ? `${rules.length} rules ready`
                    : 'No rules yet'}
              </div>
            </div>
          </div>
        ) : isHost ? (
          <p className="text-xs text-text-muted mb-2">
            Search a movie or show — rules are generated from its real plot.
          </p>
        ) : (
          <p className="empty-state">Waiting for the host to pick a movie…</p>
        )}

        {isHost && !generating && (
          <>
            <input
              className="input mt-2"
              placeholder={hasMovie ? 'Change movie…' : 'Search a movie or show'}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {searching && <p className="text-xs text-text-muted mt-2">Searching…</p>}
            {results.length > 0 && (
              <div className="flex flex-col gap-2 mt-2">
                {results.map((m) => (
                  <button
                    key={m.id}
                    className="movie-result text-left"
                    onClick={() => handlePickMovie(m)}
                  >
                    <div className="text-xl">🎞️</div>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm truncate">{m.title}</div>
                      <div className="text-xs text-text-muted">{m.year}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        {generating && (
          <div className="loading-spinner">🍿 Writing your rules…</div>
        )}
      </div>

      {/* Teams */}
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

      {/* Players */}
      <div>
        <h3 className="section-title">Players ({players.length})</h3>
        {players.length > 0 ? (
          <div className="grid grid-cols-2 gap-2">
            {players.map((p) => (
              <div
                key={p.id}
                className={`player-badge ${p.team === 0 ? 'team-a' : 'team-b'}`}
              >
                <div className="avatar">{p.name[0].toUpperCase()}</div>
                <span className="flex-1 font-medium truncate">{p.name}</span>
                {p.is_host && <span>👑</span>}
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-state">Waiting for players…</p>
        )}
      </div>

      {error && <p className="error-msg">{error}</p>}

      {isHost && (
        <button
          className="btn btn-primary btn-full btn-lg"
          onClick={handleStart}
          disabled={!canStart || generating}
        >
          {players.length < 2
            ? 'Need at least 2 players'
            : !hasRules
              ? 'Pick a movie first'
              : '🍻 Start the Game!'}
        </button>
      )}
    </div>
  );
}
