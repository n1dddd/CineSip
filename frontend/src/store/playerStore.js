import { create } from 'zustand';

const usePlayerStore = create((set) => ({
  player: null,        // { id, name, isHost }
  players: [],         // [{ id, game_id, name, team, is_host, joined_at }]
  name: '',

  setName: (name) => set({ name }),
  setPlayer: (player) => set({ player }),
  setPlayers: (players) => set({ players }),

  reset: () => set({ player: null, players: [], name: '' }),
}));

export { usePlayerStore };
export default usePlayerStore;