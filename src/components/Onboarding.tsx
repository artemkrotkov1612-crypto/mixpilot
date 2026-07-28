import { useState } from 'react';

const KEY = 'mixpilot.onboarded';

const STEPS = [
  {
    icon: '🎵',
    title: 'Загрузите песню',
    text: 'Перетащите файл в окно или выберите на диске. Ваш оригинал остаётся нетронутым — приложение работает с копией.',
  },
  {
    icon: '✨',
    title: 'Скажите, что хотите',
    text: 'Выберите готовый стиль или напишите обычными словами: «помедленнее и мощнее бас». Разбираться в темпе, тональности и эквалайзере не нужно.',
  },
  {
    icon: '🎧',
    title: 'Получите три варианта',
    text: 'Послушайте, оцените 👍 или 👎 и сохраните. Всё считается на вашем компьютере: музыка и голос никуда не отправляются.',
  },
];

export function onboardingDone(): boolean {
  return localStorage.getItem(KEY) === '1';
}

/** Три шага при первом запуске. Показывается один раз, пропустить можно всегда. */
export function Onboarding({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const current = STEPS[step];
  const last = step === STEPS.length - 1;

  const finish = () => {
    localStorage.setItem(KEY, '1');
    onDone();
  };

  return (
    <div className="screen-inner fade-in" style={{ maxWidth: 620, justifyContent: 'center' }}>
      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 18, textAlign: 'center' }}>
        <div style={{ fontSize: 56, lineHeight: 1 }}>{current.icon}</div>
        <h1 className="h-display" style={{ margin: 0 }}>{current.title}</h1>
        <p className="muted" style={{ margin: 0 }}>{current.text}</p>

        <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
          {STEPS.map((s, i) => (
            <span
              key={s.title}
              style={{
                width: i === step ? 20 : 8,
                height: 8,
                borderRadius: 999,
                background: i === step ? 'var(--accent-a)' : 'var(--surface-2)',
                transition: 'width 200ms ease-out',
              }}
            />
          ))}
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
          <button className="btn-ghost" onClick={finish}>
            Пропустить
          </button>
          <button className="btn btn-primary" onClick={() => (last ? finish() : setStep((s) => s + 1))}>
            {last ? 'Начать' : 'Дальше'}
          </button>
        </div>
      </div>
    </div>
  );
}
