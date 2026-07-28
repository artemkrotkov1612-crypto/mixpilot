/** Тонкий typed-клиент worker'а. Базовый URL появляется, когда движок online. */

export class ApiError extends Error {
  code: string;
  detail: string;

  constructor(code: string, messageRu: string, detail = '') {
    super(messageRu);
    this.code = code;
    this.detail = detail;
  }
}

let baseUrl = '';

export function setWorkerPort(port: number): void {
  baseUrl = `http://127.0.0.1:${port}`;
}

export function workerReady(): boolean {
  return baseUrl !== '';
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  json?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!baseUrl) throw new ApiError('E_WORKER_DOWN', 'AI-движок ещё запускается');

  let url = baseUrl + path;
  if (options.query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(options.query)) {
      if (value !== undefined && value !== '') params.set(key, String(value));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? (options.json !== undefined ? 'POST' : 'GET'),
      headers: options.json !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: options.json !== undefined ? JSON.stringify(options.json) : undefined,
    });
  } catch {
    throw new ApiError('E_WORKER_DOWN', 'AI-движок не отвечает');
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new ApiError('E_INTERNAL', 'Некорректный ответ движка', text.slice(0, 200));
    }
  }
  if (!response.ok) {
    const err = (data as { error?: { code?: string; message_ru?: string; detail?: string } })?.error;
    throw new ApiError(err?.code ?? 'E_INTERNAL', err?.message_ru ?? 'Внутренняя ошибка', err?.detail ?? '');
  }
  return data as T;
}

/** Отправка сырых байт (запись с микрофона) — тело не JSON. */
export async function postBinary<T>(path: string, body: Blob): Promise<T> {
  if (!baseUrl) throw new ApiError('E_WORKER_DOWN', 'AI-движок ещё запускается');
  let response: Response;
  try {
    response = await fetch(baseUrl + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body,
    });
  } catch {
    throw new ApiError('E_WORKER_DOWN', 'AI-движок не отвечает');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const err = (data as { error?: { code?: string; message_ru?: string } })?.error;
    throw new ApiError(err?.code ?? 'E_INTERNAL', err?.message_ru ?? 'Не удалось обработать запись');
  }
  return data as T;
}

/** URL аудиопотока для плеера (протокол media:// обслуживает Electron main). */
export function mediaUrl(mediaPath: string): string {
  return `media://originals/${mediaPath}`;
}

/** URL рендера варианта: render_wav вида "renders/<gen>/variant_0.wav". */
export function renderUrl(renderWav: string): string {
  return `media://render/${renderWav.replace(/^renders\//, '')}`;
}

/** Обложка варианта. Метка времени — чтобы после перерисовки не показалась старая. */
export function coverUrl(variantId: string, stamp: number | string = ''): string {
  return `${baseUrl}/variants/${variantId}/cover.png${stamp ? `?v=${stamp}` : ''}`;
}
