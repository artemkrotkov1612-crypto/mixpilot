/** Запись с микрофона и живой уровень громкости для индикатора. */

export interface Recorder {
  stop: () => Promise<Blob>;
  level: () => number;
  cancel: () => void;
}

export class MicrophoneError extends Error {
  constructor(message: string) {
    super(message);
  }
}

/** Человеческое объяснение вместо технической ошибки браузера. */
function explain(err: unknown): string {
  const name = (err as { name?: string })?.name ?? '';
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Доступ к микрофону запрещён — разрешите его в настройках системы';
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return 'Микрофон не найден — подключите его и попробуйте снова';
  }
  if (name === 'NotReadableError') {
    return 'Микрофон занят другой программой — закройте её и попробуйте снова';
  }
  return 'Не удалось включить микрофон';
}

export async function startRecording(): Promise<Recorder> {
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: false, // для пения обработка браузера только мешает
        noiseSuppression: false,
        autoGainControl: false,
      },
    });
  } catch (err) {
    throw new MicrophoneError(explain(err));
  }

  const audioCtx = new AudioContext();
  const source = audioCtx.createMediaStreamSource(stream);
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);
  const buffer = new Float32Array(analyser.fftSize);

  const chunks: BlobPart[] = [];
  const recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => {
    if (e.data.size > 0) chunks.push(e.data);
  };
  recorder.start();

  const cleanup = () => {
    stream.getTracks().forEach((t) => t.stop());
    void audioCtx.close().catch(() => {});
  };

  return {
    level: () => {
      analyser.getFloatTimeDomainData(buffer);
      let sum = 0;
      for (let i = 0; i < buffer.length; i++) sum += buffer[i] * buffer[i];
      return Math.min(1, Math.sqrt(sum / buffer.length) * 4);
    },
    stop: () =>
      new Promise<Blob>((resolve) => {
        recorder.onstop = () => {
          cleanup();
          resolve(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }));
        };
        recorder.stop();
      }),
    cancel: () => {
      try {
        if (recorder.state !== 'inactive') recorder.stop();
      } finally {
        cleanup();
      }
    },
  };
}
