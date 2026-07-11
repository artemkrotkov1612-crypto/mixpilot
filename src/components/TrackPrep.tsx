import { useCallback, useEffect, useState } from 'react';
import { ApiError, api } from '../api/client';
import type { Analysis, Job, StartProcessing } from '../api/types';
import { useEngine } from '../state/engine';
import { useJobs } from '../state/jobs';
import { BlockStrip } from './BlockStrip';

type Phase =
  | { name: 'starting' }
  | { name: 'waiting'; jobId: string; humanRu?: string; pct?: number }
  | { name: 'ready'; analysis: Analysis }
  | { name: 'cancelled' }
  | { name: 'error'; message: string };

const POLL_MS = 2500;

/** Подготовка трека: авто-анализ структуры с прогрессом и отменой (M2). */
export function TrackPrep({ trackId }: { trackId: string }) {
  const online = useEngine((s) => s.state.kind === 'online');
  const [phase, setPhase] = useState<Phase>({ name: 'starting' });
  const liveJob = useJobs((s) => (phase.name === 'waiting' ? s.jobs[phase.jobId] : undefined));

  const start = useCallback(async () => {
    setPhase({ name: 'starting' });
    try {
      const res = await api<StartProcessing>(`/analysis/${trackId}`, { method: 'POST', json: {} });
      if (res.status === 'ready' && res.analysis) {
        setPhase({ name: 'ready', analysis: res.analysis });
      } else if (res.job) {
        setPhase({ name: 'waiting', jobId: res.job.id });
      }
    } catch (err) {
      setPhase({ name: 'error', message: err instanceof ApiError ? err.message : 'Что-то пошло не так' });
    }
  }, [trackId]);

  useEffect(() => {
    if (online) void start();
  }, [online, start]);

  const settle = useCallback(
    (status: string, messageRu?: string) => {
      if (status === 'done') {
        api<Analysis>(`/analysis/${trackId}`)
          .then((analysis) => setPhase({ name: 'ready', analysis }))
          .catch(() => setPhase({ name: 'error', message: 'Не удалось получить результат' }));
      } else if (status === 'cancelled') {
        setPhase({ name: 'cancelled' });
      } else if (status === 'error') {
        setPhase({ name: 'error', message: messageRu ?? 'Не получилось разобрать трек' });
      }
    },
    [trackId],
  );

  // Живые события WS.
  useEffect(() => {
    if (phase.name !== 'waiting' || !liveJob) return;
    if (liveJob.status === 'running') {
      setPhase({ name: 'waiting', jobId: phase.jobId, humanRu: liveJob.human_ru, pct: liveJob.pct });
    } else {
      settle(liveJob.status, liveJob.error?.message_ru);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveJob?.status, liveJob?.pct, liveJob?.human_ru]);

  // Медленный REST-фолбэк на случай молчащего WS.
  useEffect(() => {
    if (phase.name !== 'waiting') return;
    const timer = setInterval(async () => {
      try {
        const job = await api<Job>(`/jobs/${phase.jobId}`);
        if (job.status !== 'running' && job.status !== 'queued') settle(job.status);
      } catch {
        /* переспросим в следующий тик */
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [phase.name === 'waiting' ? phase.jobId : null, settle]);

  const cancel = async () => {
    if (phase.name === 'waiting') await api(`/jobs/${phase.jobId}/cancel`, { method: 'POST', json: {} });
  };

  if (phase.name === 'ready') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <BlockStrip sections={phase.analysis.sections} />
        <span className="muted small">
          Мы разобрали песню на {phase.analysis.sections.length} смысловых блоков — ремикс соберётся из них
        </span>
      </div>
    );
  }

  if (phase.name === 'cancelled' || phase.name === 'error') {
    return (
      <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span className="small" style={{ color: phase.name === 'error' ? 'var(--err)' : 'var(--text-2)' }}>
          {phase.name === 'cancelled' ? 'Анализ отменён' : phase.message}
        </span>
        <button className="btn btn-secondary" onClick={() => void start()}>
          Повторить
        </button>
      </div>
    );
  }

  const human = phase.name === 'waiting' ? phase.humanRu ?? 'Слушаем трек…' : 'Готовимся…';
  const pct = phase.name === 'waiting' ? Math.round((phase.pct ?? 0) * 100) : 0;
  return (
    <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
      <div className="spinner" />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span className="small">{human}</span>
        <div className="progress-line">
          <div style={{ width: `${Math.max(pct, 4)}%` }} />
        </div>
      </div>
      {phase.name === 'waiting' && (
        <button className="btn-icon" title="Отменить" onClick={() => void cancel()}>
          ✕
        </button>
      )}
    </div>
  );
}
