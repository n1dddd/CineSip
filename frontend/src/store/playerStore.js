import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * Identity + roster.
 * `player` and `name` persist to localStorage so a phone that locks, reloads,
 * or gets backgrounded mid-movie keeps its seat in the game.
 * `players` is server state and is intentionally NOT persisted.
 */
const usePlayerStore = create(
  persist(
    (set) => ({
      player: null,   // { id, name, isHost }
      players: [],    // server roster
      name: '',

      setName: (name) => set({ name }),
      setPlayer: (player) => set({ player }),
      setPlayers: (players) => set({ players }),

      reset: () => set({ player: null, players: [], name: '' }),
    }),
    {
      name: 'cinesip-player',
      partialize: (state) => ({ player: state.player, name: state.name }),
    }
  )
);

export { usePlayerStore };
export default usePlayerStore;
