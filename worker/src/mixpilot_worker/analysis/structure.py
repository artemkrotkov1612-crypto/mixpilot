"""Структура трека: границы по novelty, кластеры по хроме, лейблы по правилам.

Сознательная замена All-in-One: его зависимость NATTEN не ставится на Windows
без MSVC+CUDA-toolchain (см. 01_DOCS/MODELS.md). Эвристика даёт разумные блоки
для пересборки; границы привязываются к downbeat'ам.
"""

import numpy as np

MIN_SEGMENT_S = 7.0
SIM_THRESHOLD = 0.90  # косинусная близость хромы для объединения в один кластер

LABELS = ("intro", "verse", "chorus", "bridge", "drop", "outro")


def _snap(value: float, grid: list[float]) -> float:
    if not grid:
        return value
    arr = np.asarray(grid)
    return float(arr[np.argmin(np.abs(arr - value))])


def _cluster(features: list[np.ndarray]) -> list[int]:
    """Жадная кластеризация сегментов по косинусной близости средних хром."""
    labels: list[int] = []
    centroids: list[np.ndarray] = []
    for feat in features:
        norm = np.linalg.norm(feat)
        vec = feat / norm if norm > 0 else feat
        best, best_sim = -1, SIM_THRESHOLD
        for ci, c in enumerate(centroids):
            sim = float(vec @ c)
            if sim > best_sim:
                best, best_sim = ci, sim
        if best < 0:
            centroids.append(vec)
            labels.append(len(centroids) - 1)
        else:
            centroids[best] = (centroids[best] + vec) / 2
            n = np.linalg.norm(centroids[best])
            if n > 0:
                centroids[best] /= n
            labels.append(best)
    return labels


def analyze(y: np.ndarray, sr: int, downbeats: list[float], beats: list[float]) -> list[dict]:
    import librosa

    duration = len(y) / sr
    hop = 512

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    feats = np.vstack([
        chroma / (chroma.max() + 1e-9),
        mfcc / (np.abs(mfcc).max() + 1e-9),
    ])

    # Число сегментов по длительности: ~1 на 25 секунд, от 3 до 12.
    k = int(np.clip(round(duration / 25), 3, 12))
    n_frames = feats.shape[1]
    if n_frames < k * 4:
        k = max(2, n_frames // 4)

    bound_frames = librosa.segment.agglomerative(feats, k)
    bound_times = librosa.frames_to_time(bound_frames, sr=sr, hop_length=hop)

    # Привязка к downbeat'ам + фильтр коротышей.
    snapped: list[float] = [0.0]
    for t in bound_times[1:]:
        s = _snap(float(t), downbeats or beats)
        if s - snapped[-1] >= MIN_SEGMENT_S and duration - s >= MIN_SEGMENT_S / 2:
            snapped.append(s)
    edges = snapped + [duration]

    # Фичи сегментов: средняя хрома (кластеры) и RMS-энергия (лейблы).
    seg_chroma: list[np.ndarray] = []
    seg_energy: list[float] = []
    times = librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=hop)
    for a, b in zip(edges[:-1], edges[1:]):
        mask = (times >= a) & (times < b)
        seg_chroma.append(chroma[:, mask].mean(axis=1) if mask.any() else np.zeros(12))
        idx = np.clip((np.array([a, b]) * sr / hop).astype(int), 0, len(rms) - 1)
        seg_energy.append(float(rms[idx[0]:max(idx[1], idx[0] + 1)].mean()))

    clusters = _cluster(seg_chroma)
    energy = np.asarray(seg_energy)
    energy_norm = energy / (energy.max() + 1e-9)

    # Лейблы: самый «тяжёлый» повторяющийся кластер — припев; следующий — куплет.
    n = len(clusters)
    weights: dict[int, float] = {}
    for i, c in enumerate(clusters):
        weights[c] = weights.get(c, 0.0) + (edges[i + 1] - edges[i]) * (0.5 + energy_norm[i])
    order = sorted(weights, key=lambda c: -weights[c])
    chorus_cluster = order[0] if order else -1
    verse_cluster = order[1] if len(order) > 1 else -1

    labels: list[str] = []
    for i, c in enumerate(clusters):
        if c == chorus_cluster:
            labels.append("chorus")
        elif c == verse_cluster:
            labels.append("verse")
        elif energy_norm[i] >= 0.85:
            labels.append("drop")
        else:
            labels.append("bridge")
    if n > 0 and energy_norm[0] <= 0.9:
        labels[0] = "intro"
    if n > 1 and labels[-1] != "chorus":
        labels[-1] = "outro"

    beats_arr = np.asarray(beats) if beats else np.asarray([0.0])
    counters: dict[str, int] = {}
    sections: list[dict] = []
    for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
        label = labels[i]
        counters[label] = counters.get(label, 0) + 1
        sections.append({
            "id": f"{label}{counters[label]}",
            "label": label,
            "start_s": round(a, 3),
            "end_s": round(b, 3),
            "start_beat": int(np.searchsorted(beats_arr, a)),
            "end_beat": int(np.searchsorted(beats_arr, b)),
            "energy": round(float(energy_norm[i]), 3),
        })
    return sections
