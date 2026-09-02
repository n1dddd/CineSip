import { create } from 'zustand';

const useGameStore = create((set, get) => ({
  rules: [],           // [{ id, game_id, team, description, trigger_count }]
  drinkCounts: {},     // { teamIndex: count }
  playerDrinks: {},    // { playerId: count }

  setRules: (rules) => set({ rules }),

  logDrink: (playerId, teamIndex) => {
    set(state => ({
      drinkCounts: {
        ...state.drinkCounts,
        [teamIndex]: (state.drinkCounts[teamIndex] || 0) + 1,
      },
      playerDrinks: {
        ...state.playerDrinks,
        [playerId]: (state.playerDrinks[playerId] || 0) + 1,
      },
    }));
  },

  reset: () => set({ rules: [], drinkCounts: {}, playerDrinks: {} }),
}));

export { useGameStore };
export default useGameStore;