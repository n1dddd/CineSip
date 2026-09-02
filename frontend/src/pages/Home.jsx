import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import usePlayerStore from '../store/playerStore';
import { createGame, joinGame } from '../services/api';

export default function Home() {
  const navigate = useNavigate();
  const { setName: saveName, setPlayer } = usePlayerStore();
  const [name, setName] = useState(usePlayerStore.getState().name || '');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null); // 'create' | 'join' | null

  const handleCreate = async () => {
    if (!name.trim()) return setError('Enter your name first');
    setBusy('create');
    setError('');
    try {
      const game = await createGame();
      const me = await joinGame(game.code, name.trim());
      saveName(name.trim());
      setPlayer({ id: me.id, name: me.name, isHost: me.is_host });
      navigate(`/lobby/${game.code}`);
    } catch {
      setError('Could not start a game. Try again.');
      setBusy(null);
    }
  };

  const handleJoin = async () => {
    if (!name.trim()) return setError('Enter your name first');
    if (code.length !== 6) return setError('Room codes are 6 characters');
    setBusy('join');
    setError('');
    try {
      const me = await joinGame(code.toUpperCase(), name.trim());
      saveName(name.trim());
      setPlayer({ id: me.id, name: me.name, isHost: me.is_host });
      navigate(`/lobby/${code.toUpperCase()}`);
    } catch (e) {
      setError(e.message?.includes('not found') ? 'No game with that code' : 'Could not join');
      setBusy(null);
    }
  };

  return (
    <div className="flex-1 flex flex-col justify-center" style={{ gap: 40, paddingBottom: 24 }}>
      <header>
        <p className="eyebrow" style={{ marginBottom: 10 }}>Movie night, with stakes</p>
        <h1 className="wordmark">
          CineSip<span className="wordmark-dot">.</span>
        </h1>
        <p style={{ color: 'var(--color-content-muted)', fontSize: 15, marginTop: 12, maxWidth: '34ch' }}>
          Split into teams. Every team gets rules drawn from the film you're
          actually watching.
        </p>
      </header>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div className="field">
          <label className="field-label" htmlFor="name">Your name</label>
          <input
            id="name"
            className="input"
            placeholder="Daniel"
            value={name}
            onChange={(e) => { setName(e.target.value); setError(''); }}
            maxLength={30}
            autoComplete="given-name"
          />
        </div>

        <button
          className="btn btn-primary btn-full"
          onClick={handleCreate}
          disabled={busy !== null}
        >
          {busy === 'create' ? 'Starting…' : 'Start a game'}
        </button>

        <div className="divider-or">or</div>

        <div className="field">
          <label className="field-label" htmlFor="code">Room code</label>
          <input
            id="code"
            className="input input-code"
            placeholder="——————"
            value={code}
            onChange={(e) => { setCode(e.target.value.toUpperCase().slice(0, 6)); setError(''); }}
            maxLength={6}
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
          />
        </div>

        <button
          className="btn btn-secondary btn-full"
          onClick={handleJoin}
          disabled={busy !== null}
        >
          {busy === 'join' ? 'Joining…' : 'Join a game'}
        </button>

        {error && <p className="error-note">{error}</p>}
      </div>
    </div>
  );
}
