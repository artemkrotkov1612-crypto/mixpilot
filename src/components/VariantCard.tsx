import { useState } from 'react';
import { coverUrl } from '../api/client';
import type { Variant } from '../api/types';
import { useGeneration } from '../state/generation';
import { usePlayer, variantPlayable } from '../state/player';

const FORMATS = [
  { id: 'mp3', label: 'MP3 — для телефона и мессенджеров' },
  { id: 'wav', label: 'WAV — максимальное качество' },
  { id: 'flac', label: 'FLAC — качество без потерь, меньше размер' },
] as const;

export function VariantCard({
  variant,
  projectTitle,
  onEdit,
  onArtwork,
}: {
  variant: Variant;
  projectTitle: string;
  onEdit: (variant: Variant) => void;
  onArtwork: (variant: Variant) => void;
}) {
  const { play, current, playing } = usePlayer();
  const { rate, exportVariant } = useGeneration();
  const [menuOpen, setMenuOpen] = useState(false);

  const playable = variantPlayable(variant, projectTitle);
  const isCurrent = current?.id === playable.id;

  return (
    <div className="card fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button
          className={`play-btn ${isCurrent && playing ? 'playing' : ''}`}
          onClick={() => void play(playable)}
          title="Послушать"
        >
          {isCurrent && playing ? '⏸' : '▶'}
        </button>
        {variant.cover_path && (
          <img
            src={coverUrl(variant.id, variant.cover_path)}
            alt=""
            style={{ width: 44, height: 44, borderRadius: 10, objectFit: 'cover', flexShrink: 0 }}
          />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 15 }}>
            {variant.custom_title || variant.title_ru}
          </div>
          <div className="muted small">
            {variant.custom_title ? variant.title_ru : variant.description_ru}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
        {/* Повторный клик снимает оценку — и заодно стирает её из профиля вкуса. */}
        <button
          className="btn-icon"
          title={variant.rating > 0 ? 'Убрать оценку' : 'Нравится'}
          onClick={() => void rate(variant.id, variant.rating > 0 ? 0 : 1)}
          style={variant.rating > 0 ? { color: 'var(--like)' } : undefined}
        >
          👍
        </button>
        <button
          className="btn-icon"
          title={variant.rating < 0 ? 'Убрать оценку' : 'Не нравится'}
          onClick={() => void rate(variant.id, variant.rating < 0 ? 0 : -1)}
          style={variant.rating < 0 ? { color: 'var(--warn)' } : undefined}
        >
          👎
        </button>
        <div style={{ flex: 1 }} />
        <button className="btn btn-secondary small" onClick={() => onArtwork(variant)}>
          Оформить
        </button>
        <button className="btn btn-secondary small" onClick={() => onEdit(variant)}>
          Изменить
        </button>
        <div className="menu">
          <button className="btn btn-secondary small" onClick={() => setMenuOpen((v) => !v)}>
            Сохранить ▾
          </button>
          {menuOpen && (
            <div className="menu-list">
              {FORMATS.map((f) => (
                <button
                  key={f.id}
                  onClick={() => {
                    setMenuOpen(false);
                    void exportVariant(variant.id, f.id);
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
