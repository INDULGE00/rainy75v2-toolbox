"""Import a user-supplied animated GIF as the character, frame by frame.

Each frame is de-backgrounded (or keeps its own alpha), then all frames are
cropped to one shared bounding box so the character never jumps between frames.
SPDX-License-Identifier: MIT.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image

# Safety cap for pathological inputs only -- NOT a sampling target.
# Every source frame is kept whenever the encoded 320x172 S1 GIF fits the 4 MiB
# protocol limit; see studio.py, which only samples down when that limit is hit.
MAX_FRAMES = 300


def durations_of(path):
    with Image.open(path) as g:
        out = []
        for i in range(g.n_frames):
            g.seek(i)
            out.append(int(g.info.get('duration') or 100))
        return out


def sample_timing(path, max_frames=MAX_FRAMES):
    """Keep the ORIGINAL loop duration after frame sampling.

    Earlier code used the average source-frame duration for every output frame,
    so sampling 60 frames down to 48 also shortened the whole loop by 20%.
    Here each output frame inherits total_ms / output_frames instead.
    """
    with Image.open(path) as g:
        n = g.n_frames
        durs = []
        for i in range(n):
            g.seek(i)
            d = int(g.info.get('duration') or 0)
            durs.append(d if 10 <= d <= 2000 else 100)   # discard broken / zero delays
    cap = MAX_FRAMES if max_frames is None else max(1, int(max_frames))
    count = min(n, cap)
    total = sum(durs)
    return {'sourceFrames': n, 'outputFrames': count, 'totalMs': total,
            'perFrameMs': total / max(1, count)}


def load_gif_frames(path, max_frames=MAX_FRAMES, remove_bg=True, threshold=225):
    path = Path(path)
    cap = MAX_FRAMES if max_frames is None else max(1, int(max_frames))
    with Image.open(path) as g:
        n = g.n_frames
        if n < 1:
            raise ValueError('GIF 没有可读取的帧')
        if n > cap:
            idx = [round(i * (n - 1) / (cap - 1)) for i in range(cap)] if cap > 1 else [0]
        else:
            idx = list(range(n))
        raw = []
        for i in idx:
            g.seek(i)
            raw.append(g.convert('RGBA'))
    from character import remove_white_safe, remove_background
    sprites = []
    for frame in raw:
        alpha = frame.getchannel('A')
        if alpha.getextrema()[0] < 250:      # already transparent, keep as-is
            sprites.append(frame)
        elif remove_bg:
            sprites.append(remove_background(frame.convert('RGB'), threshold=threshold))
        else:                               # user opted out: keep every original pixel
            sprites.append(frame)
    boxes = [s.getchannel('A').getbbox() for s in sprites]
    boxes = [b for b in boxes if b]
    if not boxes:
        raise ValueError('GIF 里没有可见的角色')
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    w, h = x1 - x0, y1 - y0
    out = []
    for s in sprites:
        canvas = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        canvas.paste(s, (-x0, -y0))
        out.append(canvas)
    return out
