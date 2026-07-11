import { useEffect } from 'react';
import { MODE_LABELS, useProjects } from '../state/projects';
import { useEngine } from '../state/engine';
import { useScreens } from '../state/screens';
import { toast } from '../state/toasts';
import { formatRelative } from '../lib/relativeTime';

const SOON = 'Скоро: в одном из следующих обновлений';

export function HomeScreen() {
  const go = useScreens((s) => s.go);
  const { recent, refreshRecent } = useProjects();
  const engine = useEngine((s) => s.state);

  useEffect(() => {
    if (engine.kind === 'online') void refreshRecent();
  }, [engine.kind, refreshRecent]);

  return (
    <div className="screen-inner fade-in">
      <header>
        <h1 className="h-display">Что делаем сегодня?</h1>
        <p className="muted">Загрузите музыку — остальное MixPilot сделает сам</p>
      </header>

      <section className="grid-3">
        <button className="mode-card" onClick={() => go({ name: 'remix' })}>
          <span className="icon">🎛️</span>
          <div className="title">Сделать ремикс</div>
          <div className="muted small">Phonk, Bass Boosted, Slowed, Club, House — или скажите словами</div>
        </button>
        <button className="mode-card" onClick={() => toast(SOON)}>
          <span className="icon">🔗</span>
          <div className="title">Соединить песни</div>
          <div className="muted small">Mashup, плавные переходы, лучшие моменты нескольких треков</div>
        </button>
        <button className="mode-card" onClick={() => toast(SOON)}>
          <span className="icon">🎤</span>
          <div className="title">Песня моим голосом</div>
          <div className="muted small">Каверы и собственные треки вашим голосом</div>
        </button>
      </section>

      {recent.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <h2 className="h2">Недавние проекты</h2>
          <div className="recent-row">
            {recent.map((p) => (
              <button
                key={p.id}
                className="recent-card"
                onClick={() =>
                  p.mode === 'remix' ? go({ name: 'remix', projectId: p.id }) : toast(SOON)
                }
              >
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{p.title}</div>
                <div className="muted small">
                  {MODE_LABELS[p.mode]} · {p.track_count ?? 0} 🎵 · {formatRelative(p.updated_at)}
                </div>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
