import { useEffect, useRef, useState } from 'react';
import type { Project, RemixParams, Track } from '../api/types';
import { api } from '../api/client';
import { DropZone } from '../components/DropZone';
import { TrackPrep } from '../components/TrackPrep';
import { TrackRow } from '../components/TrackRow';
import { useEngine } from '../state/engine';
import { useLibrary } from '../state/library';
import {
  attachTrack,
  createProject,
  detachTrack,
  loadProject,
  saveProject,
  useProjects,
} from '../state/projects';
import { useGeneration } from '../state/generation';
import { useScreens } from '../state/screens';
import { toast } from '../state/toasts';

/** Слаг стиля для worker'а -> подпись в UI. M3 реализует Slowed и Bass Boosted. */
export const REMIX_STYLES: { slug: string; label: string }[] = [
  { slug: 'slowed', label: 'Slowed' },
  { slug: 'bass_boosted', label: 'Bass Boosted' },
  { slug: 'phonk', label: 'Phonk' },
  { slug: 'club', label: 'Club' },
  { slug: 'house', label: 'House' },
  { slug: 'auto', label: '✨ AI сам решит' },
];
export const MOOD_CHIPS = [
  'Мрачно', 'Энергично', 'Спокойно', 'Мощный бас', 'Клубно',
  'Атмосферно', 'Быстрее', 'Медленнее', 'Эмоциональный вокал', 'Мощный припев',
];
const MAX_MOODS = 4;
const SAVE_DEBOUNCE_MS = 600;

type SaveState = 'idle' | 'saving' | 'saved';

interface MasterState {
  projectId: string | null;
  track: Track | null;
  style: string | null;
  chips: string[];
  text: string;
  quality: 'fast' | 'max';
}

const EMPTY: MasterState = { projectId: null, track: null, style: null, chips: [], text: '', quality: 'fast' };

