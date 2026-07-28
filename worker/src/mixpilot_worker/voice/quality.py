"""Качество записи голоса: понятный вердикт вместо технических цифр.

Пользователь не должен знать про dBFS и SNR — он должен видеть
«Отлично», «Нормально» или «Перезапишите» и человеческую причину.
"""

from __future__ import annotations

import numpy as np

# Пороги подобраны так, чтобы «Отлично» означало пригодность для голосовой модели.
CLIP_THRESHOLD = 0.985      # выше — сигнал упёрся в потолок
CLIP_RATIO_BAD = 0.005      # доля клипованных сэмплов, при которой слышны искажения
SILENCE_RMS = 0.004         # тише — считаем тишиной
LOW_LEVEL_RMS = 0.02        # слишком тихая запись
GOOD_LEVEL_RMS = 0.05       # комфортный уровень
NOISE_FLOOR_GOOD_DB = -45.0  # тише этого фон не мешает
NOISE_FLOOR_BAD_DB = -30.0   # громче — слышно шипение/гул
# Если самые тихие кадры не тише голоса хотя бы во столько раз, значит пауз в
# записи нет (тянущаяся нота) и фон измерить невозможно.
PAUSE_RATIO = 0.35
# Спектральная плоскость ниже этого — сигнал тональный (нота), а не шум.
TONAL_FLATNESS = 0.10
MIN_SPEECH_S = 1.0
FRAME = 1024


def _mono(audio: np.ndarray) -> np.ndarray:
    a = np.asarray(audio, dtype=np.float32)
    return a.mean(axis=1) if a.ndim > 1 else a


def _is_tonal(samples: np.ndarray) -> bool:
    """Тональный сигнал или шум — по спектральной плоскости (Wiener entropy).

    У ноты энергия собрана в гармониках (плоскость близка к 0), у шума
    размазана по спектру (плоскость близка к 1). Это и отличает тянущуюся
    ноту от фонового гула, когда пауз в записи нет.
    """
    if samples.size < 256:
        return False
    windowed = samples * np.hanning(samples.size)
    spectrum = np.abs(np.fft.rfft(windowed)) ** 2
    spectrum = spectrum[1:]  # без постоянной составляющей
    if spectrum.size == 0 or not np.isfinite(spectrum).all() or spectrum.sum() <= 0:
        return False
    geometric = np.exp(np.mean(np.log(spectrum + 1e-12)))
    arithmetic = float(np.mean(spectrum))
    if arithmetic <= 0:
        return False
    return bool(geometric / arithmetic < TONAL_FLATNESS)


