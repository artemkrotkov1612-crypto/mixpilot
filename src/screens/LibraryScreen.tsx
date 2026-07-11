import { useEffect } from 'react';
import { DropZone } from '../components/DropZone';
import { EmptyState } from '../components/EmptyState';
import { TrackRow } from '../components/TrackRow';
import { useEngine } from '../state/engine';
import { useLibrary, type LibrarySort } from '../state/library';

export function LibraryScreen() {
  const lib = useLibrary();
  const engine = useEngine((s) => s.state);

  useEffect(() => {
    if (engine.kind === 'online') void lib.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine.kind]);

  return (
    <div className="screen-inner fade-in">
      <header style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <h1 className="h-display">Библиотека</h1>
        {lib.total > 0 && <span className="muted small">{lib.total} трек(ов)</span>}
      </header>

      <DropZone compact onPaths={(paths) => void lib.importFiles(paths)}>
        <div style={{ fontWeight: 600 }}>Перетащите музыку сюда или нажмите, чтобы выбрать</div>
        <div className="small" style={{ marginTop: 4 }}>MP3 · WAV · FLAC · M4A и другие</div>
      </DropZone>

      {lib.importing.active && (
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="small">
            Импортируем {lib.importing.done + 1} из {lib.importing.total}: {lib.importing.current}
          </div>
          <div className="progress-line">
            <div style={{ width: `${(lib.importing.done / Math.max(lib.importing.total, 1)) * 100}%` }} />
          </div>
        </div>
      )}

      <div className="toolbar">
        <input
          className="input"
          placeholder="Поиск по названию или исполнителю"
          value={lib.query}
          onChange={(e) => lib.setQuery(e.target.value)}
        />
        <select className="select input" value={lib.sort} onChange={(e) => lib.setSort(e.target.value as LibrarySort)}>
          <option value="added">Сначала новые</option>
          <option value="title">По названию</option>
          <option value="duration">По длительности</option>
        </select>
        <button className={`chip ${lib.favOnly ? 'active' : ''}`} onClick={() => lib.setFavOnly(!lib.favOnly)}>
          ♥ Любимое
        </button>
      </div>

      <section>
        {lib.tracks.length === 0 && !lib.loading ? (
          <EmptyState
            icon="🎧"
            title={lib.query || lib.favOnly ? 'Ничего не нашлось' : 'Пока пусто'}
            hint={lib.query || lib.favOnly ? 'Попробуйте изменить запрос' : 'Перетащите музыку выше — начнём'}
          />
        ) : (
          lib.tracks.map((t) => <TrackRow key={t.id} track={t} />)
        )}
      </section>
    </div>
  );
}
