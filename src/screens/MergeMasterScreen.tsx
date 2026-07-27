import { useEffect, useRef, useState } from 'react';
import type { Project, Track } from '../api/types';
import { DropZone } from '../components/DropZone';
import { formatDuration } from '../lib/format';
import { useEngine } from '../state/engine';
import { useGeneration } from '../state/generation';
import { useLibrary } from '../state/library';
import { trackPlayable, usePlayer } from '../state/player';
import {
  attachTrack,
  createProject,
  detachTrack,
  loadProject,
  saveProject,
  useProjects,
} from '../state/projects';
import { useScreens } from '../state/screens';
import { toast } from '../state/toasts';

const STRATEGIES = [
  { slug: 'auto', label: '✨ AI сам решит', hint: 'Подберём способ по количеству и характеру песен' },
  { slug: 'vocal_instr', label: 'Вокал одной + музыка другой', hint: 'Классический mashup' },
  { slug: 'smooth', label: 'Плавное соединение', hint: 'Песни переходят одна в другую' },
  { slug: 'club', label: 'Клубный mashup', hint: 'Припевы чередуются с резкими переходами' },
  { slug: 'best_parts', label: 'Лучшие моменты', hint: 'Самое сильное из каждой песни' },
] as const;

const MANY_TRACKS = 4;
const SAVE_DEBOUNCE_MS = 600;

