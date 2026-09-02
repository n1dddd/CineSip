const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function createGame(movieTitle = null) {
  const res = await fetch(`${API_BASE}/api/games`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ movie_title: movieTitle }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
  return res.json();
}

export async function joinGame(code, name) {
  const res = await fetch(`${API_BASE}/api/games/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, name }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
  return res.json();
}

export async function getGameState(code) {
  const res = await fetch(`${API_BASE}/api/games/${code}`);
  if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
  return res.json();
}

export async function startGame(gameId) {
  const res = await fetch(`${API_BASE}/api/games/${gameId}/start`, { method: 'POST' });
  if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
  return res.json();
}

export async function logDrink(gameId, playerId, ruleId) {
  const res = await fetch(`${API_BASE}/api/games/${gameId}/drinks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId, rule_id: ruleId }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
  return res.json();
}

export async function searchMovies(query) {
  const res = await fetch(`${API_BASE}/api/movies/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) return [];
  const data = await res.json();
  return (data.results || []).map(m => ({
    id: m.id,
    title: m.title,
    year: m.release_date ? m.release_date.slice(0, 4) : '?',
    poster: m.poster_path ? `https://image.tmdb.org/t/p/w200${m.poster_path}` : '🎬',
  }));
}

export async function addRule(gameId, team, description) {
  const res = await fetch(`${API_BASE}/api/games/${gameId}/rules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game_id: gameId, team, description }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
  return res.json();
}

export default { createGame, joinGame, getGameState, startGame, logDrink, searchMovies, addRule };