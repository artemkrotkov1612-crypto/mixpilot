import { useEffect, useRef, useState } from 'react';
import { ApiError, api, postBinary } from '../api/client';
import type { ClipQuality, VoiceProfile, VoiceStep } from '../api/types';
import { MicrophoneError, startRecording, type Recorder } from '../lib/recorder';
import { useEngine } from '../state/engine';
import { useScreens } from '../state/screens';
import { toast } from '../state/toasts';

type ClipResult = { quality: ClipQuality; saved: boolean };

export function VoiceScreen() {
  const go = useScreens((s) => s.go);
  const online = useEngine((s) => s.state.kind === 'online');

  const [steps, setSteps] = useState<VoiceStep[]>([]);
  const [estimate, setEstimate] = useState(0);
  const [profile, setProfile] = useState<VoiceProfile | null>(null);
  const [stepIdx, setStepIdx] = useState(0);
  const [promptIdx, setPromptIdx] = useState(0);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [level, setLevel] = useState(0);
  const [last, setLast] = useState<ClipResult | null>(null);
  const [finishing, setFinishing] = useState(false);
  const recorderRef = useRef<Recorder | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!online) return;
    void (async () => {
      try {
        const data = await api<{ steps: VoiceStep[]; estimate_minutes: number }>('/voice/steps');
        setSteps(data.steps);
        setEstimate(data.estimate_minutes);
        const list = await api<{ profiles: VoiceProfile[]; active: VoiceProfile | null }>('/voice/profiles');
        const existing = list.profiles.find((p) => p.status === 'recording') ?? list.active;
        if (existing) setProfile(existing);
      } catch {
        toast('Не удалось загрузить мастер голоса', 'err');
      }
    })();
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      recorderRef.current?.cancel();
    };
  }, [online]);

  const refreshProfile = async (id: string) => setProfile(await api<VoiceProfile>(`/voice/profiles/${id}`));

  const beginProfile = async () => {
    setBusy(true);
    try {
      setProfile(await api<VoiceProfile>('/voice/profiles', { json: { name: 'Мой голос' } }));
      setStepIdx(0);
      setPromptIdx(0);
      setLast(null);
    } catch {
      toast('Не удалось создать профиль', 'err');
    } finally {
      setBusy(false);
    }
  };

  const step = steps[stepIdx];
  const prompt = step?.prompts[promptIdx] ?? '';
  const isNoiseStep = step?.kind === 'noise';

  const tickLevel = () => {
    const rec = recorderRef.current;
    if (!rec) return;
    setLevel(rec.level());
    rafRef.current = requestAnimationFrame(tickLevel);
  };

  const record = async () => {
    if (!profile) return;
    try {
      recorderRef.current = await startRecording();
      setRecording(true);
      setLast(null);
      tickLevel();
    } catch (err) {
      toast(err instanceof MicrophoneError ? err.message : 'Не удалось включить микрофон', 'err');
    }
  };

  const stopAndSend = async () => {
    const rec = recorderRef.current;
    if (!rec || !profile) return;
    setRecording(false);
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    setLevel(0);
    setBusy(true);
    try {
      const blob = await rec.stop();
      recorderRef.current = null;
      const url = isNoiseStep
        ? '/voice/noise-check'
        : `/voice/profiles/${profile.id}/clip?step=${step.id}&idx=${promptIdx}`;
      const data = await postBinary<ClipResult | ClipQuality>(url, blob);
      const result: ClipResult = isNoiseStep
        ? { quality: data as ClipQuality, saved: false }
        : (data as ClipResult);
      setLast(result);
      if (result.quality.accepted) await refreshProfile(profile.id);
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Не удалось сохранить запись', 'err');
    } finally {
      setBusy(false);
    }
  };

  const next = () => {
    if (!step) return;
    if (promptIdx + 1 < step.prompts.length) {
      setPromptIdx(promptIdx + 1);
    } else if (stepIdx + 1 < steps.length) {
      setStepIdx(stepIdx + 1);
      setPromptIdx(0);
    }
    setLast(null);
  };

  const finish = async () => {
    if (!profile) return;
    setFinishing(true);
    try {
      const res = await api<{ enough: boolean; reference_s: number }>(`/voice/profiles/${profile.id}/finish`);
      await refreshProfile(profile.id);
      toast(
        res.enough
          ? `Голос готов! Записано ${Math.round(res.reference_s)} секунд эталона`
          : 'Пока мало записей — запишите ещё несколько фрагментов',
        res.enough ? 'ok' : 'err',
      );
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Не удалось собрать голос', 'err');
    } finally {
      setFinishing(false);
    }
  };

  const removeProfile = async () => {
    if (!profile) return;
    if (!window.confirm('Удалить голос вместе со всеми записями? Это нельзя отменить.')) return;
    await api(`/voice/profiles/${profile.id}`, { method: 'DELETE' });
    setProfile(null);
    toast('Голос и записи удалены', 'ok');
  };

  const isLastPrompt =
    step && promptIdx + 1 >= step.prompts.length && stepIdx + 1 >= steps.length;

  return (
    <div className="screen-inner fade-in" style={{ maxWidth: 780 }}>
      <button className="btn-ghost" style={{ alignSelf: 'flex-start' }} onClick={() => go({ name: 'home' })}>
        ‹ Главная
      </button>

      <header>
        <h1 className="h-display">Мой голос</h1>
        <p className="muted">
          {profile?.status === 'ready'
            ? 'Голос готов — можно делать каверы'
            : `Запишем несколько фраз — примерно ${estimate} минут. Записи остаются на вашем компьютере`}
        </p>
      </header>

      {!profile && (
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p className="muted small">
            Мы попросим прочитать несколько фраз и немного попеть. Из лучших фрагментов соберётся ваш голос —
            им можно будет петь любые песни.
          </p>
          <button className="btn btn-primary" style={{ alignSelf: 'flex-start' }} onClick={() => void beginProfile()} disabled={busy}>
            Создать мой голос
          </button>
        </div>
      )}

      {profile && (
        <>
          <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600 }}>
                {profile.status === 'ready' ? 'Голос готов ✓' : 'Записываем голос'}
              </div>
              <div className="muted small">
                Фрагментов: {profile.recorded_clips} · записано {profile.minutes_recorded.toFixed(1)} мин
                {profile.quality?.reference_s ? ` · эталон ${Math.round(profile.quality.reference_s)} с` : ''}
              </div>
            </div>
            <button className="btn btn-secondary" onClick={() => void finish()} disabled={finishing || profile.recorded_clips === 0}>
              {finishing ? 'Собираем…' : profile.status === 'ready' ? 'Пересобрать' : 'Собрать голос'}
            </button>
            <button className="btn-icon" title="Удалить голос" onClick={() => void removeProfile()}>
              🗑
            </button>
          </div>

          {step && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <h2 className="h2">{step.title_ru}</h2>
                <span className="muted small">
                  Шаг {stepIdx + 1} из {steps.length}
                  {step.prompts.length > 1 && ` · фраза ${promptIdx + 1} из ${step.prompts.length}`}
                </span>
              </div>
              <p className="muted small">{step.instruction_ru}</p>

              {prompt && (
                <div
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: 22,
                    lineHeight: '32px',
                    padding: '18px 20px',
                    background: 'var(--surface-2)',
                    borderRadius: 'var(--radius-m)',
                  }}
                >
                  {prompt}
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                {!recording ? (
                  <button className="btn btn-primary" onClick={() => void record()} disabled={busy}>
                    {busy ? 'Проверяем…' : '● Записать'}
                  </button>
                ) : (
                  <button className="btn btn-primary" onClick={() => void stopAndSend()}>
                    ■ Остановить
                  </button>
                )}
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div className="progress-line" style={{ height: 10 }}>
                    <div style={{ width: `${Math.round(level * 100)}%`, transition: 'width 90ms linear' }} />
                  </div>
                  <span className="muted small">
                    {recording ? 'Идёт запись — говорите' : `Примерно ${step.seconds} секунд`}
                  </span>
                </div>
              </div>

              {last && (
                <div
                  className="card"
                  style={{
                    borderColor:
                      last.quality.level === 'great'
                        ? 'rgba(63,220,151,.45)'
                        : last.quality.level === 'ok'
                          ? 'rgba(255,182,72,.45)'
                          : 'rgba(255,93,115,.5)',
                  }}
                >
                  <div style={{ fontWeight: 600 }}>{last.quality.label_ru}</div>
                  <div className="muted small">{last.quality.reason_ru}</div>
                </div>
              )}

              <div style={{ display: 'flex', gap: 10 }}>
                <button className="btn btn-secondary" onClick={next} disabled={recording || busy}>
                  {last?.quality.accepted || isNoiseStep ? 'Дальше' : 'Пропустить'}
                </button>
                {isLastPrompt && (
                  <button className="btn btn-primary" onClick={() => void finish()} disabled={finishing}>
                    Готово — собрать голос
                  </button>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
