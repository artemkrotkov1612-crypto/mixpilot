import { useEngine } from '../state/engine';
import { useScreens } from '../state/screens';
import { toast } from '../state/toasts';

const SOON = 'Скоро: в следующих обновлениях';

export function Sidebar() {
  const { screen, go } = useScreens();
  const engine = useEngine((s) => s.state);

  const status = {
    browser: { color: 'var(--warn)', text: 'браузерный режим' },
    starting: { color: 'var(--warn)', text: 'движок запускается…' },
    online: { color: 'var(--ok)', text: engine.kind === 'online' ? `движок v${engine.meta.version}` : '' },
    offline: { color: 'var(--err)', text: 'движок не отвечает' },
  }[engine.kind];

  return (
    <aside className="sidebar">
      <div className="logo">
        Mix<span className="logo-accent">Pilot</span>
      </div>
      <button className={`nav-item ${screen.name === 'home' ? 'active' : ''}`} onClick={() => go({ name: 'home' })}>
        <span>🏠</span> Главная
      </button>
      <button
        className={`nav-item ${screen.name === 'library' ? 'active' : ''}`}
        onClick={() => go({ name: 'library' })}
      >
        <span>🎵</span> Библиотека
      </button>
      <button
        className={`nav-item ${screen.name === 'voice' ? 'active' : ''}`}
        onClick={() => go({ name: 'voice' })}
      >
        <span>🎤</span> Мой голос
      </button>
      <button className="nav-item" onClick={() => toast(SOON)}>
        <span>💜</span> Профиль вкуса
      </button>
      <div className="spacer" />
      <button
        className={`nav-item ${screen.name === 'settings' ? 'active' : ''}`}
        onClick={() => go({ name: 'settings' })}
      >
        <span>⚙️</span> Настройки
      </button>
      <div className="engine-line">
        <span className="status-dot" style={{ background: status.color }} />
        <span>{status.text}</span>
      </div>
    </aside>
  );
}
