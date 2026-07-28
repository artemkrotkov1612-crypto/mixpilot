import { useCallback, useEffect, useState } from 'react';
import type { Variant } from '../api/types';
import { ArtworkPanel } from '../components/ArtworkPanel';
import { EditPanel } from '../components/EditPanel';
import { VariantCard } from '../components/VariantCard';
import { useJobWatch } from '../lib/useJobWatch';
import { useEngine } from '../state/engine';
import { useGeneration } from '../state/generation';
import { usePlayer } from '../state/player';
import { useProjects } from '../state/projects';
import { useScreens } from '../state/screens';
import { toast } from '../state/toasts';

export function ResultsScreen({ generationId }: { generationId: string }) {
  const go = useScreens((s) => s.go);
  const online = useEngine((s) => s.state.kind === 'online');
  const { generation, jobId, load, refresh, setJob } = useGeneration();
  const refreshRecent = useProjects((s) => s.refreshRecent);
  const stopPlayer = usePlayer((s) => s.stop);
  const [editing, setEditing] = useState<Variant | null>(null);
  const [artwork, setArtwork] = useState<Variant | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    if (online) void load(generationId);
  }, [online, generationId, load]);

  const onSettle = useCallback(
    async ({ status, messageRu }: { status: string; messageRu?: string }) => {
      setJob(null);
      if (status === 'done') {
        setFailed(null);
        await refresh();
        void refreshRecent();
      } else if (status === 'cancelled') {
        toast('Отменено. Черновик сохранён');
      } else {
        setFailed(messageRu ?? 'Не получилось собрать вариант');
      }
    },
    [refresh, refreshRecent, setJob],
  );

  const progress = useJobWatch(jobId, onSettle);

  const cancel = async () => {
    if (!jobId) return;
    const { api } = await import('../api/client');
    await api(`/jobs/${jobId}/cancel`, { method: 'POST', json: {} }).catch(() => {});
  };

  const variants = generation?.variants ?? [];
  const projectTitle = generation?.plan?.style_name ?? 'Ремикс';
  const working = jobId !== null;

  return (
    <div className="screen-inner fade-in">
      <button
        className="btn-ghost"
        style={{ alignSelf: 'flex-start' }}
        onClick={() => {
          stopPlayer();
          go({ name: 'home' });
        }}
      >
        ‹ Главная
      </button>

      <header>
        <h1 className="h-display">{working && variants.length === 0 ? 'Готовим варианты…' : 'Готово!'}</h1>
        <p className="muted">
          {generation?.plan
            ? `Стиль: ${generation.plan.style_name}${
                generation.plan.chips?.length ? ` · ${generation.plan.chips.join(', ')}` : ''
              }`
            : 'Собираем ремикс из вашей песни'}
        </p>
      </header>

      {working && (
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div className="spinner" />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span className="small">{progress.humanRu}</span>
            <div className="progress-line">
              <div style={{ width: `${Math.max(Math.round(progress.pct * 100), 4)}%` }} />
            </div>
            <span className="muted small">Можно свернуть — мы сообщим, когда будет готово</span>
          </div>
          <button className="btn-icon" title="Отменить" onClick={() => void cancel()}>
            ✕
          </button>
        </div>
      )}

      {failed && (
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="small" style={{ color: 'var(--err)', flex: 1 }}>
            {failed}
          </span>
          <button className="btn btn-secondary" onClick={() => void refresh()}>
            Обновить
          </button>
        </div>
      )}

      {editing && (
        <EditPanel
          variant={editing}
          onClose={() => setEditing(null)}
          onStarted={(id) => {
            setEditing(null);
            setJob(id);
          }}
        />
      )}

      {artwork && (
        <ArtworkPanel
          variant={artwork}
          onClose={() => {
            setArtwork(null);
            void refresh(); // подхватываем новое название и обложку на карточке
          }}
        />
      )}

      <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {variants.map((v) => (
          <VariantCard
            key={v.id}
            variant={v}
            projectTitle={projectTitle}
            onEdit={setEditing}
            onArtwork={setArtwork}
          />
        ))}
      </section>

      {variants.length > 0 && !working && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button className="btn btn-secondary" onClick={() => go({ name: 'home' })}>
            Сделать ещё один ремикс
          </button>
        </div>
      )}
    </div>
  );
}
