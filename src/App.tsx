import { useEffect, useState } from 'react';
import type { WorkerInfo } from './types/mixpilot';

const MODES = [
  {
    icon: '🎛️',
    title: 'Сделать ремикс',
    caption: 'Phonk, Bass Boosted, Slowed, Club, House — или скажите словами',
  },
  {
    icon: '🔗',
    title: 'Соединить песни',
    caption: 'Mashup, плавные переходы, лучшие моменты нескольких треков',
  },
  {
    icon: '🎤',
    title: 'Песня моим голосом',
    caption: 'Каверы и собственные треки вашим голосом',
  },
] as const;

type EngineState =
  | { kind: 'browser' } // vite dev в обычном браузере, без Electron
  | { kind: 'starting' }
  | { kind: 'online'; version: string; port: number }
  | { kind: 'offline' };

function useEngineState(): EngineState {
  const [state, setState] = useState<EngineState>(
    window.mixpilot ? { kind: 'starting' } : { kind: 'browser' },
  );

  useEffect(() => {
    const bridge = window.mixpilot;
    if (!bridge) return;
    let stopped = false;

    const poll = async () => {
      try {
        const info: WorkerInfo = await bridge.workerInfo();
        if (stopped) return;
        if (info.status === 'online' && info.meta && info.port) {
          setState({ kind: 'online', version: info.meta.version, port: info.port });
        } else if (info.status === 'failed') {
          setState({ kind: 'offline' });
        } else {
          setState({ kind: 'starting' });
        }
      } catch {
        if (!stopped) setState({ kind: 'offline' });
      }
    };

    poll();
    const timer = setInterval(poll, 2000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, []);

  return state;
}

function EngineStatus({ state }: { state: EngineState }) {
  const view = {
    browser: { color: 'var(--warn)', text: 'Браузерный режим — движок доступен только в приложении' },
    starting: { color: 'var(--warn)', text: 'AI-движок запускается…' },
    online: { color: 'var(--ok)', text: '' },
    offline: { color: 'var(--err)', text: 'AI-движок не отвечает — перезапустите приложение' },
  }[state.kind];

  const text =
    state.kind === 'online'
      ? `AI-движок: online · v${state.version} · порт ${state.port}`
      : view.text;

  return (
    <footer style={styles.statusBar}>
      <span style={{ ...styles.statusDot, background: view.color }} />
      <span style={{ color: 'var(--text-2)', fontSize: 13 }}>{text}</span>
    </footer>
  );
}

export default function App() {
  const engine = useEngineState();

  return (
    <div style={styles.shell}>
      <main style={styles.content}>
        <header style={{ marginBottom: 8 }}>
          <h1 style={styles.logo}>
            Mix<span style={styles.logoAccent}>Pilot</span>
          </h1>
          <p style={{ color: 'var(--text-2)' }}>Что делаем сегодня?</p>
        </header>

        <section style={styles.cardRow}>
          {MODES.map((m) => (
            <div key={m.title} style={styles.modeCard} title="Скоро — в следующем обновлении каркаса">
              <div style={{ fontSize: 40, marginBottom: 16 }}>{m.icon}</div>
              <div style={styles.modeTitle}>{m.title}</div>
              <div style={{ color: 'var(--text-2)', fontSize: 13, lineHeight: '18px' }}>{m.caption}</div>
            </div>
          ))}
        </section>
      </main>
      <EngineStatus state={engine} />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  shell: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    background:
      'radial-gradient(1200px 600px at 70% -10%, rgba(124,92,255,.14), transparent 60%),' +
      'radial-gradient(900px 500px at 10% 110%, rgba(79,209,255,.10), transparent 60%),' +
      'var(--bg-0)',
  },
  content: {
    flex: 1,
    maxWidth: 1280,
    width: '100%',
    margin: '0 auto',
    padding: '64px 48px',
    display: 'flex',
    flexDirection: 'column',
    gap: 32,
  },
  logo: {
    fontFamily: 'var(--font-display)',
    fontSize: 28,
    fontWeight: 600,
    letterSpacing: '0.02em',
  },
  logoAccent: {
    background: 'var(--grad-accent)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  cardRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 20,
  },
  modeCard: {
    background: 'var(--surface-1)',
    border: '1px solid var(--stroke)',
    borderRadius: 'var(--radius-l)',
    padding: '32px 28px',
    minHeight: 180,
    transition: 'transform 160ms ease-out, border-color 160ms ease-out',
    cursor: 'default',
  },
  modeTitle: {
    fontFamily: 'var(--font-display)',
    fontSize: 20,
    fontWeight: 600,
    marginBottom: 8,
  },
  statusBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '10px 16px',
    borderTop: '1px solid var(--stroke)',
    background: 'var(--bg-1)',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    flexShrink: 0,
  },
};
