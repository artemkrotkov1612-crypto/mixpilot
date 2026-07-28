import { useEffect, useState } from 'react';
import { api, coverUrl } from '../api/client';
import type { ShareLink, TitleSuggestions, Variant } from '../api/types';
import { toast } from '../state/toasts';

type Tab = 'title' | 'share';

/** Название с обложкой и передача на телефон — обе «витринные» операции варианта. */
export function ArtworkPanel({ variant, onClose }: { variant: Variant; onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('title');

  return (
    <div className="card fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <h2 className="h2" style={{ flex: 1 }}>Оформление «{variant.custom_title || variant.title_ru}»</h2>
        <button className="btn-icon" onClick={onClose} title="Закрыть">✕</button>
      </div>
      <div className="seg" style={{ alignSelf: 'flex-start' }}>
        <button className={`seg-item ${tab === 'title' ? 'active' : ''}`} onClick={() => setTab('title')}>
          Название и обложка
        </button>
        <button className={`seg-item ${tab === 'share' ? 'active' : ''}`} onClick={() => setTab('share')}>
          На телефон
        </button>
      </div>
      {tab === 'title' ? <TitleTab variant={variant} /> : <ShareTab variant={variant} />}
    </div>
  );
}

function TitleTab({ variant }: { variant: Variant }) {
  const [titles, setTitles] = useState<TitleSuggestions | null>(null);
  const [chosen, setChosen] = useState(variant.custom_title ?? '');
  const [cover, setCover] = useState<string>(variant.cover_path ? coverUrl(variant.id, variant.cover_path) : '');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api<TitleSuggestions>(`/variants/${variant.id}/titles`)
      .then((t) => alive && setTitles(t))
      .catch(() => alive && toast('Не удалось придумать названия', 'err'));
    return () => {
      alive = false;
    };
  }, [variant.id]);

  const makeCover = async (title: string) => {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await api(`/variants/${variant.id}/cover`, { json: { title } });
      // Метка времени обязательна: путь тот же, браузер иначе покажет старую картинку.
      setCover(coverUrl(variant.id, Date.now()));
      toast('Обложка готова');
    } catch {
      toast('Не удалось нарисовать обложку', 'err');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {cover ? (
        <img src={cover} alt="Обложка" style={{ width: 200, borderRadius: 14, alignSelf: 'center' }} />
      ) : (
        <div className="muted small">Выберите название — обложка нарисуется по волне вашего трека.</div>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {titles ? (
          titles.titles.map((t) => (
            <button
              key={t}
              className={`chip ${chosen === t ? 'active' : ''}`}
              onClick={() => {
                setChosen(t);
                void makeCover(t);
              }}
            >
              {t}
            </button>
          ))
        ) : (
          <span className="muted small">Придумываем названия…</span>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <input
          className="input"
          style={{ flex: 1 }}
          placeholder="Или своё название"
          value={chosen}
          onChange={(e) => setChosen(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void makeCover(chosen)}
        />
        <button className="btn btn-primary" disabled={busy || !chosen.trim()} onClick={() => void makeCover(chosen)}>
          {busy ? 'Рисуем…' : 'Сделать обложку'}
        </button>
      </div>

      {titles && !titles.cloud && (
        <p className="muted small">
          Названия подобраны на вашем компьютере: понимание текста выключено или нет интернета.
        </p>
      )}
    </div>
  );
}

function ShareTab({ variant }: { variant: Variant }) {
  const [link, setLink] = useState<ShareLink | null>(null);
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(0);

  useEffect(() => {
    if (!link) return;
    setLeft(link.expires_in_s);
    const timer = setInterval(() => setLeft((v) => Math.max(0, v - 1)), 1000);
    return () => clearInterval(timer);
  }, [link]);

  const create = async () => {
    setBusy(true);
    try {
      setLink(await api<ShareLink>(`/variants/${variant.id}/share`, { method: 'POST' }));
    } catch {
      toast('Не удалось открыть ссылку', 'err');
    } finally {
      setBusy(false);
    }
  };

  const close = async () => {
    await api('/share', { method: 'DELETE' }).catch(() => undefined);
    setLink(null);
  };

  if (!link) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <p className="muted small">
          Наведите камеру телефона на QR-код и скачайте трек. Ссылка работает только в вашей домашней сети
          и погаснет через 15 минут — в интернет ничего не отправляется.
        </p>
        <button className="btn btn-primary" disabled={busy} onClick={() => void create()} style={{ alignSelf: 'flex-start' }}>
          {busy ? 'Готовим…' : 'Показать QR-код'}
        </button>
      </div>
    );
  }

  const mm = String(Math.floor(left / 60)).padStart(2, '0');
  const ss = String(left % 60).padStart(2, '0');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'center' }}>
      <div
        style={{ background: '#fff', padding: 12, borderRadius: 14, lineHeight: 0 }}
        // QR рисует segno на нашей же стороне: это наш SVG, не чужой контент.
        dangerouslySetInnerHTML={{ __html: link.qr_svg }}
      />
      <div className="small" style={{ userSelect: 'text', textAlign: 'center' }}>{link.url}</div>
      <div className="muted small">
        {left > 0 ? `Ссылка погаснет через ${mm}:${ss}` : 'Ссылка погасла — откройте новую'}
      </div>
      <button className="btn btn-secondary small" onClick={() => void close()}>
        Закрыть доступ сейчас
      </button>
    </div>
  );
}