export function RemixMasterScreen({ projectId, initialTrackId }: { projectId?: string; initialTrackId?: string }) {
  const go = useScreens((s) => s.go);
  const engine = useEngine((s) => s.state);
  const importFiles = useLibrary((s) => s.importFiles);
  const refreshRecent = useProjects((s) => s.refreshRecent);

  const [state, setState] = useState<MasterState>(EMPTY);
  const [title, setTitle] = useState('Новый ремикс');
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [loading, setLoading] = useState(Boolean(projectId));
  const [starting, setStarting] = useState(false);
  const startGeneration = useGeneration((s) => s.start);
  const saveTimer = useRef<number | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  // Открытие существующего черновика / трека из библиотеки.
  useEffect(() => {
    if (engine.kind !== 'online') return;
    let cancelled = false;
    (async () => {
      if (projectId) {
        try {
          const p = await loadProject(projectId);
          if (cancelled) return;
          const params = p.params as RemixParams;
          setTitle(p.title);
          setState({
            projectId: p.id,
            track: p.tracks.find((t) => t.role === 'source') ?? null,
            style: params.style ?? null,
            chips: params.chips ?? [],
            text: params.text ?? '',
            quality: params.quality ?? 'fast',
          });
        } catch {
          toast('Не удалось открыть проект', 'err');
          go({ name: 'home' });
        } finally {
          setLoading(false);
        }
      } else if (initialTrackId) {
        try {
          const track = await api<Track>(`/library/tracks/${initialTrackId}`);
          if (!cancelled) setState((s) => ({ ...s, track }));
        } catch {
          /* трек могли удалить — просто пустой мастер */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine.kind, projectId, initialTrackId]);

  /** Черновик создаётся лениво — при первом содержательном действии. */
  const ensureProject = async (): Promise<string> => {
    if (stateRef.current.projectId) return stateRef.current.projectId;
    const p: Project = await createProject('remix');
    setState((s) => ({ ...s, projectId: p.id }));
    if (stateRef.current.track) await attachTrack(p.id, stateRef.current.track.id);
    void refreshRecent();
    return p.id;
  };

  const scheduleSave = () => {
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    setSaveState('saving');
    saveTimer.current = window.setTimeout(async () => {
      try {
        const id = await ensureProject();
        const { style, chips, text, quality } = stateRef.current;
        await saveProject(id, { title, params: { style: style ?? undefined, chips, text, quality } });
        setSaveState('saved');
      } catch {
        setSaveState('idle');
        toast('Не удалось сохранить черновик', 'err');
      }
    }, SAVE_DEBOUNCE_MS);
  };

  const update = (patch: Partial<MasterState>) => {
    setState((s) => ({ ...s, ...patch }));
    // сохранение после применения patch — через рефы в таймере
    window.setTimeout(scheduleSave, 0);
  };

  const onDropTrack = async (paths: string[]) => {
    const added = await importFiles(paths.slice(0, 1));
    const track = added[0];
    if (!track) return;
    const prev = stateRef.current.track;
    setState((s) => ({ ...s, track }));
    try {
      const id = await ensureProject();
      if (prev && prev.id !== track.id) await detachTrack(id, prev.id);
      await attachTrack(id, track.id);
      scheduleSave();
    } catch {
      toast('Не удалось прикрепить трек', 'err');
    }
  };

  const createRemix = async () => {
    if (!state.track) {
      toast('Сначала добавьте песню');
      return;
    }
    setStarting(true);
    try {
      const id = await ensureProject();
      const { style, chips, text, quality } = stateRef.current;
      await saveProject(id, { title, params: { style: style ?? undefined, chips, text, quality } });
      const generationId = await startGeneration(id, {
        style: style ?? 'auto',
        chips,
        text: text || undefined,
        quality,
      });
      if (generationId) go({ name: 'results', generationId });
    } catch {
      toast('Не удалось запустить генерацию', 'err');
    } finally {
      setStarting(false);
    }
  };

  const toggleMood = (chip: string) => {
    const has = state.chips.includes(chip);
    if (!has && state.chips.length >= MAX_MOODS) {
      toast(`Не больше ${MAX_MOODS} карточек настроения`);
      return;
    }
    update({ chips: has ? state.chips.filter((c) => c !== chip) : [...state.chips, chip] });
  };

  if (loading) {
    return (
      <div className="splash">
        <div className="spinner" />
        <div className="muted">Открываем проект…</div>
      </div>
    );
  }

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
            scheduleSave();
          }}
        />
        <span className="muted small" style={{ whiteSpace: 'nowrap' }}>
          {saveState === 'saving' ? 'Сохраняем…' : saveState === 'saved' ? 'Черновик сохранён ✓' : ''}
        </span>
      </header>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 className="h2">Песня</h2>
        {state.track ? (
          <div className="card" style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <TrackRow track={state.track} showRemix={false} />
            <div style={{ padding: '0 14px 8px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              <TrackPrep key={state.track.id} trackId={state.track.id} />
              <DropZone compact onPaths={(p) => void onDropTrack(p)}>
                <span className="small">Заменить песню — перетащите или нажмите</span>
              </DropZone>
            </div>
          </div>
        ) : (
          <DropZone onPaths={(p) => void onDropTrack(p)}>
            <div style={{ fontWeight: 600 }}>Перетащите песню или нажмите, чтобы выбрать</div>
            <div className="small" style={{ marginTop: 4 }}>MP3 · WAV · FLAC · M4A</div>
          </DropZone>
        )}
      </section>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 className="h2">Каким сделать?</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {REMIX_STYLES.map((s) => (
            <button
              key={s.slug}
              className={`chip ${state.style === s.slug ? 'active' : ''}`}
              onClick={() => update({ style: state.style === s.slug ? null : s.slug })}
            >
              {s.label}
            </button>
          ))}
        </div>
      </section>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 className="h2">
          Добавить настроение <span className="muted small">(необязательно, до {MAX_MOODS})</span>
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {MOOD_CHIPS.map((c) => (
            <button key={c} className={`chip ${state.chips.includes(c) ? 'active' : ''}`} onClick={() => toggleMood(c)}>
              {c}
            </button>
          ))}
        </div>
      </section>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 className="h2">
          Свои пожелания <span title="В облако уходит только текст, не звук">☁️</span>
        </h2>
        <textarea
          className="textarea"
          placeholder="Например: сделай вступление короче, бас мощнее, а припев энергичнее"
          value={state.text}
          onChange={(e) => update({ text: e.target.value })}
        />
      </section>

      <section style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div className="seg">
          <button
            className={`seg-item ${state.quality === 'fast' ? 'active' : ''}`}
            onClick={() => update({ quality: 'fast' })}
          >
            Быстро · ≈3 мин
          </button>
          <button
            className={`seg-item ${state.quality === 'max' ? 'active' : ''}`}
            onClick={() => update({ quality: 'max' })}
          >
            Максимум · ≈10 мин
          </button>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <button
            className="btn btn-primary"
            disabled={!state.track || starting}
            onClick={() => void createRemix()}
          >
            {starting ? 'Запускаем…' : 'Создать ремикс'}
          </button>
          <span className="muted small">
            {state.track
              ? `Получите три варианта · ${state.quality === 'fast' ? '≈3 мин' : '≈10 мин'}`
              : 'Добавьте песню, чтобы продолжить'}
          </span>
        </div>
      </section>
    </div>
  );
}
