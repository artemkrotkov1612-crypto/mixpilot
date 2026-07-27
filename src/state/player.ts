import { create } from 'zustand';
import { api, mediaUrl, renderUrl } from '../api/client';
import type { PeaksDoc, Track, Variant } from '../api/types';

/** Любой воспроизводимый источник: трек библиотеки или вариант ремикса. */
export interface Playable {
  id: string;
  title: string;
  subtitle: string;
  url: string;
  peaksUrl: string;
  duration: number;
}

export function trackPlayable(track: Track): Playable {
  return {
    id: `track:${track.id}`,
    title: track.title,
    subtitle: track.artist ?? '—',
    url: mediaUrl(track.media_path),
    peaksUrl: `/library/tracks/${track.id}/peaks`,
    duration: track.duration_s,
  };
}

export function variantPlayable(variant: Variant, projectTitle: string): Playable {
  return {
    id: `variant:${variant.id}`,
    title: variant.title_ru,
    subtitle: projectTitle,
    url: renderUrl(variant.render_wav ?? ''),
    peaksUrl: `/variants/${variant.id}/peaks`,
    duration: 0, // придёт из документа пиков
  };
}

interface PlayerState {
  current: Playable | null;
  peaks: number[] | null;
  duration: number;
  playing: boolean;
  /** Играть источник; повторный вызов на том же — пауза/продолжение. */
  play: (item: Playable) => Promise<void>;
  toggle: () => void;
  stop: () => void;
  onFinished: () => void;
}

export const usePlayer = create<PlayerState>((set, get) => ({
  current: null,
  peaks: null,
  duration: 0,
  playing: false,

  play: async (item) => {
    if (get().current?.id === item.id) {
      set({ playing: !get().playing });
      return;
    }
    set({ current: item, peaks: null, duration: item.duration, playing: false });
    try {
      const doc = await api<PeaksDoc>(item.peaksUrl);
      // пики могли прийти уже для другого источника — не затираем
      if (get().current?.id === item.id) {
        set({ peaks: doc.peaks, duration: doc.duration_s, playing: true });
      }
    } catch {
      if (get().current?.id === item.id) set({ playing: true }); // без пиков тоже играем
    }
  },

  toggle: () => set((s) => (s.current ? { playing: !s.playing } : s)),
  stop: () => set({ current: null, peaks: null, playing: false, duration: 0 }),
  onFinished: () => set({ playing: false }),
}));

/** Играет ли сейчас конкретный источник (для подсветки кнопок). */
export function isPlayingId(id: string): boolean {
  const s = usePlayer.getState();
  return s.current?.id === id && s.playing;
}
