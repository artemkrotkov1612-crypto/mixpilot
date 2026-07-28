import { useEffect, useState } from 'react';
import { Onboarding, onboardingDone } from './components/Onboarding';
import { PlayerBar } from './components/PlayerBar';
import { Sidebar } from './components/Sidebar';
import { Toasts } from './components/Toasts';
import { HomeScreen } from './screens/HomeScreen';
import { LibraryScreen } from './screens/LibraryScreen';
import { MergeMasterScreen } from './screens/MergeMasterScreen';
import { RemixMasterScreen } from './screens/RemixMasterScreen';
import { ResultsScreen } from './screens/ResultsScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { VoiceCoverScreen } from './screens/VoiceCoverScreen';
import { VoiceScreen } from './screens/VoiceScreen';
import { useEngine } from './state/engine';
import { useScreens } from './state/screens';

function CurrentScreen() {
  const screen = useScreens((s) => s.screen);
  switch (screen.name) {
    case 'home':
      return <HomeScreen />;
    case 'library':
      return <LibraryScreen />;
    case 'remix':
      return (
        <RemixMasterScreen
          key={screen.projectId ?? screen.initialTrackId ?? 'new'}
          projectId={screen.projectId}
          initialTrackId={screen.initialTrackId}
        />
      );
    case 'merge':
      return <MergeMasterScreen key={screen.projectId ?? 'new'} projectId={screen.projectId} />;
    case 'results':
      return <ResultsScreen key={screen.generationId} generationId={screen.generationId} />;
    case 'voice':
      return <VoiceScreen />;
    case 'voiceCover':
      return <VoiceCoverScreen />;
    case 'settings':
      return <SettingsScreen />;
  }
}

export default function App() {
  const engine = useEngine((s) => s.state);
  const start = useEngine((s) => s.start);
  const [needsOnboarding, setNeedsOnboarding] = useState(() => !onboardingDone());

  useEffect(() => start(), [start]);

  // Первый запуск: доустанавливаем Python и библиотеки (один раз, ~3 ГБ).
  if (engine.kind === 'setup' || engine.kind === 'setupFailed') {
    const failed = engine.kind === 'setupFailed';
    return (
      <div className="splash">
        <div className="h-display">
          Mix<span className="logo-accent">Pilot</span>
        </div>
        {failed ? (
          <>
            <div className="small" style={{ color: 'var(--err)', maxWidth: 460, textAlign: 'center' }}>
              {engine.errorRu}
            </div>
            <div className="muted small">Закройте окно и запустите MixPilot снова</div>
          </>
        ) : (
          <>
            <div className="spinner" />
            <div className="muted">{engine.textRu}</div>
            <div className="progress-line" style={{ width: 320 }}>
              <div style={{ width: `${Math.max(Math.round(engine.pct * 100), 3)}%` }} />
            </div>
            <div className="muted small" style={{ maxWidth: 420, textAlign: 'center' }}>
              Это делается один раз при первом запуске: MixPilot скачивает и настраивает всё сам.
              Нужен интернет и около 8 ГБ на диске.
            </div>
          </>
        )}
      </div>
    );
  }

  // Сплэш, пока движок стартует (обычно 1–3 секунды).
  if (engine.kind === 'starting') {
    return (
      <div className="splash">
        <div className="h-display">
          Mix<span className="logo-accent">Pilot</span>
        </div>
        <div className="spinner" />
        <div className="muted">Запускаем AI-движок…</div>
      </div>
    );
  }

  // Знакомство показываем поверх пустого шелла: движок к этому моменту уже жив.
  if (needsOnboarding) {
    return (
      <div className="app-shell">
        <main className="screen">
          <Onboarding onDone={() => setNeedsOnboarding(false)} />
        </main>
        <Toasts />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="screen">
        <CurrentScreen />
      </main>
      <PlayerBar />
      <Toasts />
    </div>
  );
}
