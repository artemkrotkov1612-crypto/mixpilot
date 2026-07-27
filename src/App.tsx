import { useEffect } from 'react';
import { PlayerBar } from './components/PlayerBar';
import { Sidebar } from './components/Sidebar';
import { Toasts } from './components/Toasts';
import { HomeScreen } from './screens/HomeScreen';
import { LibraryScreen } from './screens/LibraryScreen';
import { RemixMasterScreen } from './screens/RemixMasterScreen';
import { ResultsScreen } from './screens/ResultsScreen';
import { SettingsScreen } from './screens/SettingsScreen';
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
    case 'results':
      return <ResultsScreen key={screen.generationId} generationId={screen.generationId} />;
    case 'settings':
      return <SettingsScreen />;
  }
}

export default function App() {
  const engine = useEngine((s) => s.state);
  const start = useEngine((s) => s.start);

  useEffect(() => start(), [start]);

  // Сплэш, пока движок стартует первый раз (обычно 1–3 секунды).
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
