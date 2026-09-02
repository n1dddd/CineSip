import { create } from 'zustand';

/**
 * Live game state mirrored from the server.
 * Drink totals are derived from server drink_logs at render time, so every
 * device shows identical numbers — nothing authoritative is cached here.
 */
const useGameStore = create((set) => ({
  rules: [],

  setRules: (rules) => set({ rules }),

  reset: () => set({ rules: [] }),
}));

export { useGameStore };
export default useGameStore;
