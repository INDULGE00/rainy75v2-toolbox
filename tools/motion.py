"""Gentle body motion only. SPDX-License-Identifier: MIT.

Deliberately draws nothing on the character: no fake faces, no fake hands, no
overlaid effects. When a real animated GIF is supplied, studio mode switches
to frame-by-frame playback instead (see gifclip.py / draw_character).
"""
from __future__ import annotations
import math
from PIL import Image, ImageDraw

_STEP = 6


def _blank(size):
    return Image.new('RGBA', size, (0, 0, 0, 0))


def _shear(im, y0, y1, amp, top=False):
    """Shift horizontal bands progressively. Continuous -> no visible seams."""
    if not amp:
        return im
    out = im.copy()
    y1 = min(y1, im.height)
    span = max(1, y1 - y0)
    for y in range(y0, y1, _STEP):
        y2 = min(y + _STEP, y1)
        k = 1.0 - (y - y0) / span if top else (y - y0) / span
        dx = int(round(amp * (k if top else k * k)))
        if not dx:
            continue
        band = im.crop((0, y, im.width, y2))
        shifted = _blank(band.size)
        shifted.paste(band, (dx, 0))
        out.paste(_blank(band.size), (0, y))
        out.paste(shifted, (0, y), shifted)
    return out


def _transform(sprite, f):
    im = sprite.copy()
    w, h = im.size
    ratio = w / 460.0
    im = _shear(im, int(h * 0.58), h, f.get('sway', 0) * ratio)
    im = _shear(im, 0, int(h * 0.14), f.get('ahoge', 0) * ratio, top=True)
    tilt = f.get('tilt', 0)
    if tilt:
        im = im.rotate(tilt, resample=Image.Resampling.BICUBIC, expand=False)
    return im


def pose(phase, total, views=1):
    """Small, natural body motion only."""
    p = phase % max(1, total)
    t = p / max(1, total)
    breath = math.sin(2 * math.pi * p / 8.0)
    f = dict(view=0, bob=round(1.0 * breath), tilt=0, squash=1.0 + 0.010 * breath,
             sway=1.5 * math.sin(2 * math.pi * p / 14.0),
             ahoge=1.2 * math.sin(2 * math.pi * p / 11.0), jump=0, dx=0)
    if 0.22 <= t < 0.45:                        # gentle side-to-side sway
        k = (t - 0.22) / 0.23
        f['tilt'] = 3.5 * math.sin(k * math.pi * 2)
        f['dx'] = round(2 * math.sin(k * math.pi * 2))
        f['sway'] = 3.5 * math.sin(k * math.pi * 2)
    elif 0.58 <= t < 0.76:                      # tiny hop
        k = (t - 0.58) / 0.18
        f['jump'] = round(-4 * math.sin(k * math.pi))
        f['squash'] = 1.0 - 0.025 * math.sin(k * math.pi)
        f['ahoge'] = 3.0 * math.sin(k * math.pi * 2)
    return f


def draw(im, theme, phase, cfg, sprites, box):
    """Paste the character with gentle body motion; never draw on the face."""
    motion = (cfg.get('motion') or {})
    total = int(cfg.get('frameCount') or motion.get('frames') or 8)
    f = pose(phase, total, len(sprites))
    sprite = sprites[phase % len(sprites)]
    x0, y0, x1, y1 = [int(v) for v in box]
    scale = float(cfg.get('scale', 1.0)) * f['squash']
    ratio = min((x1 - x0) / sprite.width, (y1 - y0) / sprite.height) * scale
    width = max(1, round(sprite.width * ratio))
    height = max(1, round(sprite.height * ratio))
    view = _transform(sprite, f).resize((width, height), Image.Resampling.LANCZOS)
    px = x0 + ((x1 - x0) - width) // 2 + f['dx']
    py = y1 - height + f['bob'] + int(cfg.get('offsetY', 0)) + f['jump']
    d = ImageDraw.Draw(im)
    if cfg.get('shadow', True):
        d.ellipse((x0 + 6, y1 - 6, x1 - 6, y1 + 4), fill=theme['shell'])
    im.paste(view, (px, py), view)


def frame_count(cfg):
    return int(cfg.get('frameCount') or (cfg.get('motion') or {}).get('frames') or 8)
