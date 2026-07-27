import { useState } from 'react';
import type { Variant } from '../api/types';
import { useGeneration } from '../state/generation';
import { toast } from '../state/toasts';

/** Чипы правок — те же названия, что понимает worker (llm/edit_dsl.py CHIP_OPS). */
const EDIT_CHIPS = [
  'Больше баса',
  'Меньше баса',
  'Громче голос',
  'Тише голос',
  'Быстрее',
  'Медленнее',
  'Мощнее припев',
  'Больше атмосферы',
  'Ярче',
  'Мрачнее',
];

export function EditPanel({
  variant,
  onClose,
  onStarted,
}: {
  variant: Variant;
  onClose: () => void;
  onStarted: (jobId: string) => void;
}) {
  const edit = useGeneration((s) => s.edit);
  const [chips, setChips] = useState<string[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);

  const toggle = (chip: string) =>
    setChips((prev) => (prev.includes(chip) ? prev.filter((c) => c !== chip) : [...prev, chip]));

  const apply = async () => {
    if (chips.length === 0 && !text.trim()) {
      toast('Выберите, что изменить');
      return;
    }
    setBusy(true);
    const jobId = await edit(variant.id, chips, text.trim() || undefined);
    setBusy(false);
    if (jobId) {
      setChips([]);
      setText('');
      onStarted(jobId);
    }
  };

  return (
    <div className="card fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <h2 className="h2" style={{ flex: 1 }}>
          Что изменить в «{variant.title_ru}»?
        </h2>
        <button className="btn-icon" title="Закрыть" onClick={onClose}>
          ✕
        </button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {EDIT_CHIPS.map((c) => (
          <button key={c} className={`chip ${chips.includes(c) ? 'active' : ''}`} onClick={() => toggle(c)}>
            {c}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label className="muted small">
          Или скажите словами <span title="В облако уходит только текст, не звук">☁️</span>
        </label>
        <textarea
          className="textarea"
          placeholder="Например: сделай вступление короче и голос немного громче"
          value={text}
          onChange={(e) => setText(e.target.value)}
          style={{ minHeight: 60 }}
        />
        <span className="muted small">
          В облако уходит только текст пожелания — звук остаётся на вашем компьютере
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button className="btn btn-primary" onClick={() => void apply()} disabled={busy}>
          {busy ? 'Применяем…' : 'Применить'}
        </button>
        {chips.length > 0 && <span className="muted small">{chips.join(', ')}</span>}
      </div>
    </div>
  );
}
