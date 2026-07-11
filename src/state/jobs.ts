import { create } from 'zustand';

/** Живое состояние задачи из WS-событий worker'а (job.progress/done/error). */
export interface LiveJob {
  id: string;
  kind: string;
  status: 'running' | 'done' | 'error' | 'cancelled';
  stage?: string;
  human_ru?: string;
  pct: number;
  result?: unknown;
  error?: { code: string; message_ru: string };
}

interface JobsState {
  connected: boolean;
  jobs: Record<string, LiveJob>;
  /** Подключение к ws://127.0.0.1:<port>/ws с автопереподключением. Идемпотентно. */
  connect: (port: number) => void;
}

const RETRY_MS = 2000;
let socket: WebSocket | null = null;
let connectedPort: number | null = null;

export const useJobs = create<JobsState>((set, get) => ({
  connected: false,
  jobs: {},

  connect: (port) => {
    if (connectedPort === port && socket && socket.readyState <= WebSocket.OPEN) return;
    connectedPort = port;
    socket?.close();

    const open = () => {
      if (connectedPort !== port) return;
      const ws = new WebSocket(`ws://127.0.0.1:${port}/ws`);
      socket = ws;
      ws.onopen = () => set({ connected: true });
      ws.onclose = () => {
        set({ connected: false });
        if (connectedPort === port) setTimeout(open, RETRY_MS);
      };
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(String(event.data));
          const id: string = msg.job_id;
          if (!id) return;
          const prev = get().jobs[id];
          let job: LiveJob;
          if (msg.type === 'job.progress') {
            job = { id, kind: msg.kind, status: 'running', stage: msg.stage,
                    human_ru: msg.human_ru, pct: msg.pct ?? prev?.pct ?? 0 };
          } else if (msg.type === 'job.done') {
            job = { id, kind: msg.kind, status: 'done', pct: 1, result: msg.result };
          } else if (msg.type === 'job.error') {
            job = {
              id, kind: msg.kind,
              status: msg.code === 'E_CANCELLED' ? 'cancelled' : 'error',
              pct: prev?.pct ?? 0,
              error: { code: msg.code, message_ru: msg.message_ru },
            };
          } else {
            return;
          }
          set((s) => ({ jobs: { ...s.jobs, [id]: job } }));
        } catch {
          /* мусорное сообщение — игнорируем */
        }
      };
    };
    open();
  },
}));
