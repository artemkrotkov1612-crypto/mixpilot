import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Track, VoiceProfile } from '../api/types';
import { DropZone } from '../components/DropZone';
import { TrackRow } from '../components/TrackRow';
import { useEngine } from '../state/engine';
import { useGeneration } from '../state/generation';
import { useLibrary } from '../state/library';
import { attachTrack, createProject, detachTrack, saveProject } from '../state/projects';
import { useScreens } from '../state/screens';
import { toast } from '../state/toasts';

export function VoiceCoverScreen() {
  const go = useScreens((s) => s.go);
  const online = useEngine((s) => s.state.kind === 'online');
  const importFiles = useLibrary((s) => s.importFiles);
  const startGeneration = useGeneration((s) => s.start);

  const [voice, setVoice] = useState<VoiceProfile | null>(null);
  const [track, setTrack] = useState<Track | null>(null);
  const [pid, setPid] = useState<string | null>(null);
  const [quality, setQuality] = useState<'fast' | 'max'>('fast');
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!online) return;
    void api<{ active: VoiceProfile | null }>('/voice/profiles')
      .then((d) => setVoice(d.active))
      .catch(() => {});
  }, [online]);

  const ensureProject = async (): Promise<string> => {
    if (pid) return pid;
    const p = await createProject('voice_cover');
    setPid(p.id);
    return p.id;
  };

  const onDrop = async (paths: string[]) => {
    const added = await importFiles(paths.slice(0, 1));
    const next = added[0];
    if (!next) return;
    const id = await ensureProject();
    if (track && track.id !== next.id) await detachTrack(id, track.id);
    await attachTrack(id, next.id);
    setTrack(next);
  };

  const makeCover = async () => {
    if (!track) {
      toast('Добавьте песню');
      return;
    }
    setStarting(true);
    try {
      const id = await ensureProject();
      await saveProject(id, { title: `Кавер — ${track.title}`, params: { quality } });
      const generationId = await startGeneration(id, { quality });
      if (generationId) go({ name: 'results', generationId });
    } finally {
      setStarting(false);
    }
  };

  if (!voice) {
    return (
      <div className="screen-inner fade-in" style={{ maxWidth: 720 }}>
        <button className="btn-ghost" style={{ alignSelf: 'flex-start' }} onClick={() => go({ name: 'home' })}>
          ‹ Главная
        </button>
        <header>
          <h1 className="h-display">Песня моим голосом</h1>
          <p className="muted">Сначала создадим ваш голос — это займёт пару минут</p>
        </header>
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p className="muted small">
            Мы попросим прочитать несколько фраз и немного попеть. После этого любую песню можно будет
            услышать вашим голосом.
          </p>
          <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }} onClick={() => go({ name: 'voice' })}>
            Создать мой голос
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="screen-inner fade-in" style={{ maxWidth: 780 }}>
      <button className="btn-ghost" style={{ alignSelf: 'flex-start' }} onClick={() => go({ name: 'home' })}>
        ‹ Главная
      </button>

      <header>
        <h1 className="h-display">Песня моим голосом</h1>
        <p className="muted">Голос «{voice.name}» готов — выберите песню для кавера</p>
      </header>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 className="h2">Песня</h2>
        {track ? (
          <div className="card" style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <TrackRow track={track} showRemix={false} />
            <div style={{ padding: '0 14px 8px' }}>
              <DropZone compact onPaths={(p) => void onDrop(p)}>
                <span className="small">Заменить песню</span>
              </DropZone>
            </div>
          </div>
        ) : (
          <DropZone onPaths={(p) => void onDrop(p)}>
            <div style={{ fontWeight: 600 }}>Перетащите песню или нажмите, чтобы выбрать</div>
            <div className="small" style={{ marginTop: 4 }}>MP3 · WAV · FLAC · M4A</div>
          </DropZone>
        )}
      </section>

      <section style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div className="seg">
          <button className={`seg-item ${quality === 'fast' ? 'active' : ''}`} onClick={() => setQuality('fast')}>
            Быстро
          </button>
          <button className={`seg-item ${quality === 'max' ? 'active' : ''}`} onClick={() => setQuality('max')}>
            Максимум
          </button>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <button className="btn btn-primary" disabled={!track || starting} onClick={() => void makeCover()}>
            {starting ? 'Запускаем…' : 'Сделать кавер'}
          </button>
          <span className="muted small">
            {track ? 'Получите три варианта обработки голоса' : 'Добавьте песню, чтобы продолжить'}
          </span>
        </div>
      </section>
    </div>
  );
}
