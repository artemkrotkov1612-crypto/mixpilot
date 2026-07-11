import { useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import { mediaUrl } from '../api/client';
import { formatDuration } from '../lib/format';
import { usePlayer } from '../state/player';

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function PlayerBar() {
  const { track, peaks, duration, playing, toggle, onFinished } = usePlayer();
  const waveRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const [position, setPosition] = useState(0);

  // Пересоздаём wavesurfer на смену трека (после прихода пиков).
  useEffect(() => {
    wsRef.current?.destroy();
    wsRef.current = null;
    setPosition(0);
    if (!track || !waveRef.current || peaks === null) return;

    const ws = WaveSurfer.create({
      container: waveRef.current,
      height: 44,
      url: mediaUrl(track.media_path),
      peaks: [peaks],
      duration,
      normalize: true,
      waveColor: cssVar('--wave-rest'),
      progressColor: cssVar('--wave-played'),
      cursorColor: 'transparent',
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
    });
    ws.on('timeupdate', (t) => setPosition(t));
    ws.on('finish', onFinished);
    wsRef.current = ws;
    return () => {
      ws.destroy();
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track?.id, peaks === null]);

  useEffect(() => {
    const ws = wsRef.current;
    if (!ws) return;
    if (playing && !ws.isPlaying()) void ws.play();
    if (!playing && ws.isPlaying()) ws.pause();
  }, [playing, peaks]);

  if (!track) return <div className="playerbar" style={{ color: 'var(--text-3)', fontSize: 13 }}>Выберите трек — послушаем</div>;

  return (
    <div className="playerbar">
      <button className={`play-btn ${playing ? 'playing' : ''}`} onClick={toggle} title={playing ? 'Пауза' : 'Играть'}>
        {playing ? '⏸' : '▶'}
      </button>
      <div className="titles">
        <div className="name">{track.title}</div>
        <div className="muted small">{track.artist ?? '—'}</div>
      </div>
      <div className="wave" ref={waveRef}>
        {peaks === null && <div className="progress-line"><div style={{ width: '30%' }} /></div>}
      </div>
      <div className="muted small tabular">
        {formatDuration(position)} / {formatDuration(duration)}
      </div>
    </div>
  );
}
