"""Базовый конвейер стиля: per-стем DSP → микс → темп/питч → мастеринг.

Стиль описывается набором параметров (StyleParams) на каждый из 3 вариантов;
конкретные стили (slowed, bass_boosted) задают базу и разброс по вариантам,
плюс human-описание различий. Правки (M4) меняют те же параметры.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from ..mixkit import SR, dynamics, eq, loudness, mixdown, reverb, saturate
from ..timepitch import stretcher

STEM_ORDER = ("vocals", "drums", "bass", "other")


@dataclass
class StyleParams:
    tempo_factor: float = 1.0
    pitch_semitones: float = 0.0
    gain_db: dict[str, float] = field(default_factory=dict)   # per-стем усиление
    bass_shelf_db: float = 0.0       # low-shelf на басовом стеме
    bass_drive_db: float = 0.0       # сатурация баса (0 = выкл)
    kick_boost_db: float = 0.0       # пик ~70 Гц на барабанах
    vocal_reverb: float = 0.0        # 0..1 влажность вокала
    air_db: float = 0.0              # high-shelf на мастере (воздух/яркость)
    sub_db: float = 0.0              # low-shelf на мастере (суббас)
    warmth_db: float = 0.0           # лёгкий срез верха на мастере (< 0)
    comp_threshold_db: float = -18.0
    comp_ratio: float = 2.0
    target_loudness: str = "stream"  # 'stream' | 'club'
    ceiling_db: float = -1.0

    def to_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StyleParams":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


def _process_stem(name: str, audio: np.ndarray, p: StyleParams) -> np.ndarray:
    x = mixdown.to_stereo(audio)
    g = p.gain_db.get(name, 0.0)
    if abs(g) > 1e-6:
        x = mixdown.apply_gain(x, g)
    if name == "bass":
        sos = []
        if abs(p.bass_shelf_db) > 1e-6:
            sos.append(eq.low_shelf(110, p.bass_shelf_db))
        if sos:
            x = eq.apply(x, sos)
        if p.bass_drive_db > 1e-6:
            x = saturate.saturate(x, drive_db=p.bass_drive_db, mix=0.6)
    elif name == "drums" and abs(p.kick_boost_db) > 1e-6:
        x = eq.apply(x, [eq.peaking(70, p.kick_boost_db, q=1.2)])
    elif name == "vocals" and p.vocal_reverb > 1e-4:
        x = reverb.reverb(x, mix=p.vocal_reverb, room=0.6, damp=0.45)
    return x


def _master(mixed: np.ndarray, p: StyleParams, progress=None) -> np.ndarray:
    sos = []
    if abs(p.sub_db) > 1e-6:
        sos.append(eq.low_shelf(80, p.sub_db))
    if abs(p.warmth_db) > 1e-6:
        sos.append(eq.high_shelf(8000, p.warmth_db))
    if abs(p.air_db) > 1e-6:
        sos.append(eq.high_shelf(10000, p.air_db))
    x = eq.apply(mixed, sos) if sos else mixed
    x = dynamics.compressor(x, threshold_db=p.comp_threshold_db, ratio=p.comp_ratio,
                            attack_ms=15, release_ms=150)
    target = loudness.TARGET_LUFS.get(p.target_loudness, -11.0)
    x = loudness.normalize_lufs(x, target_lufs=target)
    x = dynamics.limiter(x, ceiling_db=p.ceiling_db)
    return x


def render(stems: dict[str, np.ndarray], params: StyleParams, sr: int = SR, progress=None) -> np.ndarray:
    """Полный рендер варианта: обработка стемов → микс → темп/питч → мастеринг."""
    if progress:
        progress(0.05)
    processed = [_process_stem(name, stems[name], params) for name in STEM_ORDER if name in stems]
    if progress:
        progress(0.35)
    mixed = mixdown.mix(processed)

    if abs(params.tempo_factor - 1.0) > 1e-3 or abs(params.pitch_semitones) > 1e-3:
        mixed = stretcher.stretch(mixed, sr, params.tempo_factor, params.pitch_semitones)
    if progress:
        progress(0.7)

    out = _master(mixed, params)
    if progress:
        progress(0.95)
    return out


def with_edits(base: StyleParams, **changes) -> StyleParams:
    return replace(base, **changes)
