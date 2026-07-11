import { create } from 'zustand';
import { setWorkerPort } from '../api/client';
import type { WorkerMeta } from '../types/mixpilot';

export type EngineState =
  | { kind: 'browser' } // vite в обычном браузере: без Electron-моста
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
        if (info.status === 'online' && info.meta && info.port) {
          setWorkerPort(info.port);
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
