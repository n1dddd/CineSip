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
  const [loading, setLoading] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) return setError('Enter your name');
    setLoading(true);
    try {
      const game = await createGame();
      saveName(name.trim());
      setPlayer({ id: null, name: name.trim(), isHost: true });
      navigate(`/lobby/${game.code}`);
    } catch (e) {
      setError('Failed to create game');
    }
    setLoading(false);
  };

  const handleJoin = async () => {
    if (!name.trim()) return setError('Enter your name');
    if (code.length !== 6) return setError('Room code is 6 characters');
    setLoading(true);
    try {
      const player = await joinGame(code.toUpperCase(), name.trim());
      saveName(name.trim());
      setPlayer({ id: player.id, name: name.trim(), isHost: player.is_host });
      navigate(`/lobby/${code.toUpperCase()}`);
    } catch (e) {
      setError(e.message || 'Game not found');
    }
    setLoading(false);
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center gap-10" style={{ paddingTop: '12vh' }}>
      <div>
        <div className="text-6xl mb-2">🍿</div>
        <h1 className="text-5xl font-bold tracking-tight text-gradient">CineSip</h1>
        <p className="text-text-secondary mt-2">Watch movies. Drink responsibly.</p>
      </div>

      <div className="w-full flex flex-col gap-4">
        <div className="flex flex-col gap-2 w-full">
          <label className="text-sm font-semibold text-text-secondary text-left">Your Name</label>
          <input
            className="input"
            placeholder="Enter your drinking alias"
            value={name}
            onChange={e => { setName(e.target.value); setError(''); }}
            maxLength={30}
          />
        </div>

        <button className="btn btn-primary btn-full btn-lg" onClick={handleCreate} disabled={loading}>
          🎬 Create New Game
        </button>

        <div className="divider">or join existing</div>

        <div className="flex flex-col gap-2 w-full">
          <label className="text-sm font-semibold text-text-secondary text-left">Room Code</label>
          <input
            className="input input-code"
            placeholder="ABC123"
            value={code}
            onChange={e => { setCode(e.target.value.toUpperCase().slice(0, 6)); setError(''); }}
            maxLength={6}
          />
        </div>

        <button className="btn btn-secondary btn-full btn-lg" onClick={handleJoin} disabled={loading}>
          🍿 Join Game
        </button>

        {error && <p className="error-msg">{error}</p>}
      </div>
    </div>
  );
}