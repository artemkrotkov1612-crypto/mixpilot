import { create } from 'zustand';

export type Screen =
  | { name: 'home' }
  | { name: 'library' }
  | { name: 'remix'; projectId?: string; initialTrackId?: string }
  | { name: 'settings' };

interface ScreensState {
  screen: Screen;
  go: (screen: Screen) => void;
}

export const useScreens = create<ScreensState>((set) => ({
  screen: { name: 'home' },
  go: (screen) => set({ screen }),
}));
