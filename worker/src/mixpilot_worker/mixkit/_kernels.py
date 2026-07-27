"""Горячие посэмпловые DSP-циклы, скомпилированные numba (njit).

Отдельный модуль: компиляция один раз при первом вызове, дальше — скорость C.
Все ядра работают с моно float32-массивами; стерео обрабатывается поканально.
"""

import numpy as np
from numba import njit


@njit(cache=True, fastmath=True)
def comp_gain(env_db, threshold_db, ratio, att, rel):
    """Сглаженный gain reduction (дБ) компрессора: быстрая атака, медленный релиз."""
    n = env_db.shape[0]
    out = np.empty(n, dtype=np.float32)
    prev = 0.0
    inv = 1.0 / ratio - 1.0
    for i in range(n):
        over = env_db[i] - threshold_db
        target = over * inv if over > 0.0 else 0.0
        coeff = att if target < prev else rel
        prev = coeff * prev + (1.0 - coeff) * target
        out[i] = prev
    return out


@njit(cache=True, fastmath=True)
def limiter_gain(future_peak, ceiling, rel):
    """Гейн лимитера: мгновенное падение к цели, сглаженный релиз вверх."""
    n = future_peak.shape[0]
    out = np.empty(n, dtype=np.float32)
    prev = 1.0
    for i in range(n):
        t = ceiling / (future_peak[i] + 1e-9)
        if t > 1.0:
            t = 1.0
        prev = t if t < prev else rel * prev + (1.0 - rel) * t
        out[i] = prev
    return out


@njit(cache=True, fastmath=True)
def comb(x, delay, feedback, damp):
    """Гребёнчатый фильтр с ВЧ-затуханием хвоста (Schroeder-Moorer)."""
    n = x.shape[0]
    y = np.empty(n, dtype=np.float32)
    buf = np.zeros(delay, dtype=np.float32)
    idx = 0
    filt = 0.0
    for i in range(n):
        delayed = buf[idx]
        filt = delayed * (1.0 - damp) + filt * damp
        buf[idx] = x[i] + filt * feedback
        y[i] = delayed
        idx += 1
        if idx >= delay:
            idx = 0
    return y


@njit(cache=True, fastmath=True)
def allpass(x, delay, gain):
    n = x.shape[0]
    y = np.empty(n, dtype=np.float32)
    buf = np.zeros(delay, dtype=np.float32)
    idx = 0
    for i in range(n):
        delayed = buf[idx]
        out = -x[i] + delayed
        buf[idx] = x[i] + delayed * gain
        y[i] = out
        idx += 1
        if idx >= delay:
            idx = 0
    return y
