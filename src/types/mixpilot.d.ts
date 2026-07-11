/** Поверхность preload-моста (electron/preload.cjs). */
export interface WorkerMeta {
  name: string;
  version: string;
  python: string;
  pid: number;
  uptime_s: number;
  gpu: string | null;
  ffmpeg?: boolean;
  data_dir?: string;
}

export interface WorkerInfo {
  status: 'stopped' | 'starting' | 'online' | 'failed';
  port: number | null;
  meta: WorkerMeta | null;
}

declare global {
  interface Window {
    /** Отсутствует, когда UI открыт в обычном браузере (vite dev без Electron). */
    mixpilot?: {
      workerInfo(): Promise<WorkerInfo>;
      pickFiles(): Promise<string[]>;
      showInFolder(targetPath: string): Promise<void>;
      getPathForFile(file: File): string;
    };
  }
}

export {};
