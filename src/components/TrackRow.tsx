import { useEffect, useRef, useState } from 'react';
import type { Track } from '../api/types';
import { formatDuration } from '../lib/format';
import { useLibrary } from '../state/library';
import { trackPlayable, usePlayer } from '../state/player';
import { useScreens } from '../state/screens';
import { toast } from '../state/toasts';

export function TrackRow({ track, showRemix = true }: { track: Track; showRemix?: boolean }) {
  const { play, current, playing } = usePlayer();
  const { remove, toggleFavorite } = useLibrary();
  const go = useScreens((s) => s.go);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const isCurrent = current?.id === `track:${track.id}`;

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [menuOpen]);

  const showInFolder = () => {
    const target = track.src_path;
    if (target && window.mixpilot) void window.mixpilot.showInFolder(target);
    else toast('Исходный файл недоступен');
    setMenuOpen(false);
  };

  const del = () => {
    setMenuOpen(false);
    if (window.confirm(`Удалить «${track.title}» из библиотеки?\nИсходный файл на диске не будет тронут.`)) {
      void remove(track.id);
    }
  };

  return (
    <div className={`track-row ${isCurrent ? 'playing' : ''} ${menuOpen ? 'menu-open' : ''}`}>
      <button
        className={`play-btn ${isCurrent && playing ? 'playing' : ''}`}
        onClick={() => void play(trackPlayable(track))}
      >
        {isCurrent && playing ? '⏸' : '▶'}
      </button>
      <div className="meta">
        <div className="name">{track.title}</div>
        <div className="muted small">{track.artist ?? '—'}</div>
      </div>
      <div className="muted small tabular">{formatDuration(track.duration_s)}</div>
      <div className="actions">
        <button
          className="btn-icon"
          title={track.is_favorite ? 'Убрать из любимого' : 'В любимое'}
          onClick={() => void toggleFavorite(track)}
          style={track.is_favorite ? { color: 'var(--like)' } : undefined}
        >
          {track.is_favorite ? '♥' : '♡'}
        </button>
        <div className="menu" ref={menuRef}>
          <button className="btn-icon" title="Ещё" onClick={() => setMenuOpen((v) => !v)}>
            ⋯
          </button>
          {menuOpen && (
            <div className="menu-list">
              {showRemix && (
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    go({ name: 'remix', initialTrackId: track.id });
                  }}
                >
                  🎛️ Сделать ремикс
                </button>
              )}
              <button onClick={showInFolder}>📂 Показать в папке</button>
              <button className="danger" onClick={del}>
                🗑 Удалить из библиотеки
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
