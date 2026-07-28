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

/** Доустановка компонентов при первом запуске (electron/bootstrap.cjs). */
export interface SetupState {
  active: boolean;
  pct: number;
  text_ru: string;
  error_ru: string | null;
}

export interface WorkerInfo {
  status: 'stopped' | 'starting' | 'online' | 'failed';
  port: number | null;
  meta: WorkerMeta | null;
  setup?: SetupState;
}

declare global {
  interface Window {
    /** Отсутствует, когда UI открыт в обычном браузере (vite dev без Electron). */
    mixpilot?: {
      workerInfo(): Promise<WorkerInfo>;
      pickFiles(): Promise<string[]>;
      showInFolder(targetPath: string): Promise<void>;
      getPathForFile(file: File): string;
      notifyDone(title: string, body: string): Promise<boolean>;
    };
  }
}

export {};
