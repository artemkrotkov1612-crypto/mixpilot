import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { CloudStatus, Settings, StorageInfo } from '../api/types';
import { useEngine } from '../state/engine';
import { toast } from '../state/toasts';

export function SettingsScreen() {
  const engine = useEngine((s) => s.state);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [cloud, setCloud] = useState<CloudStatus | null>(null);

  const refresh = async () => {
    const [s, st, cl] = await Promise.all([
      api<Settings>('/settings'),
      api<StorageInfo>('/storage'),
      api<CloudStatus>('/cloud'),
    ]);
    setSettings(s);
    setStorage(st);
    setCloud(cl);
  };

  const toggleCloud = async () => {
    const updated = await api<Settings>('/settings', {
      method: 'PUT',
      json: { key: 'cloud_enabled', value: !(settings?.cloud_enabled ?? true) },
    });
    setSettings(updated);
    setCloud(await api<CloudStatus>('/cloud'));
  };

  useEffect(() => {
    if (engine.kind === 'online') void refresh().catch(() => toast('Не удалось загрузить настройки', 'err'));
  }, [engine.kind]);

  const setQuality = async (value: 'fast' | 'max') => {
    const updated = await api<Settings>('/settings', { method: 'PUT', json: { key: 'quality_mode', value } });
    setSettings(updated);
  };

  return (
    <div className="screen-inner fade-in" style={{ maxWidth: 760 }}>
      <h1 className="h-display">Настройки</h1>

      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 className="h2">Качество по умолчанию</h2>
        <div className="seg" style={{ alignSelf: 'flex-start' }}>
          <button
            className={`seg-item ${settings?.quality_mode === 'fast' ? 'active' : ''}`}
            onClick={() => void setQuality('fast')}
          >
            Быстро
          </button>
          <button
            className={`seg-item ${settings?.quality_mode === 'max' ? 'active' : ''}`}
            onClick={() => void setQuality('max')}
          >
            Максимальное качество
          </button>
        </div>
        <p className="muted small">«Быстро» — лёгкие модели и короткое ожидание. «Максимум» — лучший звук, дольше.</p>
      </div>

      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 className="h2">Понимание текста ☁️</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className={`chip ${settings?.cloud_enabled ? 'active' : ''}`} onClick={() => void toggleCloud()}>
            {settings?.cloud_enabled ? 'Включено' : 'Выключено'}
          </button>
          {cloud && (
            <span className="small" style={{ color: cloud.ready ? 'var(--ok)' : 'var(--warn)' }}>
              {cloud.ready
                ? `Ключ подключён (${cloud.key_hint})`
                : cloud.has_key
                  ? 'Ключ есть, но понимание текста выключено'
                  : 'Ключ не задан — работают карточки и кнопки'}
            </span>
          )}
        </div>
        <p className="muted small">
          Позволяет писать пожелания обычными словами. В облако уходит только текст: аудио, голос и файлы
          никогда не покидают ваш компьютер. Карточки и кнопки работают без интернета.
        </p>
        {cloud?.has_key && <p className="muted small">Провайдер: {cloud.base_url}</p>}
      </div>

      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <h2 className="h2">Хранилище</h2>
        {storage ? (
          <>
            <div className="small muted" style={{ userSelect: 'text' }}>{storage.data_dir}</div>
            <div className="small">
              Свободно на диске: <b>{storage.disk_free_gb} ГБ</b> из {storage.disk_total_gb} ГБ
            </div>
            <div className="small muted">
              Музыка: {storage.media_mb} МБ · Кеш обработки: {storage.cache_mb} МБ · Результаты: {storage.renders_mb} МБ
            </div>
            <button className="btn btn-secondary" style={{ alignSelf: 'flex-start' }} onClick={() => void refresh()}>
              Обновить
            </button>
          </>
        ) : (
          <div className="muted small">Загружаем…</div>
        )}
      </div>

      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <h2 className="h2">Движок</h2>
        {engine.kind === 'online' ? (
          <div className="small muted" style={{ userSelect: 'text' }}>
            worker v{engine.meta.version} · Python {engine.meta.python} · порт {engine.port}
            {engine.meta.ffmpeg === false && <span style={{ color: 'var(--err)' }}> · ffmpeg не найден!</span>}
          </div>
        ) : (
          <div className="small muted">Движок недоступен</div>
        )}
        <p className="muted small">Облако (понимание текста) и «Мой голос» появятся в следующих обновлениях.</p>
      </div>
    </div>
  );
}