export function MergeMasterScreen({ projectId }: { projectId?: string }) {
  const go = useScreens((s) => s.go);
  const engine = useEngine((s) => s.state);
  const importFiles = useLibrary((s) => s.importFiles);
  const refreshRecent = useProjects((s) => s.refreshRecent);
  const startGeneration = useGeneration((s) => s.start);
  const { play, current, playing } = usePlayer();

  const [pid, setPid] = useState<string | null>(projectId ?? null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [strategy, setStrategy] = useState<string>('auto');
  const [vocalFrom, setVocalFrom] = useState(0);
  const [musicFrom, setMusicFrom] = useState(1);
  const [quality, setQuality] = useState<'fast' | 'max'>('fast');
  const [title, setTitle] = useState('Соединение песен');
  const [starting, setStarting] = useState(false);
  const [loading, setLoading] = useState(Boolean(projectId));
  const saveTimer = useRef<number | null>(null);

  useEffect(() => {
    if (engine.kind !== 'online' || !projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const p = await loadProject(projectId);
        if (cancelled) return;
        setTitle(p.title);
        setTracks(p.tracks.filter((t) => t.role === 'source'));
        const params = p.params as { strategy?: string; quality?: 'fast' | 'max' };
        if (params.strategy) setStrategy(params.strategy);
        if (params.quality) setQuality(params.quality);
      } catch {
        toast('Не удалось открыть проект', 'err');
        go({ name: 'home' });
      } finally {
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine.kind, projectId]);

  const ensureProject = async (): Promise<string> => {
    if (pid) return pid;
    const p: Project = await createProject('merge');
    setPid(p.id);
    void refreshRecent();
    return p.id;
  };

  const scheduleSave = (next: { strategy?: string; quality?: 'fast' | 'max'; title?: string }) => {
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(async () => {
      try {
        const id = await ensureProject();
        await saveProject(id, {
          title: next.title ?? title,
          params: { strategy: next.strategy ?? strategy, quality: next.quality ?? quality },
        });
      } catch {
        /* черновик сохранится при следующем действии */
      }
    }, SAVE_DEBOUNCE_MS);
  };

  const addFiles = async (paths: string[]) => {
    const added = await importFiles(paths);
    if (added.length === 0) return;
    const id = await ensureProject();
    const next = [...tracks];
    for (const track of added) {
      if (next.some((t) => t.id === track.id)) continue;
      await attachTrack(id, track.id);
      next.push(track);
    }
    setTracks(next);
    scheduleSave({});
  };

  const removeTrack = async (trackId: string) => {
    if (!pid) return;
    await detachTrack(pid, trackId);
    const next = tracks.filter((t) => t.id !== trackId);
    setTracks(next);
    if (vocalFrom >= next.length) setVocalFrom(0);
    if (musicFrom >= next.length) setMusicFrom(Math.max(next.length - 1, 0));
  };

  const merge = async () => {
    if (tracks.length < 2) {
      toast('Добавьте хотя бы две песни');
      return;
    }
    setStarting(true);
    try {
      const id = await ensureProject();
      await saveProject(id, { title, params: { strategy, quality } });
      const generationId = await startGeneration(id, {
        strategy,
        quality,
        vocal_from: vocalFrom,
        music_from: musicFrom,
      });
      if (generationId) go({ name: 'results', generationId });
    } finally {
      setStarting(false);
    }
  };

  if (loading) {
    return (
      <div className="splash">
        <div className="spinner" />
        <div className="muted">Открываем проект…</div>
      </div>
    );
  }

  const estimate = Math.max(2, Math.round(tracks.length * (quality === 'fast' ? 1.5 : 4)));

  return (
    <div className="screen-inner fade-in" style={{ maxWidth: 860 }}>
      <button className="btn-ghost" style={{ alignSelf: 'flex-start' }} onClick={() => go({ name: 'home' })}>
        ‹ Главная
      </button>

      <header style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <input
          className="input h1"
          style={{ background: 'transparent', border: 'none', padding: 0, fontFamily: 'var(--font-display)' }}
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            scheduleSave({ title: e.target.value });
          }}
        />
      </header>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 className="h2">Песни {tracks.length > 0 && <span className="muted small">({tracks.length})</span>}</h2>
        {tracks.map((t, i) => (
          <div key={t.id} className="track-row" style={{ background: 'var(--surface-1)' }}>
            <button
              className={`play-btn ${current?.id === `track:${t.id}` && playing ? 'playing' : ''}`}
              onClick={() => void play(trackPlayable(t))}
            >
              {current?.id === `track:${t.id}` && playing ? '⏸' : '▶'}
            </button>
            <div className="meta">
              <div className="name">
                {i + 1}. {t.title}
              </div>
              <div className="muted small">{t.artist ?? '—'}</div>
            </div>
            <div className="muted small tabular">{formatDuration(t.duration_s)}</div>
            <button className="btn-icon" title="Убрать" onClick={() => void removeTrack(t.id)}>
              ✕
            </button>
          </div>
        ))}
        <DropZone compact={tracks.length > 0} onPaths={(p) => void addFiles(p)}>
          <div style={{ fontWeight: 600 }}>
            {tracks.length === 0 ? 'Перетащите две песни или больше' : 'Добавить ещё песню'}
          </div>
          {tracks.length === 0 && <div className="small" style={{ marginTop: 4 }}>MP3 · WAV · FLAC · M4A</div>}
        </DropZone>
        {tracks.length >= MANY_TRACKS && (
          <div className="card small" style={{ borderColor: 'rgba(255,182,72,.4)' }}>
            Чем больше песен, тем дольше обработка: примерно {estimate} минут
          </div>
        )}
      </section>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 className="h2">Как соединить?</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {STRATEGIES.map((s) => (
            <button
              key={s.slug}
              className={`chip ${strategy === s.slug ? 'active' : ''}`}
              title={s.hint}
              onClick={() => {
                setStrategy(s.slug);
                scheduleSave({ strategy: s.slug });
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
        <span className="muted small">{STRATEGIES.find((s) => s.slug === strategy)?.hint}</span>
      </section>

      {strategy === 'vocal_instr' && tracks.length >= 2 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <h2 className="h2">Чей голос и чья музыка</h2>
          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span className="muted small">Голос из песни</span>
              <select
                className="select input"
                value={vocalFrom}
                onChange={(e) => setVocalFrom(Number(e.target.value))}
              >
                {tracks.map((t, i) => (
                  <option key={t.id} value={i}>
                    {i + 1}. {t.title}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span className="muted small">Музыка из песни</span>
              <select
                className="select input"
                value={musicFrom}
                onChange={(e) => setMusicFrom(Number(e.target.value))}
              >
                {tracks.map((t, i) => (
                  <option key={t.id} value={i}>
                    {i + 1}. {t.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>
      )}

      <section style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div className="seg">
          <button
            className={`seg-item ${quality === 'fast' ? 'active' : ''}`}
            onClick={() => {
              setQuality('fast');
              scheduleSave({ quality: 'fast' });
            }}
          >
            Быстро
          </button>
          <button
            className={`seg-item ${quality === 'max' ? 'active' : ''}`}
            onClick={() => {
              setQuality('max');
              scheduleSave({ quality: 'max' });
            }}
          >
            Максимум
          </button>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <button className="btn btn-primary" disabled={tracks.length < 2 || starting} onClick={() => void merge()}>
            {starting ? 'Запускаем…' : 'Соединить песни'}
          </button>
          <span className="muted small">
            {tracks.length < 2 ? 'Нужно хотя бы две песни' : `Получите три варианта · ≈${estimate} мин`}
          </span>
        </div>
      </section>
    </div>
  );
}
