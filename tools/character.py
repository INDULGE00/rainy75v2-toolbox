"""Character sprite helpers for the local customization studio. SPDX-License-Identifier: MIT.

Everything written by this module lives under ``local/`` (git-ignored), so private
character artwork never becomes a release source.
"""
from __future__ import annotations
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'local'
VIEWS_DIR = LOCAL / 'views'
CONFIG = LOCAL / 'character.json'
VIEW_NAMES = ('front', 'side', 'back')


def detect_views(im: Image.Image, threshold: int = 28, min_gap: int = 8):
    """Split a white-background character sheet into 1..3 views by column projection."""
    rgb = im.convert('RGB')
    w, h = rgb.size
    diff = ImageChops.difference(rgb, Image.new('RGB', (w, h), (255, 255, 255))).convert('L')
    mask = diff.point(lambda v: 255 if v > threshold else 0)
    small = mask.resize((w, max(1, h // 4)))
    sw, sh = small.size
    cols = [sum(1 for y in range(sh) if small.getpixel((x, y)) > 0) for x in range(sw)]
    gaps, start = [], None
    for x, n in enumerate(cols):
        if n <= 2:
            if start is None:
                start = x
        else:
            if start is not None and x - start >= min_gap:
                gaps.append((start, x))
            start = None
    if start is not None and sw - start >= min_gap:
        gaps.append((start, sw))
    inner = [g for g in gaps if g[0] > 0 and g[1] < w]
    inner.sort(key=lambda g: g[1] - g[0], reverse=True)
    cuts = sorted((a + b) // 2 for a, b in inner[:2])
    bounds = [0] + cuts + [w]
    crops = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a < 32:
            continue
        bb = mask.crop((a, 0, b, h)).getbbox()
        if bb is None:
            continue
        pad = 6
        box = (max(0, a + bb[0] - pad), max(0, bb[1] - pad), min(w, a + bb[2] + pad), min(h, bb[3] + pad))
        crops.append(rgb.crop(box))
    return crops[:3]


def _background_candidates(rgb: Image.Image, threshold: int):
    """Only bright, neutral greys qualify as background.

    Cream / warm whites in the artwork (R noticeably larger than B, e.g. a cream
    sweater 245/238/225) are deliberately excluded so they survive de-backgrounding.
    """
    r, g, b = rgb.split()
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    bright = mn.point(lambda v: 255 if v >= threshold else 0)
    low_sat = ImageChops.subtract(mx, mn).point(lambda v: 255 if v <= 22 else 0)
    neutral = ImageChops.difference(r, b).point(lambda v: 255 if v <= 10 else 0)
    return ImageChops.multiply(ImageChops.multiply(bright, low_sat), neutral)


def remove_white(im: Image.Image, threshold: int = 120, feather: float = 0.6):
    """Aggressive colour-distance flood fill for scanned / JPEG character sheets."""
    rgb = im.convert('RGB')
    w, h = rgb.size
    work = rgb.copy()
    mark = (0, 255, 0)
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    for seed in seeds:
        if work.getpixel(seed) != mark:
            ImageDraw.floodfill(work, seed, mark, thresh=threshold)
    delta = ImageChops.difference(work, Image.new('RGB', (w, h), mark)).convert('L')
    alpha = delta.point(lambda v: 0 if v == 0 else 255)
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    out = rgb.convert('RGBA')
    out.putalpha(alpha)
    bb = alpha.getbbox()
    return out.crop(bb) if bb else out


def remove_white_safe(im: Image.Image, threshold: int = 225, feather: float = 0.6):
    """Conservative GIF de-backgrounding.

    Only neutral bright pixels connected to the border are removed, so cream /
    warm whites and white clothing inside the character are never mistaken for
    background (the old colour-distance fill ate them).
    """
    rgb = im.convert('RGB')
    w, h = rgb.size
    mask = _background_candidates(rgb, threshold)
    pixels = mask.load()
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    for seed in seeds:
        if pixels[seed] == 255:
            ImageDraw.floodfill(mask, seed, 128, thresh=0)
    alpha = mask.point(lambda v: 0 if v == 128 else 255)
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    out = rgb.convert('RGBA')
    out.putalpha(alpha)
    bb = alpha.getbbox()
    return out.crop(bb) if bb else out


def prepare(im: Image.Image, split: bool = True):
    """Return a list of transparent RGBA sprites, one per detected view."""
    if im.mode in ('RGBA', 'LA') and im.getchannel('A').getextrema()[0] < 250:
        return [im.convert('RGBA')]  # already transparent, use as a single view
    views = detect_views(im) if split else [im.convert('RGB')]
    if not views:
        raise ValueError('No character found in the image')
    return [remove_white(v) for v in views]


def save_sprites(sprites):
    VIEWS_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, sprite in enumerate(sprites):
        name = VIEW_NAMES[i] if i < len(VIEW_NAMES) else f'view{i}'
        path = VIEWS_DIR / f'{name}.png'
        sprite.save(path)
        paths.append(path)
    return paths


def default_config(sprites, theme='ocean', name='自定义角色'):
    n = len(sprites)
    seq = ([0] * 2 + [1] * 2 + [2] * 2 + [1] * 2) if n >= 3 else ([0, 0, 1, 1, 0, 0, 1, 1] if n == 2 else [0] * 8)
    files = []
    for i in range(n):
        stem = VIEW_NAMES[i] if i < len(VIEW_NAMES) else f'view{i}'
        files.append((VIEWS_DIR / stem).with_suffix('.png').relative_to(ROOT).as_posix())
    return {
        'enabled': True,
        'name': name,
        'theme': theme,
        'files': files,
        'sequence': seq,
        'box': [188, 42, 300, 154],
        'scale': 1.0,
        'offsetY': 0,
        'bob': [0, 0, -1, -1, 0, 1, 1, 0],
        'shadow': True,
        'duration': 160,
    }


def load_config():
    if not CONFIG.exists():
        return None
    try:
        return json.loads(CONFIG.read_text(encoding='utf8'))
    except (ValueError, OSError):
        return None


def load_sprites(cfg):
    source = cfg.get('sourceGif')
    if source:
        from gifclip import load_gif_frames
        path = ROOT / source
        if not path.exists():
            raise ValueError('Missing source GIF: ' + source)
        # Upload decides how many frames survive (size-driven sampling). Reuse the
        # exact same sample everywhere so previews / apply / render never shift.
        keep = cfg.get('gifSample') or cfg.get('frameCount')
        kw = {'max_frames': int(keep)} if keep else {}
        return load_gif_frames(path, remove_bg=bool(cfg.get('removeBg', True)), **kw)
    out = []
    for rel in cfg.get('files', []):
        path = ROOT / rel
        if not path.exists():
            raise ValueError('Missing character sprite: ' + rel)
        with Image.open(path) as im:
            out.append(im.convert('RGBA'))
    if not out:
        raise ValueError('Character config has no sprites')
    return out

def _flat_background(rgb: Image.Image, tolerance: int = 24):
    """Mask of pixels matching a flat border colour (cyan, grey, white...).

    Samples the outermost ring, keeps colours that cover a meaningful part of
    it, marks every pixel within ``tolerance`` of one of them, then keeps only
    the region connected to the border so same-coloured artwork survives.
    """
    w, h = rgb.size
    from collections import Counter
    ring = Counter()
    step = max(1, min(w, h) // 64)
    for x in range(0, w, step):
        ring[rgb.getpixel((x, 0))] += 1
        ring[rgb.getpixel((x, h - 1))] += 1
    for y in range(0, h, step):
        ring[rgb.getpixel((0, y))] += 1
        ring[rgb.getpixel((w - 1, y))] += 1
    total = sum(ring.values()) or 1
    colours = [c for c, n in ring.most_common(4) if n / total >= 0.08][:2]
    if not colours:
        return None
    mask = Image.new('L', (w, h), 0)
    bands = rgb.split()
    for colour in colours:
        dist = None
        for band, value in zip(bands, colour):
            delta = ImageChops.difference(band, Image.new('L', (w, h), value))
            dist = delta if dist is None else ImageChops.lighter(dist, delta)
        hit = dist.point(lambda v: 255 if v <= tolerance else 0)
        mask = ImageChops.lighter(mask, hit)
    pixels = mask.load()
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    linked = Image.new('L', (w, h), 0)
    linked.paste(mask)
    for seed in seeds:
        if pixels[seed] == 255:
            ImageDraw.floodfill(linked, seed, 128, thresh=0)
    return linked


def remove_flat_bg(im: Image.Image, tolerance: int = 80, feather: float = 0.5):
    """Remove a flat coloured background (e.g. a cyan studio backdrop)."""
    rgb = im.convert('RGB')
    mask = _flat_background(rgb, tolerance)
    if mask is None:
        return im.convert('RGBA')
    alpha = mask.point(lambda v: 0 if v == 128 else 255)
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    out = rgb.convert('RGBA')
    out.putalpha(alpha)
    bb = alpha.getbbox()
    return out.crop(bb) if bb else out


def remove_background(im: Image.Image, threshold: int = 225):
    """Pick the right de-backgrounding pass for one GIF frame.

    Neutral-white backdrops keep the conservative white remover (it protects
    cream/white clothing); anything else (cyan, grey, photo-ish flats) falls
    back to the border-colour flood fill.
    """
    cut = remove_white_safe(im, threshold=threshold)
    if cut.getchannel('A').getbbox() is None:
        return cut
    hist = cut.getchannel('A').histogram()
    opaque = sum(hist[250:])
    if opaque >= 0.97 * (cut.width * cut.height):
        alt = remove_flat_bg(im)
        if alt.getchannel('A').getbbox() is not None:
            return alt
    return cut
