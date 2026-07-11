"""Темп, битовая сетка и downbeats (фаза по басовой энергии, допущение 4/4)."""

import numpy as np

BPM_MIN, BPM_MAX = 70.0, 180.0


def fold_bpm(bpm: float) -> float:
    """Приводим half/double-time в диапазон 70–180."""
    if bpm <= 0:
        return 0.0
    while bpm < BPM_MIN:
        bpm *= 2
    while bpm > BPM_MAX:
        bpm /= 2
    return bpm


def analyze(y: np.ndarray, sr: int) -> dict:
    import librosa

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, trim=False)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    bpm = fold_bpm(float(np.atleast_1d(tempo)[0]))

    duration = len(y) / sr
    expected_beats = duration * bpm / 60 if bpm > 0 else 1
    coverage = min(1.0, len(beat_times) / max(expected_beats, 1))

    # Downbeats: сдвиг фазы, максимизирующий басовую onset-энергию каждого 4-го бита.
    phase = 0
    if len(beat_frames) >= 8:
        # n_mels под узкую полосу, иначе librosa ругается на пустые mel-фильтры
        bass_env = librosa.onset.onset_strength(y=y, sr=sr, fmax=160, n_mels=24)
        idx = np.clip(beat_frames, 0, len(bass_env) - 1)
        at_beats = bass_env[idx]
        phase = int(np.argmax([at_beats[k::4].sum() for k in range(4)]))
    downbeat_times = beat_times[phase::4]

    return {
        "bpm": round(bpm, 2),
        "bpm_conf": round(float(coverage), 2),
        "beats": [round(float(t), 4) for t in beat_times],
        "downbeats": [round(float(t), 4) for t in downbeat_times],
    }
