import type { Section } from '../api/types';
import { formatDuration } from '../lib/format';

export const SECTION_RU: Record<Section['label'], string> = {
  intro: 'Вступление',
  verse: 'Куплет',
  chorus: 'Припев',
  bridge: 'Проигрыш',
  drop: 'Дроп',
  outro: 'Финал',
};

const SECTION_BG: Record<Section['label'], string> = {
  intro: 'var(--surface-2)',
  verse: '#3d4470',
  chorus: 'var(--grad-accent)',
  bridge: '#2c3150',
  drop: 'linear-gradient(135deg, #ff5d9e 0%, #7c5cff 100%)',
  outro: 'var(--surface-2)',
};

/** Полоса структуры трека: цветные смысловые блоки (не DAW-дорожки). */
export function BlockStrip({ sections }: { sections: Section[] }) {
  if (sections.length === 0) return null;
  const total = sections[sections.length - 1].end_s;
  return (
    <div style={{ display: 'flex', gap: 3, width: '100%' }}>
      {sections.map((s) => {
        const widthPct = ((s.end_s - s.start_s) / total) * 100;
        const label = SECTION_RU[s.label];
        return (
          <div
            key={s.id}
            title={`${label} · ${formatDuration(s.start_s)}–${formatDuration(s.end_s)}`}
            style={{
              width: `${widthPct}%`,
              minWidth: 8,
              height: 36,
              borderRadius: 8,
              background: SECTION_BG[s.label],
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
              whiteSpace: 'nowrap',
              fontSize: 11,
              fontWeight: 700,
              color: 'var(--text-1)',
              opacity: 0.55 + 0.45 * s.energy,
            }}
          >
            {widthPct > 9 ? label : ''}
          </div>
        );
      })}
    </div>
  );
}
