import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface MapState {
  selectedRouteIds: string[];
  // ... other existing state
}

const initialState: MapState = {
  selectedRouteIds: [],
};

const mapSlice = createSlice({
  name: 'map',
  initialState,
  reducers: {
    setSelectedRouteIds(state, action: PayloadAction<string[]>) {
      state.selectedRouteIds = action.payload;
    },
    clearRouteFilter(state) {
      state.selectedRouteIds = [];
    },
    toggleRouteSelection(state, action: PayloadAction<string>) {
      const routeId = action.payload;
      const index = state.selectedRouteIds.indexOf(routeId);
      if (index === -1) {
        state.selectedRouteIds.push(routeId);
      } else {
        state.selectedRouteIds.splice(index, 1);
      }
    },
  },
});

export const { setSelectedRouteIds, clearRouteFilter, toggleRouteSelection } = mapSlice.actions;
export default mapSlice.reducer;