"""Обложка трека: рисуем локально из его же волны.

Картиночную нейросеть (SDXL) в MVP не берём: она весит ~7 ГБ, делит те же
8 ГБ VRAM с Demucs и seed-vc и добавляет минуты ожидания ради украшения.
Вместо этого обложка строится из настоящих данных трека — волны, темпа и
энергии, — поэтому у каждого варианта она своя и появляется мгновенно.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

log = logging.getLogger("mixpilot.artwork")

SIZE = 1000
# Палитра Aurora Noir из дизайн-системы, по акценту на стиль.
BG = (10, 11, 16)
STYLE_COLORS = {
    "slowed":       ((124, 92, 255), (79, 209, 255)),    # фиолетовый → голубой
    "bass_boosted": ((255, 92, 138), (124, 92, 255)),    # малиновый → фиолетовый
    "phonk":        ((236, 72, 153), (30, 30, 46)),      # неон на чёрном
    "club":         ((79, 209, 255), (34, 197, 94)),     # голубой → зелёный
    "house":        ((255, 176, 32), (255, 92, 138)),    # янтарь → розовый
}
DEFAULT_COLORS = ((124, 92, 255), (79, 209, 255))

FONT_CANDIDATES = (
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
)


def _font(size: int):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    # Без системных шрифтов обложка всё равно должна получиться.
    return ImageFont.load_default(size)


def _lerp(a: tuple, b: tuple, t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient(c1: tuple, c2: tuple) -> Image.Image:
    """Диагональная заливка — рисуем мелко и растягиваем, так быстрее."""
    small = Image.new("RGB", (64, 64))
    px = small.load()
    for y in range(64):
        for x in range(64):
            px[x, y] = _lerp(c1, c2, (x + y) / 126)
    return small.resize((SIZE, SIZE), Image.BICUBIC)


def _glow(colors: tuple, energy: float) -> Image.Image:
    """Мягкое свечение позади волны: чем энергичнее трек, тем ярче."""
    layer = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    draw = ImageDraw.Draw(layer)
    radius = int(SIZE * (0.26 + 0.10 * energy))
    peak = _lerp((0, 0, 0), colors[0], 0.55 + 0.35 * energy)
    for i in range(7):
        t = i / 6
        r = int(radius * (0.6 + t * 1.4))
        # От центра к краю свечение гаснет — складываем от тусклого к яркому.
        draw.ellipse([SIZE // 2 - r, SIZE // 2 - r, SIZE // 2 + r, SIZE // 2 + r],
                     fill=_lerp(peak, (0, 0, 0), t**0.7))
    return layer.filter(ImageFilter.GaussianBlur(SIZE // 10))


def _vignette() -> Image.Image:
    """Затемнение к краям и особенно к низу — чтобы название всегда читалось."""
    mask = Image.new("L", (128, 128), 0)
    px = mask.load()
    for y in range(128):
        for x in range(128):
            dx, dy = (x - 63.5) / 63.5, (y - 63.5) / 63.5
            edge = min(1.0, (dx * dx + dy * dy) ** 0.5 / 1.25)
            bottom = max(0.0, (y / 127 - 0.55) / 0.45)
            px[x, y] = int(255 * min(1.0, 0.55 * edge**1.6 + 0.55 * bottom**1.4))
    return mask.resize((SIZE, SIZE), Image.BICUBIC)


def _ring(draw: ImageDraw.ImageDraw, peaks: list[float], colors: tuple, energy: float) -> None:
    """Волна трека по кругу — «отпечаток» именно этой песни."""
    cx = cy = SIZE / 2
    inner = SIZE * 0.27
    span = SIZE * (0.12 + 0.10 * energy)
    n = max(len(peaks), 1)
    width = max(3, int(SIZE / n * 0.62))
    for i, value in enumerate(peaks):
        angle = 2 * math.pi * i / n - math.pi / 2
        length = inner + span * max(0.06, min(1.0, value))
        # К краю штрих светлеет — так кольцо читается и на тёмном фоне.
        color = _lerp(_lerp(colors[0], colors[1], i / n), (255, 255, 255), 0.25)
        draw.line(
            [cx + math.cos(angle) * inner, cy + math.sin(angle) * inner,
             cx + math.cos(angle) * length, cy + math.sin(angle) * length],
            fill=color, width=width,
        )


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start: int) -> tuple:
    size = start
    while size > 28:
        font = _font(size)
        if draw.textlength(text, font=font) <= max_width:
            return font, size
        size -= 4
    return _font(28), 28


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        probe = f"{current} {word}".strip()
        if draw.textlength(probe, font=font) <= max_width or not current:
            current = probe
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:2]


def _energy_of(peaks: list[float]) -> float:
    if not peaks:
        return 0.5
    return max(0.0, min(1.0, sum(peaks) / len(peaks) * 1.6))


def render_cover(title: str, subtitle: str, peaks: list[float], style: str, out_path: Path) -> Path:
    """Собирает PNG 1000×1000 и возвращает путь."""
    colors = STYLE_COLORS.get(style, DEFAULT_COLORS)
    energy = _energy_of(peaks)

    # Приглушённый градиент как основа, поверх — свечение (складываем, а не
    # смешиваем: смешивание гасило цвет и делало фон грязным), затем виньетка.
    base = Image.blend(Image.new("RGB", (SIZE, SIZE), BG), _gradient(*colors), 0.42)
    image = ImageChops.add(base, _glow(colors, energy))
    image = Image.composite(Image.new("RGB", (SIZE, SIZE), BG), image, _vignette())

    draw = ImageDraw.Draw(image)
    _ring(draw, peaks[:180] or [0.5] * 120, colors, energy)

    margin = int(SIZE * 0.08)
    max_width = SIZE - 2 * margin
    title = (title or "Без названия").strip()
    font, size = _fit_text(draw, title, max_width, 92)
    lines = _wrap(draw, title, font, max_width) if size <= 28 else [title]

    y = SIZE - margin - len(lines) * int(size * 1.15) - (46 if subtitle else 0)
    for line in lines:
        # Тень под текстом: на светлом участке градиента белое иначе теряется.
        draw.text((margin + 3, y + 3), line, font=font, fill=(0, 0, 0))
        draw.text((margin, y), line, font=font, fill=(255, 255, 255))
        y += int(size * 1.15)
    if subtitle:
        small = _font(34)
        draw.text((margin + 2, y + 8), subtitle, font=small, fill=(0, 0, 0))
        draw.text((margin, y + 6), subtitle, font=small, fill=(226, 228, 240))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, "PNG", optimize=True)
    return out_path


def peaks_from_file(path: Path) -> list[float]:
    """Пики варианта уже посчитаны при рендере — берём их, а не аудио."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return [float(v) for v in doc.get("peaks", [])]
    except (OSError, ValueError):
        log.warning("не удалось прочитать пики для обложки: %s", path)
        return []
