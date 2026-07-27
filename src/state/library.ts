import { create } from 'zustand';
import { api } from '../api/client';
import type { ImportedTrack, Track } from '../api/types';
import { toast } from './toasts';
import { usePlayer } from './player';

const ALLOWED_EXTS = ['mp3', 'wav', 'flac', 'm4a', 'aac', 'ogg', 'opus', 'wma', 'aiff', 'aif'];

export function isAudioPath(p: string): boolean {
  const ext = p.split('.').pop()?.toLowerCase() ?? '';
  return ALLOWED_EXTS.includes(ext);
}

export type LibrarySort = 'added' | 'title' | 'duration';

interface ImportProgress {
  active: boolean;
  done: number;
  total: number;
  current: string;
}

interface LibraryState {
  tracks: Track[];
  total: number;
  query: string;
  sort: LibrarySort;
  favOnly: boolean;
  loading: boolean;
  importing: ImportProgress;
  refresh: () => Promise<void>;
  setQuery: (q: string) => void;
  setSort: (s: LibrarySort) => void;
  setFavOnly: (v: boolean) => void;
  /** Импорт путей; возвращает успешно добавленные (включая дубликаты). */
  importFiles: (paths: string[]) => Promise<Track[]>;
  remove: (trackId: string) => Promise<void>;
  toggleFavorite: (track: Track) => Promise<void>;
}

export const useLibrary = create<LibraryState>((set, get) => ({
  tracks: [],
  total: 0,
  query: '',
  sort: 'added',
  favOnly: false,
  loading: false,
  importing: { active: false, done: 0, total: 0, current: '' },

  refresh: async () => {
    const { query, sort, favOnly } = get();
    set({ loading: true });
    try {
      const res = await api<{ tracks: Track[]; total: number }>('/library/tracks', {
        query: { q: query, sort, favorite: favOnly || undefined },
      });
      set({ tracks: res.tracks, total: res.total });
    } finally {
      set({ loading: false });
    }
  },

  setQuery: (query) => {
    set({ query });
    void get().refresh();
  },
  setSort: (sort) => {
    set({ sort });
    void get().refresh();
  },
  setFavOnly: (favOnly) => {
    set({ favOnly });
    void get().refresh();
  },

  importFiles: async (paths) => {
    const audio = paths.filter(isAudioPath);
    const skippedNonAudio = paths.length - audio.length;
    if (audio.length === 0) {
      if (skippedNonAudio > 0) toast('Это не похоже на аудиофайлы', 'err');
      return [];
    }
    set({ importing: { active: true, done: 0, total: audio.length, current: '' } });
    const added: Track[] = [];
    let duplicates = 0;
    let errors = 0;
    for (const [index, p] of audio.entries()) {
      const name = p.split(/[\\/]/).pop() ?? p;
      set({ importing: { active: true, done: index, total: audio.length, current: name } });
      try {
        const track = await api<ImportedTrack>('/library/import', { json: { path: p } });
        if (track.duplicate) duplicates += 1;
        added.push(track);
      } catch {
        errors += 1;
      }
    }
    set({ importing: { active: false, done: 0, total: 0, current: '' } });
    await get().refresh();

    const parts: string[] = [];
    const fresh = added.length - duplicates;
    if (fresh > 0) parts.push(`добавлено: ${fresh}`);
    if (duplicates > 0) parts.push(`уже в библиотеке: ${duplicates}`);
    if (errors > 0) parts.push(`не прочитано: ${errors}`);
    if (skippedNonAudio > 0) parts.push(`не аудио: ${skippedNonAudio}`);
    if (parts.length > 0) toast(`Импорт — ${parts.join(', ')}`, errors > 0 ? 'err' : 'ok');
    return added;
  },

  remove: async (trackId) => {
    await api(`/library/tracks/${trackId}`, { method: 'DELETE' });
    const player = usePlayer.getState();
    if (player.current?.id === `track:${trackId}`) player.stop();
    await get().refresh();
    toast('Удалено из библиотеки. Исходный файл на диске не тронут', 'ok');
  },

  toggleFavorite: async (track) => {
    await api(`/library/tracks/${track.id}`, {
      method: 'PATCH',
      json: { is_favorite: track.is_favorite === 0 },
    });
    await get().refresh();
  },
}));
