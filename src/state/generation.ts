import { create } from 'zustand';
import { ApiError, api } from '../api/client';
import type { Generation, GenerationParams, Job } from '../api/types';
import { toast } from './toasts';

interface StartResponse {
  generation_id: string;
  job: Job;
}

interface GenerationState {
  generation: Generation | null;
  /** id активной задачи: генерации или правки */
  jobId: string | null;
  loading: boolean;
  start: (projectId: string, request: GenerationParams) => Promise<string | null>;
  load: (generationId: string) => Promise<void>;
  refresh: () => Promise<void>;
  /** Правка варианта чипами/операциями — возвращает id задачи. */
  edit: (variantId: string, chips: string[], text?: string) => Promise<string | null>;
  /** 0 — снять оценку (и убрать её из профиля вкуса). */
  rate: (variantId: string, rating: 1 | -1 | 0) => Promise<void>;
  exportVariant: (variantId: string, format: 'mp3' | 'wav' | 'flac') => Promise<void>;
  setJob: (jobId: string | null) => void;
  clear: () => void;
}

export const useGeneration = create<GenerationState>((set, get) => ({
  generation: null,
  jobId: null,
  loading: false,

  start: async (projectId, request) => {
    try {
      const res = await api<StartResponse>('/generations', {
        json: { project_id: projectId, request },
      });
      set({ jobId: res.job.id, generation: null });
      await get().load(res.generation_id);
      return res.generation_id;
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Не удалось запустить генерацию', 'err');
      return null;
    }
  },

  load: async (generationId) => {
    set({ loading: true });
    try {
      const gen = await api<Generation>(`/generations/${generationId}`);
      set({ generation: gen });
    } finally {
      set({ loading: false });
    }
  },

  refresh: async () => {
    const id = get().generation?.id;
    if (id) await get().load(id);
  },

  edit: async (variantId, chips, text) => {
    try {
      const res = await api<{ job: Job }>(`/variants/${variantId}/edit`, {
        json: { chips, text: text || undefined },
      });
      set({ jobId: res.job.id });
      return res.job.id;
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Не удалось применить изменения', 'err');
      return null;
    }
  },

  rate: async (variantId, rating) => {
    try {
      await api(`/variants/${variantId}/feedback`, { json: { rating } });
      await get().refresh();
      toast(rating > 0 ? 'Учтём! MixPilot запоминает ваш вкус' : 'Понял, такое реже', 'ok');
    } catch {
      toast('Не удалось сохранить оценку', 'err');
    }
  },

  exportVariant: async (variantId, format) => {
    try {
      const res = await api<{ path: string }>(`/variants/${variantId}/export`, { json: { format } });
      toast(`Сохранено: ${res.path.split(/[\\/]/).pop()}`, 'ok');
      if (window.mixpilot) void window.mixpilot.showInFolder(res.path);
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Не удалось сохранить файл', 'err');
    }
  },

  setJob: (jobId) => set({ jobId }),
  clear: () => set({ generation: null, jobId: null }),
}));
