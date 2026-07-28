import { create } from 'zustand';
import { setWorkerPort } from '../api/client';
import type { WorkerMeta } from '../types/mixpilot';
import { useJobs } from './jobs';

export type EngineState =
  | { kind: 'browser' } // vite в обычном браузере: без Electron-моста
  | { kind: 'setup'; pct: number; textRu: string } // первый запуск: ставим компоненты
  | { kind: 'setupFailed'; errorRu: string }
  | { kind: 'starting' }
  | { kind: 'online'; port: number; meta: WorkerMeta }
  | { kind: 'offline' };

interface EngineStore {
  state: EngineState;
  started: boolean;
  start: () => void;
}

const POLL_MS = 2000;

export const useEngine = create<EngineStore>((set, get) => ({
  state: window.mixpilot ? { kind: 'starting' } : { kind: 'browser' },
  started: false,
  start: () => {
    if (get().started) return;
    set({ started: true });
    const bridge = window.mixpilot;
    if (!bridge) return;

    const poll = async () => {
      try {
        const info = await bridge.workerInfo();
        // Доустановка компонентов главнее статуса worker'а: пока она идёт,
        // движка ещё нет, и говорить «недоступен» было бы неправдой.
        if (info.setup?.error_ru) {
          set({ state: { kind: 'setupFailed', errorRu: info.setup.error_ru } });
          return;
        }
        if (info.setup?.active) {
          set({ state: { kind: 'setup', pct: info.setup.pct, textRu: info.setup.text_ru } });
          return;
        }
        if (info.status === 'online' && info.meta && info.port) {
          setWorkerPort(info.port);
          useJobs.getState().connect(info.port);
          set({ state: { kind: 'online', port: info.port, meta: info.meta } });
        } else if (info.status === 'failed') {
          set({ state: { kind: 'offline' } });
        } else {
          set({ state: { kind: 'starting' } });
        }
      } catch {
        set({ state: { kind: 'offline' } });
      }
    };
    void poll();
    setInterval(poll, POLL_MS);
  },
}));
