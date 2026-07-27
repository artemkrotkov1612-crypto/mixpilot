import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Job } from '../api/types';
import { useJobs } from '../state/jobs';

export interface JobProgress {
  humanRu: string;
  pct: number;
}

type Settled = { status: 'done' | 'error' | 'cancelled'; messageRu?: string };

const POLL_MS = 2500;

/**
 * Следит за задачей: WS-события + медленный REST-фолбэк.
 * onSettle вызывается один раз на завершение (done/error/cancelled).
 */
export function useJobWatch(jobId: string | null, onSettle: (r: Settled) => void): JobProgress {
  const liveJob = useJobs((s) => (jobId ? s.jobs[jobId] : undefined));
  const [progress, setProgress] = useState<JobProgress>({ humanRu: 'Готовимся…', pct: 0 });

  const settle = useCallback(
    (status: Settled['status'], messageRu?: string) => onSettle({ status, messageRu }),
    [onSettle],
  );

  useEffect(() => {
    setProgress({ humanRu: 'Готовимся…', pct: 0 });
  }, [jobId]);

  // Живые события WS.
  useEffect(() => {
    if (!jobId || !liveJob) return;
    if (liveJob.status === 'running') {
      setProgress({ humanRu: liveJob.human_ru ?? 'Обрабатываем…', pct: liveJob.pct });
    } else {
      settle(liveJob.status, liveJob.error?.message_ru);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, liveJob?.status, liveJob?.pct, liveJob?.human_ru]);

  // REST-фолбэк на случай молчащего WS.
  useEffect(() => {
    if (!jobId) return;
    const timer = setInterval(async () => {
      try {
        const job = await api<Job>(`/jobs/${jobId}`);
        if (job.status === 'running') {
          setProgress((p) => ({ humanRu: p.humanRu, pct: Math.max(p.pct, job.progress) }));
        } else if (job.status !== 'queued') {
          settle(job.status);
        }
      } catch {
        /* переспросим в следующий тик */
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [jobId, settle]);

  return progress;
}
