import { create } from 'zustand';
import { api } from '../api/client';
import type { PeaksDoc, Track } from '../api/types';

interface PlayerState {
  track: Track | null;
  peaks: number[] | null;
  duration: number;
  playing: boolean;
  /** Играть трек; повторный вызов на том же треке — пауза/продолжение. */
  play: (track: Track) => Promise<void>;
  toggle: () => void;
  stop: () => void;
  onFinished: () => void;
}

export const usePlayer = create<PlayerState>((set, get) => ({
  track: null,
  peaks: null,
  duration: 0,
  playing: false,

  play: async (track) => {
    const current = get().track;
    if (current?.id === track.id) {
      set({ playing: !get().playing });
      return;
    }
    set({ track, peaks: null, duration: track.duration_s, playing: false });
    try {
      const doc = await api<PeaksDoc>(`/library/tracks/${track.id}/peaks`);
      // пики могли прийти уже для другого трека — не затираем
      if (get().track?.id === track.id) {
        set({ peaks: doc.peaks, duration: doc.duration_s, playing: true });
      }
    } catch {
      if (get().track?.id === track.id) set({ playing: true }); // без пиков тоже играем
    }
  },

  toggle: () => set((s) => (s.track ? { playing: !s.playing } : s)),
  stop: () => set({ track: null, peaks: null, playing: false, duration: 0 }),
  onFinished: () => set({ playing: false }),
}));