def _frames_of(mono: np.ndarray) -> np.ndarray:
    n = max(1, mono.size // FRAME)
    return mono[: n * FRAME].reshape(n, FRAME)


def _frame_rms(mono: np.ndarray) -> np.ndarray:
    if mono.size < FRAME:
        return np.array([float(np.sqrt(np.mean(mono**2)))] if mono.size else [0.0], dtype=np.float32)
    frames = _frames_of(mono)
    return np.sqrt((frames**2).mean(axis=1))


def _db(value: float) -> float:
    return 20 * float(np.log10(max(value, 1e-9)))


def analyze(audio: np.ndarray, sr: int) -> dict:
    """Разбор одного клипа: уровни, шум, речь. Возвращает вердикт и причину."""
    mono = _mono(audio)
    duration = len(mono) / sr if sr else 0.0
    if mono.size == 0 or duration < 0.2:
        return _verdict("retake", "Записи почти нет — попробуйте ещё раз", duration, {})

    peak = float(np.abs(mono).max())
    rms_frames = _frame_rms(mono)
    speech_frames = rms_frames[rms_frames > SILENCE_RMS]
    speech_ratio = float(speech_frames.size / max(rms_frames.size, 1))
    speech_s = speech_ratio * duration
    voice_rms = float(speech_frames.mean()) if speech_frames.size else 0.0

    # Фон — по самым тихим 10% кадров: там, где человек молчит.
    quiet_idx = np.argsort(rms_frames)[: max(1, rms_frames.size // 10)]
    noise_rms = float(rms_frames[quiet_idx].mean())
    noise_db = _db(noise_rms)

    # Протяжная гласная или длинная нота звучит без пауз: «тихие» кадры —
    # это сам голос. Отличаем такой случай от гула по тональности спектра,
    # иначе хорошая длинная нота отвергалась бы как «шумная».
    quiet_samples = _frames_of(mono)[quiet_idx].reshape(-1) if rms_frames.size > 1 else mono
    quiet_is_tone = noise_rms >= voice_rms * PAUSE_RATIO and _is_tonal(quiet_samples)
    has_pauses = voice_rms > 0 and not quiet_is_tone
    clip_ratio = float((np.abs(mono) >= CLIP_THRESHOLD).mean())

    metrics = {
        "duration_s": round(duration, 2),
        "speech_s": round(speech_s, 2),
        "peak_db": round(_db(peak), 1),
        "voice_db": round(_db(voice_rms), 1),
        "noise_db": round(noise_db, 1),
        "clip_ratio": round(clip_ratio, 4),
        # Насколько голос громче фона — главный показатель пригодности.
        "snr_db": round(_db(voice_rms) - noise_db, 1) if voice_rms > 0 else 0.0,
        "has_pauses": bool(has_pauses),
    }

    # Причины «перезаписать» — по убыванию серьёзности.
    if speech_s < MIN_SPEECH_S:
        return _verdict("retake", "Не слышно голоса — говорите ближе к микрофону", duration, metrics)
    if clip_ratio > CLIP_RATIO_BAD:
        return _verdict("retake", "Слишком громко — звук искажается. Отодвиньтесь от микрофона", duration, metrics)
    if voice_rms < LOW_LEVEL_RMS:
        return _verdict("retake", "Очень тихо — говорите громче или ближе", duration, metrics)
    # Шум оцениваем только если в записи были паузы (см. has_pauses выше).
    if has_pauses and noise_db > NOISE_FLOOR_BAD_DB:
        return _verdict("retake", "Много фонового шума — закройте окно и выключите вентилятор", duration, metrics)

    noisy = has_pauses and noise_db > NOISE_FLOOR_GOOD_DB
    if noisy or voice_rms < GOOD_LEVEL_RMS or clip_ratio > 0:
        hint = "Немного шумно" if noisy else "Можно чуть громче"
        return _verdict("ok", hint, duration, metrics)
    return _verdict("great", "Отличная запись", duration, metrics)


def _verdict(level: str, reason: str, duration: float, metrics: dict) -> dict:
    labels = {"great": "Отлично", "ok": "Нормально", "retake": "Перезапишите"}
    return {
        "level": level,
        "label_ru": labels[level],
        "reason_ru": reason,
        "accepted": level != "retake",
        "duration_s": round(duration, 2),
        "metrics": metrics,
    }


def measure_noise_floor(audio: np.ndarray, sr: int) -> dict:
    """Шаг «помолчите 5 секунд»: насколько тихо в комнате."""
    mono = _mono(audio)
    if mono.size == 0:
        return {"level": "retake", "label_ru": "Перезапишите", "reason_ru": "Тишина не записалась",
                "accepted": False, "noise_db": -99.0}
    noise_db = _db(float(np.sqrt(np.mean(mono**2))))
    if noise_db > NOISE_FLOOR_BAD_DB:
        return {"level": "retake", "label_ru": "Шумно", "accepted": False, "noise_db": round(noise_db, 1),
                "reason_ru": "В комнате шумно — закройте окно, выключите вентилятор и кондиционер"}
    if noise_db > NOISE_FLOOR_GOOD_DB:
        return {"level": "ok", "label_ru": "Терпимо", "accepted": True, "noise_db": round(noise_db, 1),
                "reason_ru": "Небольшой фон есть, но записывать можно"}
    return {"level": "great", "label_ru": "Тихо", "accepted": True, "noise_db": round(noise_db, 1),
            "reason_ru": "В комнате тихо — отлично для записи"}


def trim_silence(audio: np.ndarray, sr: int, keep_ms: float = 120.0) -> np.ndarray:
    """Убираем паузы по краям, оставляя небольшой запас."""
    mono = _mono(audio)
    rms = _frame_rms(mono)
    loud = np.flatnonzero(rms > SILENCE_RMS)
    if loud.size == 0:
        return np.asarray(audio, dtype=np.float32)
    keep = int(keep_ms * 0.001 * sr)
    start = max(0, int(loud[0]) * FRAME - keep)
    end = min(len(mono), (int(loud[-1]) + 1) * FRAME + keep)
    audio = np.asarray(audio, dtype=np.float32)
    return audio[start:end]


def normalize_peak(audio: np.ndarray, target_db: float = -3.0) -> np.ndarray:
    """Приводим клипы к одному уровню, чтобы датасет был ровным."""
    a = np.asarray(audio, dtype=np.float32)
    peak = float(np.abs(a).max()) if a.size else 0.0
    if peak <= 1e-6:
        return a
    target = 10 ** (target_db / 20)
    return (a * (target / peak)).astype(np.float32)
