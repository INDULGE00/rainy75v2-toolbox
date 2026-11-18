"""Local character/theme customization studio. SPDX-License-Identifier: MIT.

Only listens on 127.0.0.1. All user artwork and custom themes are written under
``local/`` (git-ignored); the shipped profiles/ sources stay untouched.
Run: python tools/studio.py --port 8766
"""
from __future__ import annotations
import argparse, base64, hashlib, importlib, io, json, math, os, re, shutil, subprocess, sys, threading, time, traceback
from collections import Counter
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# RAINY75_ROOT lets the frozen single-file build point every path at the
# extracted app directory instead of the (read-only) PyInstaller temp dir.
ROOT = Path(os.environ.get('RAINY75_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(ROOT / 'tools'))
os.environ['RAINY75_STUDIO'] = '1'  # must be set before importing assets
import assets  # noqa: E402
import character as charmod  # noqa: E402
from PIL import Image  # noqa: E402

LOCAL = ROOT / 'local'
THEMES_FILE = LOCAL / 'themes.json'
CHAR_FILE = LOCAL / 'character.json'
KEYS_FILE = ROOT / 'profiles' / 'keys.json'
BUILD_IPS = ROOT / 'build' / 'ips'
ASSETS_DIR = BUILD_IPS / 'assets'
STOCK = ROOT / 'inputs' / 'ips-stock.bin'
MAIN_STOCK = ROOT / 'inputs' / 'main-stock.bin'
# Compile inputs are NOT the finished 507,904 B image: the factory extract is
# 502,925 B and build.py verifies it by SHA-256. Accept the exact hash, or the
# full-image sizes when someone dumps the whole flash (build.py will then verify).
IPS_STOCK_SHA = '32defab7902e57eb972a577fc6cbf3a7e57bc772d59b99f11038370412b77f41'
STOCK_ACCEPT = {
    'ips': {'sizes': {502925, 507904}, 'sha': IPS_STOCK_SHA, 'hint': '502,925 B 的原厂提取件'},
    'main': {'sizes': {284492, 294912}, 'sha': None, 'hint': '284,492 B 的原厂提取件'},
}
COLOR_FIELDS = ('background', 'panel', 'shell', 'ink', 'accent')
REQUIRED_COLORS = ('background', 'panel', 'shell', 'ink', 'accent')
LOCK = threading.Lock()
_SERVER = None  # set by serve(); used by /api/quit

# Hard limits shown in the UI. The S1 slot uses the project's cache-GIF protocol:
# 320x172 full opaque frames, disposal=1, and <=4 MiB total (validateGif / build.py).
SCREEN_W, SCREEN_H = 320, 172
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
# Device external Flash varies between batches; 4 MiB is the documented default.
# Overridable so a smaller/larger target can be exercised without changing code.
MAX_OUTPUT_GIF = int(os.environ.get('RAINY75_OUTPUT_GIF_LIMIT', 4 * 1024 * 1024))
# The screen's external flash is shared with whatever else lives there, so the
# practical S1 budget is far below the protocol's 4 MiB ceiling: a 1.87 MB /
# 8083-packet animation is refused with BEGIN status 4 while the 250 KB lite
# version goes in fine. Keep a conservative default and let the UI change it.
# 4 MiB is the protocol ceiling (MAX_OUTPUT_GIF); pick it as the default so the
# animation keeps every frame, and let the wizard auto-degrade if the screen's
# external flash turns out smaller.
S1_BUDGETS = [256 * 1024, 512 * 1024, 1024 * 1024, 2 * 1024 * 1024, 4 * 1024 * 1024]
DEFAULT_S1_BUDGET = 4 * 1024 * 1024
SETTINGS_FILE = LOCAL / 'settings.json'
# Folder shortcuts for the "查看固件" buttons. Fixed keys only: the endpoint
# never accepts a free-form path from the browser.
FIRMWARE_TARGETS = {
    'screen': lambda: BUILD_IPS,
    'main': lambda: ROOT / 'build' / 'main',
    'snapshot': lambda: ROOT / 'toolbox' / 'firmware',
}


def firmware_info():
    out = {}
    for key, resolve in FIRMWARE_TARGETS.items():
        folder = resolve()
        entry = {'path': str(folder), 'rel': str(folder.relative_to(ROOT)) if folder.exists() else '',
                 'exists': folder.exists(), 'files': []}
        if folder.exists():
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.suffix.lower() in ('.bin', '.json', '.gif', '.png'):
                    entry['files'].append({'name': f.name, 'bytes': f.stat().st_size})
        out[key] = entry
    return out
# Only a guard against pathological inputs. Frame sampling is driven by the
# encoded S1 size, not by a fixed frame budget: a GIF that fits 4 MiB keeps all
# of its frames (see /api/upload below).
MAX_FRAMES = 300
LIMITS = {
    'uploadBytes': MAX_UPLOAD_BYTES, 'outputBytes': MAX_OUTPUT_GIF,
    'screen': [SCREEN_W, SCREEN_H], 'maxFrames': MAX_FRAMES,
    'rules': ['严格 320×172', '每帧完整且 disposal=1、不透明',
              '默认按「动画体积上限」抽帧，保证能写进屏幕外置 Flash',
              '上限可在定制台切换（256 KB / 512 KB / 1 MB / 2 MB）'],
}

PRESETS = {
    '深海蓝': {'background': '#eaf2fd', 'panel': '#f7fbff', 'shell': '#a9c6ef', 'ink': '#22418c', 'accent': '#3f7fd8'},
    '樱花粉': {'background': '#fff1f6', 'panel': '#fff8e9', 'shell': '#f0c1d5', 'ink': '#a35479', 'accent': '#d58eae'},
    '薄荷绿': {'background': '#edf8f2', 'panel': '#f8fff6', 'shell': '#b1d8c9', 'ink': '#366c61', 'accent': '#70a998'},
    '墨水灰': {'background': '#e9e9e7', 'panel': '#fafaf7', 'shell': '#b7b9b5', 'ink': '#343b37', 'accent': '#8c948b'},
    '奶油杏': {'background': '#fff6e9', 'panel': '#fffbf2', 'shell': '#efd2a8', 'ink': '#7a4c22', 'accent': '#e0a456'},
    '薰衣草紫': {'background': '#f3f0fd', 'panel': '#fbf8ff', 'shell': '#cbb8ee', 'ink': '#4b3480', 'accent': '#8f6fd6'},
    '抹茶青': {'background': '#eef7ec', 'panel': '#f7fdf3', 'shell': '#b6d8b4', 'ink': '#2f5c3f', 'accent': '#6fae7d'},
    '蜜桃粉': {'background': '#fff0ed', 'panel': '#fff8f5', 'shell': '#f3c3ba', 'ink': '#8a3f3c', 'accent': '#e0867b'},
    '天青': {'background': '#e9f6fa', 'panel': '#f4fcff', 'shell': '#a9d5e6', 'ink': '#1f5470', 'accent': '#4fa6c8'},
    '复古棕': {'background': '#f6efe4', 'panel': '#fdf8ef', 'shell': '#d6c2a4', 'ink': '#5a3d2b', 'accent': '#a8794f'},
    '赛博青': {'background': '#e6fbf8', 'panel': '#f0fffd', 'shell': '#9ad9d2', 'ink': '#14524c', 'accent': '#2fb3a3'},
    '暗夜': {'background': '#232a3b', 'panel': '#303950', 'shell': '#414d69', 'ink': '#eef2ff', 'accent': '#7f9cf0'},
}


def looks_like_ui_capture(raw):
    """Detect a screenshot of the screen / studio preview used as a character.

    Baking a whole UI image into S1 shows a second, smaller copy of the interface
    inside the character box ("nested screens"). Unlike a warning, callers must
    refuse such input. Two independent signals are combined:

    * screen-like aspect ratio and size (the classic 320x172 / 1.86 family);
    * long, perfectly straight dark lines - the key-card / panel borders that
      every UI has but hand-drawn or photo character art does not.

    Returns (is_capture, reason). Only the first frame is inspected.
    """
    try:
        import io as _io
        with Image.open(_io.BytesIO(raw)) as probe:
            w, h = probe.size
            probe.seek(0)
            im = probe.convert('RGB')
    except Exception:
        return False, ''
    ratio = w / max(1, h)
    aspect = w >= 300 and 1.62 <= ratio <= 2.10
    # Sample a coarse grid; long straight runs are what matter, not fine detail.
    gray = im.convert('L')
    pw, ph = gray.size
    sx, sy = max(1, pw // 160), max(1, ph // 90)
    px = gray.load()
    xs = list(range(0, pw, sx))
    ys = list(range(0, ph, sy))
    straight = False
    for y in ys:
        run = best = 0
        for x in xs:
            if px[x, y] < 128:
                run += 1
                best = max(best, run)
            else:
                run = 0
        if best * sx > pw * 0.30:
            straight = True
            break
    if not straight:
        for x in xs:
            run = best = 0
            for y in ys:
                if px[x, y] < 128:
                    run += 1
                    best = max(best, run)
                else:
                    run = 0
            if best * sy > ph * 0.30:
                straight = True
                break
    if aspect and straight:
        return True, f'{w}×{h} 的横屏截图（含 UI 直线边框）'
    if aspect:
        return True, f'{w}×{h} 的横屏截图'
    return False, ''


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf8'))
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def convert_s1_gif(raw, theme_id=None, budget=None, layout='base', box=None, scale=1.0,
                   remove_bg=True, name='自定义角色'):
    """Render any GIF into the screen's 320x172 S1 background.

    Used by the flashing wizard so a phone-saved GIF (480x270, partial frames,
    odd aspect) can be written straight to S1 without recompiling the IPS: the
    character is contained into the character box on the current theme
    background, frames are sampled until the file fits ``budget``. Nothing is
    written to ``local/`` - the caller gets the bytes back.
    """
    import gifclip, tempfile
    budget = budget or s1_budget()
    themes = all_themes()
    theme_id = theme_id if theme_id in themes else ('pink' if 'pink' in themes else next(iter(themes)))
    theme = themes[theme_id]
    with tempfile.TemporaryDirectory(prefix='rainy75-convert-') as tmp:
        src = Path(tmp) / 'src.gif'
        src.write_bytes(raw)
        with Image.open(src) as probe:
            n = probe.n_frames
        if n < 1:
            raise ValueError('GIF 没有可读取的帧')
        target = min(n, MAX_FRAMES)
        out = Path(tmp) / 's1.gif'
        frames, timing = [], None
        for _ in range(8):
            frames = gifclip.load_gif_frames(src, max_frames=target, remove_bg=remove_bg)
            timing = gifclip.sample_timing(src, max_frames=len(frames))
            cfg = {'enabled': True, 'name': name[:40], 'sourceGif': 'convert',
                   'files': [], 'frameCount': len(frames), 'sequence': list(range(len(frames))),
                   'motion': {'enabled': False, 'frames': len(frames), 'style': 'gif'},
                   'bob': [0] * 8, 'shadow': True, 'scale': float(scale or 1.0), 'offsetY': 0,
                   'box': list(box or [188, 42, 300, 154]), 'removeBg': remove_bg,
                   'duration': min(600, max(60, round(timing['perFrameMs'] / 10) * 10))}
            duration = cfg['duration']
            keep_studio, keep_cfg, keep_sprites = assets.STUDIO, assets._CHAR_CFG, assets._CHAR_SPRITES
            keep_character = assets.character
            try:
                assets.STUDIO = layout == 'studio'
                assets._CHAR_CFG = cfg
                assets._CHAR_SPRITES = frames
                assets.character = lambda: cfg
                images = [assets.base_frame(theme, i) for i in range(len(frames))]
            finally:
                assets.STUDIO, assets._CHAR_CFG, assets._CHAR_SPRITES = keep_studio, keep_cfg, keep_sprites
                assets.character = keep_character
            assets.save_cache_gif(images, out, duration)
            size = out.stat().st_size
            if size <= budget * 0.97 or len(frames) <= 2:
                break
            target = max(2, int(len(frames) * (budget * 0.94) / max(1, size)))
        size = out.stat().st_size
        return {'gif': out.read_bytes(), 'frames': len(frames), 'sourceFrames': n,
                'bytes': size, 'overBudget': size > budget, 'budget': budget,
                'perFrameMs': timing['perFrameMs'] if timing else 0,
                'theme': theme_id, 'layout': layout,
                'source': list(Image.open(src).size)}

def all_themes():
    return {**read_json(ROOT / 'profiles' / 'themes.json', {}), **read_json(THEMES_FILE, {})}


def find_clang():
    # Order: explicit override (packaged build sets this) -> toolchain next to
    # the executable -> portable llvm next to the repository -> PATH.
    env = os.environ.get('RAINY75_CLANG')
    if env and Path(env).exists():
        return env
    for base in (ROOT, ROOT.parent):
        for pattern in ('llvm/bin/clang.exe', 'llvm/*/bin/clang.exe', 'llvm-portable/*/bin/clang.exe',
                        'llvm/bin/clang', 'llvm/*/bin/clang', 'llvm-portable/*/bin/clang'):
            hits = sorted(base.glob(pattern))
            if hits:
                return str(hits[0])
    return shutil.which('clang')


def run_build(argv):
    """Run tools/build.py and return (returncode, combined output).

    When frozen as a single .exe there is no separate interpreter to spawn, so
    the builder is imported and executed in-process with its stdout captured.
    """
    if getattr(sys, 'frozen', False):
        import contextlib
        import io
        buf = io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                build_module = importlib.import_module('build')
                parser = build_module.argparse.ArgumentParser()
                parser.add_argument('target', choices=['ips', 'main'])
                parser.add_argument('--stock', type=Path, required=True)
                parser.add_argument('--isp-lib', type=Path)
                parser.add_argument('--restore-stock', action='store_true')
                parser.add_argument('--clang')
                parser.add_argument('--riscv-march', default='rv32imac_zicsr_zifencei')
                parser.add_argument('--out', type=Path, default=ROOT / 'build')
                parser.add_argument('--keys', type=Path, default=ROOT / 'profiles/keys.json')
                parser.add_argument('--theme', default='pink')
                build_module.build(parser.parse_args(argv))
        except SystemExit as e:
            code = int(e.code or 0)
        except Exception as e:  # keep the log useful instead of a traceback popup
            buf.write(f'\n{e}\n')
            code = 1
        return code, buf.getvalue()
    proc = subprocess.run(
        [sys.executable, str(ROOT / 'tools' / 'build.py'), *argv],
        cwd=str(ROOT), env={**os.environ, 'RAINY75_STUDIO': '1'},
        capture_output=True, text=True, timeout=300)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


_WHITE, _BLACK = (255, 255, 255), (0, 0, 0)


def _hex(c):
    return '#%02x%02x%02x' % tuple(max(0, min(255, round(v))) for v in c)


def _toward(c, target, f):
    return tuple(v + (t - v) * f for v, t in zip(c, target))


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _sat(c):
    hi, lo = max(c), min(c)
    return 0 if hi == 0 else (hi - lo) / hi


def extract_palette(raw):
    """Quantise the GIF's dominant colours into 3 usable UI themes."""
    with Image.open(io.BytesIO(raw)) as g:
        n = g.n_frames
        picks = sorted({0, n // 4, n // 2, (3 * n) // 4, n - 1})
        tiny = []
        for i in picks:
            g.seek(i)
            im = g.convert('RGB')
            im.thumbnail((96, 96))
            tiny.append(im)
    px = [p for im in tiny for p in im.getdata() if min(p) < 246]
    if not px:
        return []
    sheet = Image.new('RGB', (len(px), 1))
    sheet.putdata(px)
    quant = sheet.quantize(colors=10, method=Image.Quantize.MEDIANCUT).convert('RGB')
    cols = [list(c) for c, _ in Counter(quant.getdata()).most_common(10)]
    cols.sort(key=_lum)
    dark, light, mid = cols[0], cols[-1], cols[len(cols) // 2]
    vivid = max(cols, key=lambda c: _sat(c) * 1.4 - abs(_lum(c) - 128) / 255.0)

    def build(name, bg_f, panel_f, shell_f, ink_f, accent_f, shell_src, ink_src):
        # Keep a hint of the character's dominant hue instead of a flat white.
        bg = _toward(_toward(light, _WHITE, bg_f), vivid, 0.12)
        panel = _toward(_toward(light, _WHITE, panel_f), vivid, 0.06)
        shell = _toward(shell_src, _WHITE, shell_f)
        ink = _toward(ink_src, _BLACK, ink_f)
        accent = _toward(vivid, _WHITE, accent_f)
        if _lum(bg) - _lum(ink) < 90:
            ink = _toward(ink, _BLACK, 0.5)
        c = {'background': _hex(bg), 'panel': _hex(panel), 'shell': _hex(shell),
             'ink': _hex(ink), 'accent': _hex(accent)}
        if assets.rgb565(c['shell']) == assets.rgb565(c['background']):
            c['shell'] = _hex(_toward(shell, _BLACK, 0.12))
        return {'name': name, 'colors': c,
                'swatches': [c['background'], c['shell'], c['accent'], c['ink']]}

    return [build('贴合原色', 0.80, 0.92, 0.30, 0.20, 0.10, mid, dark),
            build('清爽浅色', 0.90, 0.96, 0.55, 0.32, 0.05, vivid, dark),
            build('高对比', 0.70, 0.86, 0.18, 0.45, 0.18, mid, dark)]


def gif_fit_size(frames, cfg, source_size=None):
    """Report the contain-fit size used when pasting frames into the screen."""
    s = frames[0]
    x0, y0, x1, y1 = [int(v) for v in cfg.get('box', [188, 42, 300, 154])]
    scale = float(cfg.get('scale', 1.0))
    ratio = min((x1 - x0) / s.width, (y1 - y0) / s.height) * scale
    return {'source': list(source_size) if source_size else [s.width, s.height],
            'cropped': [s.width, s.height],
            'fitted': [max(1, round(s.width * ratio)), max(1, round(s.height * ratio))],
            'box': [x0, y0, x1, y1], 'frames': len(frames)}


def validate_colors(raw):
    if not isinstance(raw, dict):
        raise ValueError('主题色格式错误')
    out = {}
    for key in COLOR_FIELDS:
        value = raw.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError('颜色 ' + key + ' 必须是 #rrggbb 格式')
        out[key] = value.lower()
    for key in REQUIRED_COLORS:
        if key not in out:
            raise ValueError('缺少必需颜色 ' + key)
    if assets.rgb565(out['shell']) == assets.rgb565(out['background']):
        raise ValueError('shell 与 background 在 RGB565 下不能相同（GIF 标记点校验会失败）')
    return out


def validate_character(raw):
    if not isinstance(raw, dict):
        raise ValueError('角色配置格式错误')
    files = raw.get('files')
    if not isinstance(files, list) or not files or len(files) > 3:
        raise ValueError('还没有角色素材：请在 ① 里上传一张角色 GIF（或选择 1~3 张视角图）后再应用')
    for rel in files:
        if not isinstance(rel, str) or not rel.startswith('local/views/') or '..' in rel:
            raise ValueError('角色素材路径不合法')
        if not (ROOT / rel).exists():
            raise ValueError('缺少角色素材 ' + rel)
    src = raw.get('sourceGif')
    if src:
        if not isinstance(src, str) or not src.startswith('local/') or '..' in src or not (ROOT / src).exists():
            raise ValueError('GIF 素材路径不合法')
        from gifclip import durations_of, MAX_FRAMES
        total = len(durations_of(ROOT / src))
        sample = int(raw.get('gifSample') or 0) or None
        # gifSample is the exact number of frames the uploaded GIF was sampled
        # down to; load_sprites() replays the same sample, so indices must match.
        limit = min(total, MAX_FRAMES, sample) if sample else min(total, MAX_FRAMES)
    else:
        limit = len(files)
    seq = raw.get('sequence')
    if not isinstance(seq, list) or not 1 <= len(seq) <= max(64, limit) or any(not isinstance(v, int) or not 0 <= v < limit for v in seq):
        raise ValueError('动画帧序不合法')
    box = raw.get('box')
    if not isinstance(box, list) or len(box) != 4 or any(not isinstance(v, int) for v in box):
        raise ValueError('角色区域 box 不合法')
    cfg = dict(raw)
    cfg['enabled'] = True
    cfg['files'] = files
    cfg['sequence'] = seq
    if src:
        cfg['sourceGif'] = src
    else:
        cfg.pop('sourceGif', None)
    cfg['box'] = box
    cfg['scale'] = min(1.6, max(0.4, float(raw.get('scale', 1.0))))
    cfg['offsetY'] = min(30, max(-30, int(raw.get('offsetY', 0))))
    cfg['duration'] = min(600, max(60, int(raw.get('duration', 160))))
    cfg['shadow'] = bool(raw.get('shadow', True))
    cfg['removeBg'] = bool(raw.get('removeBg', True))
    frames = int(raw.get('frameCount', 8))
    # Frame budget is now size-driven (up to the 300-frame safety cap), so a
    # full-length uploaded GIF must also pass preview/apply validation.
    if not 1 <= frames <= MAX_FRAMES:
        raise ValueError(f'动画帧数必须在 1~{MAX_FRAMES} 之间')
    cfg['frameCount'] = frames
    if cfg.get('sourceGif'):
        cfg['bob'] = [0] * 8  # uploaded GIF has its own motion; no synthetic bob
    motion = raw.get('motion')
    if isinstance(motion, dict):
        cfg['motion'] = {'enabled': bool(motion.get('enabled')), 'frames': frames,
                         'style': str(motion.get('style') or 'lively')[:20]}
    else:
        cfg['motion'] = {'enabled': False, 'frames': frames, 'style': 'off'}
    return cfg


def decode_image(data_url):
    if not isinstance(data_url, str) or ',' not in data_url:
        raise ValueError('图片数据格式错误')
    raw = base64.b64decode(data_url.split(',', 1)[1], validate=True)
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError('图片超过 12 MiB')
    im = Image.open(io.BytesIO(raw))
    im.seek(0)
    return im.convert('RGB') if im.mode not in ('RGBA', 'LA') else im.convert('RGBA')


def png_bytes(im):
    buf = io.BytesIO()
    im.convert('RGB').save(buf, format='PNG')
    return buf.getvalue()


def s1_budget():
    """Current S1 size target (bytes)."""
    try:
        raw = read_json(SETTINGS_FILE, {}) or {}
        # One-time migration: v1.3.19 and earlier capped the default at 512 KB or
        # 2 MB. The protocol ceiling is now selectable, so raise everyone to it
        # once; later choices are respected.
        if raw.get('s1BudgetVersion') != 2:
            raw['s1Budget'] = max(int(raw.get('s1Budget') or 0), DEFAULT_S1_BUDGET)
            raw['s1BudgetVersion'] = 2
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            write_json(SETTINGS_FILE, raw)
        value = int(raw.get('s1Budget') or DEFAULT_S1_BUDGET)
    except Exception:
        value = DEFAULT_S1_BUDGET
    return max(64 * 1024, min(MAX_OUTPUT_GIF, value))


def set_s1_budget(value):
    raw = read_json(SETTINGS_FILE, {}) or {}
    raw['s1Budget'] = max(64 * 1024, min(MAX_OUTPUT_GIF, int(value)))
    write_json(SETTINGS_FILE, raw)
    return raw['s1Budget']


def state_payload():
    cfg = read_json(CHAR_FILE, {}) or {}
    manifest = read_json(BUILD_IPS / 'manifest.json', {}) or {}
    theme_id = manifest.get('theme') or cfg.get('theme') or 'pink'
    sprites = []
    for i, rel in enumerate(cfg.get('files', [])):
        path = ROOT / rel
        if path.exists():
            with Image.open(path) as im:
                sprites.append({'index': i, 'name': charmod.VIEW_NAMES[i] if i < 3 else f'view{i}', 'w': im.width, 'h': im.height, 'url': f'/api/sprite/{i}'})
    gif = ASSETS_DIR / f'robot-{theme_id}.gif'
    return {
        'ok': True,
        'themes': all_themes(),
        'presets': PRESETS,
        'themeId': theme_id,
        'character': cfg,
        'sprites': sprites,
        'sourceGif': cfg.get('sourceGif'),
        'gifFrames': len(cfg.get('sequence') or []) if cfg.get('sourceGif') else 0,
        'manifest': manifest,
        'gifBytes': gif.stat().st_size if gif.exists() else 0,
        'gifUrl': f'/api/gif?t={theme_id}',
        'previewUrl': f'/api/preview?t={theme_id}',
        'limits': LIMITS,
        's1Budget': s1_budget(),
        's1BudgetOptions': S1_BUDGETS,
        'statusbar': read_json(ROOT / 'profiles' / 'statusbar.json', {}),
        'leftIcon': read_json(LOCAL / 'left-icon.json', {}),
        'stockReady': STOCK.exists(),
        'mainStockReady': MAIN_STOCK.exists(),
        'clang': find_clang(),
        'wizardUrl': 'web/flash-wizard.html',  # relative: same origin as the wizard inside the toolbox
    }


def preview_icon(spec):
    """Decode a '<w>x<h>:<hex>' pixel spec sent by the live pixel editor."""
    if not spec:
        return None
    try:
        w, rest = spec.split('x', 1)
        h, hexbits = rest.split(':', 1)
        w, h = int(w), int(h)
        if not (1 <= w <= 64 and 1 <= h <= 32):
            return None
        bits = ''.join(f'{int(c, 16):04b}' for c in hexbits)[:w * h]
        rows = [bits[y * w:(y + 1) * w].replace('0', '.').replace('1', '#')
                for y in range(h)]
        return assets._art(rows)
    except Exception:
        return None


def render_preview(colors, cfg, icon=None, statusbar=None, icon_color=None):
    # An empty cfg means "no custom character loaded yet" (the GET icon-preview
    # path). Render the stock background/robot and only override the rice icon.
    try:
        sprites = charmod.load_sprites(cfg)
    except Exception:
        sprites = None
    keys = assets.load(KEYS_FILE)
    with LOCK:
        old_cfg, old_sprites = assets._CHAR_CFG, assets._CHAR_SPRITES
        old_icon = assets._LEFT_ICON_OVERRIDE
        old_bar = assets._STATUSBAR_OVERRIDE
        if sprites is not None:
            assets._CHAR_CFG, assets._CHAR_SPRITES = cfg, sprites
        else:
            assets._CHAR_CFG, assets._CHAR_SPRITES = None, ()
        if icon is not None:
            assets._LEFT_ICON_OVERRIDE = icon
        if statusbar is not None:
            assets._STATUSBAR_OVERRIDE = statusbar
        try:
            return assets.preview_frame(colors, keys, icon_color=icon_color)
        finally:
            assets._CHAR_CFG, assets._CHAR_SPRITES = old_cfg, old_sprites
            assets._LEFT_ICON_OVERRIDE = old_icon
            assets._STATUSBAR_OVERRIDE = old_bar


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript'}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'")
        super().end_headers()

    def log_message(self, fmt, *args):
        # A windowed build has sys.stderr = None; writing to it would raise and
        # abort the request (the client sees a dropped connection).
        if '/api/' in (self.path or '') and sys.stderr is not None:
            super().log_message(fmt, *args)

    def send_bytes(self, data, content_type='image/png', status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, obj, status=200):
        self.send_bytes(json.dumps(obj, ensure_ascii=False).encode('utf8'), 'application/json; charset=utf-8', status)

    def body(self):
        size = int(self.headers.get('Content-Length', 0))
        if size > 14 * 1024 * 1024:
            raise ValueError('请求体过大')
        return json.loads(self.rfile.read(size) or b'{}')

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == '/api/firmware-info':
                return self.send_json({'ok': True, 'targets': firmware_info()})
            if path == '/api/state':
                return self.send_json(state_payload())
            if path.startswith('/api/sprite/'):
                cfg = read_json(CHAR_FILE, {}) or {}
                idx = int(path.rsplit('/', 1)[1])
                rel = cfg.get('files', [])[idx]
                p = ROOT / rel
                if not str(p.resolve()).startswith(str((ROOT / 'local' / 'views').resolve())):
                    raise ValueError('路径越界')
                return self.send_bytes(p.read_bytes())
            if path == '/api/gif':
                t = (parse_qs(urlparse(self.path).query).get('t') or [state_payload()['themeId']])[0]
                t = re.sub(r'[^a-z0-9_-]', '', t)
                p = ASSETS_DIR / f'robot-{t}.gif'
                if not p.exists():
                    return self.send_json({'error': 'GIF 不存在'}, 404)
                return self.send_bytes(p.read_bytes(), 'image/gif')
            if path == '/api/preview':
                query = parse_qs(urlparse(self.path).query)
                t = (query.get('t') or [state_payload()['themeId']])[0]
                t = re.sub(r'[^a-z0-9_-]', '', t)
                spec = (query.get('i') or [''])[0]
                theme = all_themes().get(t)
                if spec and theme:
                    # live preview while the user paints the pixel editor: the
                    # rows come straight from the browser, no save required
                    icon = preview_icon(spec)
                    if icon is not None:
                        keys = assets.load(KEYS_FILE)
                        img = render_preview(theme, {}, icon)
                        buf = io.BytesIO()
                        img.save(buf, 'PNG')
                        return self.send_bytes(buf.getvalue())
                p = ASSETS_DIR / f'preview-{t}.png'
                if not p.exists():
                    return self.send_json({'error': '预览图不存在'}, 404)
                return self.send_bytes(p.read_bytes())
            return super().do_GET()
        except Exception as e:
            return self.send_json({'error': str(e)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/quit':
            # Used by the packaged app's 退出程序 button when the page runs in a
            # normal browser tab (no window process to watch).
            self.send_json({'ok': True, 'message': 'stopping'})
            threading.Thread(target=_shutdown_soon, daemon=True).start()
            return
        if path == '/api/reveal':
            data = self.body()
            key = str(data.get('target') or '')
            resolve = FIRMWARE_TARGETS.get(key)
            if resolve is None:
                return self.send_json({'ok': False, 'error': '未知的固件位置'}, 400)
            folder = resolve()
            if not folder.exists():
                return self.send_json(
                    {'ok': False, 'error': '该目录还不存在：先点「应用并重新编译 IPS 固件」生成产物'}, 400)
            if sys.platform.startswith('win'):
                import subprocess
                subprocess.Popen(['explorer', str(folder)])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', str(folder)])
            return self.send_json({'ok': True, 'path': str(folder)})
        if path == '/api/settings':
            data = self.body()
            if 's1Budget' in data:
                try:
                    value = set_s1_budget(data['s1Budget'])
                except Exception:
                    return self.send_json({'ok': False, 'error': '体积上限不是有效数字'}, 400)
                return self.send_json({'ok': True, 's1Budget': value,
                                       'log': f'动画体积上限已设为 {value // 1024} KB，下次上传/应用生效'})
            return self.send_json({'ok': True, 's1Budget': s1_budget()})
        if path == '/api/stock':
            # The public build ships WITHOUT any factory firmware (those binaries
            # belong to WOB and are not MIT). The user drops their own copy here;
            # it stays on this machine under inputs/ and is never uploaded.
            data = self.body()
            target = str(data.get('target') or 'ips')
            if target not in STOCK_ACCEPT:
                return self.send_json({'ok': False, 'error': '未知目标：' + target}, 400)
            raw = data.get('data') or ''
            if not isinstance(raw, str) or ',' not in raw:
                return self.send_json({'ok': False, 'error': '缺少文件内容'}, 400)
            try:
                blob = base64.b64decode(raw.split(',', 1)[1], validate=True)
            except Exception:
                return self.send_json({'ok': False, 'error': '文件不是有效的 base64 数据'}, 400)
            spec = STOCK_ACCEPT[target]
            digest = hashlib.sha256(blob).hexdigest()
            if len(blob) not in spec['sizes'] or (spec['sha'] and digest != spec['sha']):
                return self.send_json({
                    'ok': False,
                    'error': (f'这不是可用的原厂固件：收到 {len(blob)} B / sha256 {digest[:12]}…，'
                              f'需要 {spec["hint"]}（sha256 '
                              f'{spec["sha"][:12] + "…" if spec["sha"] else "任意"}）。'
                              '请从官方烧录工具导出后原样选择，别改名或裁剪。')}, 400)
            dest = STOCK if target == 'ips' else MAIN_STOCK
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            return self.send_json({'ok': True, 'state': state_payload(),
                                   'log': f'已导入原厂固件 {target}（{len(blob)} B，sha256 {digest[:12]}…）到 inputs/{dest.name}'})
        try:
            data = self.body()
            if path == '/api/palette':
                url = data.get('image') or ''
                if isinstance(url, str) and url.startswith('data:'):
                    raw = base64.b64decode(url.split(',', 1)[1], validate=True)
                    if len(raw) > MAX_UPLOAD_BYTES:
                        raise ValueError('图片超过 12 MiB')
                else:
                    saved = LOCAL / 'character.gif'
                    if not saved.exists():
                        raise ValueError('请先上传一个 GIF 动画，再提取配色')
                    raw = saved.read_bytes()
                return self.send_json({'ok': True, 'palettes': extract_palette(raw)})
            if path == '/api/left-icon':
                target = LOCAL / 'left-icon.json'
                if target.exists():
                    target.unlink()
                return self.send_json({'ok': True, 'cleared': True, 'log': '已恢复默认米饭图标'})
            if path == '/api/statusbar':
                left = data.get('left') or {}
                kind = left.get('type')
                if kind not in ('time', 'text', 'rice'):
                    raise ValueError('左边只能选：时间 / 自定义文字 / 米饭图标')
                text = ''.join(str(left.get('text') or ''))[:6]
                bowls, fish = 0, 0
                if kind == 'text' and not text:
                    raise ValueError('选了自定义文字就要填内容（最多 6 字）')
                right = [w for w in (data.get('right') or [])
                         if w in assets.STATUS_WIDGETS and w not in []][:3]
                values = {k: str((data.get('values') or {}).get(k) or '--')[:4]
                          for k in ('rate', 'debounce')}
                cfg = {'left': {'type': kind, 'text': text, 'bowls': bowls, 'fish': fish},
                       'right': right, 'values': values}
                rows = data.get('icon')
                if isinstance(rows, list) and rows:
                    rows = [str(r) for r in rows]
                    if len({len(r) for r in rows}) != 1 or set(''.join(rows)) - {'0', '1'}:
                        raise ValueError('点阵格式不对：每行等长、只能 0/1')
                    # Crop to the displayable area instead of rejecting: an icon
                    # saved by an older build may be wider than 20 px, and
                    # failing the whole save silently kept the old left mode.
                    rows = [r[:assets.ICON_MAX_W] for r in rows[:assets.ICON_MAX_H]]
                    if not rows or not rows[0]:
                        raise ValueError('点阵是空的，请至少画一个像素')
                    color = str(data.get('color') or '').strip().lower()
                    if color and not re.fullmatch(r'#[0-9a-f]{6}', color):
                        raise ValueError('颜色格式不对：请用 #rrggbb')
                    LOCAL.mkdir(parents=True, exist_ok=True)
                    payload = {'w': len(rows[0]), 'h': len(rows), 'rows': rows}
                    if color:
                        payload['color'] = color
                    write_json(LOCAL / 'left-icon.json', payload)
                write_json(ROOT / 'profiles' / 'statusbar.json', cfg)
                layout = assets.status_layout(all_themes().get(
                    (read_json(BUILD_IPS / 'manifest.json', {}) or {}).get('theme') or 'pink')
                    or next(iter(all_themes().values())))
                return self.send_json({'ok': True, 'statusbar': cfg,
                                       'regions': len(layout['regions']),
                                       'maskBytes': layout['total'],
                                       'log': '状态栏已保存：左边 %s，右边 %s（掩码 %d B，%d 个区域）。点「应用并重新编译 IPS 固件」后生效%s。'
                                              % (kind, ','.join(right) or '无', layout['total'], len(layout['regions']),
                                                 '；自定义文字画在 S1 底图上，还要在刷机向导第 ⑤ 步重新上传 S1' if kind == 'text' else '')})
            if path == '/api/convert-s1':
                url = data.get('image') or ''
                if not (isinstance(url, str) and url.startswith('data:image/gif')):
                    raise ValueError('请选择一个 GIF 图片（.gif）')
                raw = base64.b64decode(url.split(',', 1)[1], validate=True)
                if len(raw) > MAX_UPLOAD_BYTES:
                    raise ValueError('GIF 超过 12 MiB，请先在本地压缩')
                # A screenshot of the screen / studio preview would be pasted
                # into the character box and produce a nested second UI.
                shot, shot_reason = looks_like_ui_capture(raw)
                if shot:
                    raise ValueError('这是整屏截图（'+shot_reason+'），会被当成角色贴进 S1 底图，'
                                     '导致屏幕上出现两层界面。请只上传角色本身：'
                                     '透明背景的 GIF，或先把角色从截图里裁出来再上传。')
                budget = s1_budget()
                if data.get('budgetBytes'):
                    try:
                        budget = int(data['budgetBytes'])
                    except Exception:
                        pass
                try:
                    got = convert_s1_gif(raw, theme_id=data.get('themeId'), budget=budget,
                                         layout=data.get('layout') or 'base',
                                         remove_bg=bool(data.get('removeBg', True)))
                except Exception as exc:
                    return self.send_json({'ok': False, 'error': f'自动转换失败：{exc}'}, 400)
                blob = got.pop('gif')
                return self.send_json({'ok': True, 'gif': 'data:image/gif;base64,'
                                      + base64.b64encode(blob).decode(), **got})
            upload_warning = ''
            if path == '/api/upload':
                url = data.get('image') or ''
                if isinstance(url, str) and url.startswith('data:image/gif'):
                    raw = base64.b64decode(url.split(',', 1)[1], validate=True)
                    if len(raw) > 12 * 1024 * 1024:
                        raise ValueError('GIF 超过 12 MiB')
                    with Image.open(io.BytesIO(raw)) as probe:
                        n = probe.n_frames
                        src_w, src_h = probe.size
                    # A screenshot of the screen itself gets baked into S1 as a
                    # second copy of the whole UI (frame, cards, status bar), so
                    # the display ends up showing the layout twice. Refuse it
                    # outright: a warning is not enough - the nested image was
                    # still written and shipped to S1.
                    shot, shot_reason = looks_like_ui_capture(raw)
                    if shot:
                        raise ValueError('这是整屏截图（'+shot_reason+'），会被当成角色贴进 S1 底图，'
                                         '导致屏幕上出现两层界面。请只上传角色本身：'
                                         '透明背景的 GIF，或先把角色从截图里裁出来再上传。')
                    if n > 1:
                        import gifclip
                        gif_path = LOCAL / 'character.gif'
                        gif_path.write_bytes(raw)
                        remove_bg = bool(data.get('removeBg', True))
                        (LOCAL / 'views').mkdir(parents=True, exist_ok=True)
                        base_cfg = read_json(CHAR_FILE, {}) or {}
                        theme_id = (base_cfg.get('theme')
                                    or (read_json(BUILD_IPS / 'manifest.json', {}) or {}).get('theme')
                                    or 'ocean')
                        # Keep EVERY source frame by default. Sampling is driven by
                        # the encoded S1 size, not by a fixed frame budget: only a
                        # GIF that would exceed 4 MiB gets sampled down.
                        target = min(n, MAX_FRAMES)
                        out_gif = ASSETS_DIR / f'robot-{theme_id}.gif'
                        # Respect the user's S1 size target: the screen refuses
                        # anything bigger than its free flash (BEGIN status 4),
                        # so sample frames down until the GIF fits the budget.
                        budget = s1_budget()
                        if data.get('budgetBytes'):
                            try:
                                budget = set_s1_budget(data['budgetBytes'])
                            except Exception:
                                pass
                        frames, timing, cfg, size = [], None, base_cfg, 0
                        for _ in range(8):
                            frames = gifclip.load_gif_frames(gif_path, max_frames=target, remove_bg=remove_bg)
                            keep = len(frames)
                            timing = gifclip.sample_timing(gif_path, max_frames=keep)
                            cfg = dict(base_cfg)
                            cfg['enabled'] = True
                            cfg['sourceGif'] = 'local/character.gif'
                            cfg['files'] = ['local/views/gif-pose.png']
                            cfg['name'] = str(data.get('name') or base_cfg.get('name') or '自定义角色')[:40]
                            cfg['frameCount'] = keep
                            cfg['gifSample'] = keep          # replayed by load_sprites()
                            cfg['sequence'] = list(range(keep))
                            cfg['motion'] = {'enabled': False, 'frames': keep, 'style': 'gif'}
                            cfg['removeBg'] = remove_bg
                            # Preserve the original loop length after frame sampling.
                            cfg['duration'] = min(600, max(60, round(timing['perFrameMs'] / 10) * 10))
                            cfg.setdefault('box', [188, 42, 300, 154])
                            cfg.setdefault('scale', 1.0)
                            cfg.setdefault('offsetY', 0)
                            # Uploaded GIFs carry their own motion; never inherit
                            # the synthetic 8-phase bob from a previous profile.
                            cfg['bob'] = [0] * 8
                            cfg.setdefault('shadow', True)
                            write_json(CHAR_FILE, cfg)
                            with LOCK:
                                assets._CHAR_CFG, assets._CHAR_SPRITES = None, ()
                                assets.generate(KEYS_FILE, theme_id, ASSETS_DIR, None)
                            size = out_gif.stat().st_size if out_gif.exists() else 0
                            if size <= budget * 0.97:
                                break
                            nxt = max(2, int(keep * (budget * 0.94) / max(1, size)))
                            target = min(nxt, keep - 1) if nxt >= keep else nxt
                        frames[0].save(LOCAL / 'views' / 'gif-pose.png')
                        count = len(frames)
                        sampled = count < n
                        # Recompile IPS once, with the final frame count.
                        compiled, build_log = False, ''
                        clang = find_clang()
                        if STOCK.exists() and clang:
                            code, build_log = run_build(
                                ['ips', '--stock', str(STOCK), '--theme', theme_id, '--clang', clang])
                            compiled = code == 0
                        if not compiled:
                            build_log = build_log or '缺少原厂输入或便携 clang，已仅生成 S1 素材'
                        size = out_gif.stat().st_size if out_gif.exists() else 0
                        with Image.open(gif_path) as probe:
                            source_size = probe.size
                        return self.send_json({
                            'ok': True, 'views': 1, 'gifFrames': count,
                            'sourceFrames': n, 'sampled': sampled,
                            'compiled': compiled, 'buildLog': build_log[-1400:],
                            'fitted': gif_fit_size(frames, cfg, source_size),
                            'outputBytes': size, 'overLimit': size > MAX_OUTPUT_GIF,
                            'budgetBytes': budget, 'overBudget': size > budget,
                            'packets': (size + 231) // 232,
                            'timing': timing, 'removeBg': remove_bg,
                            'loopMs': count * cfg['duration'],
                            'speedClamped': timing['perFrameMs'] > 600 or timing['perFrameMs'] < 60,
                            'palettes': extract_palette(raw),
                            'state': state_payload()})
                image = decode_image(url)
                split = bool(data.get('split', True))
                sprites = charmod.prepare(image, split=split)
                paths = charmod.save_sprites(sprites)
                cfg = read_json(CHAR_FILE, {}) or charmod.default_config(sprites)
                cfg['enabled'] = True
                cfg['files'] = [p.relative_to(ROOT).as_posix() for p in paths]
                cfg['name'] = str(data.get('name') or cfg.get('name') or '自定义角色')[:40]
                n = len(sprites)
                cfg['sequence'] = ([0, 0, 1, 1, 2, 2, 1, 1] if n >= 3 else [0, 0, 1, 1, 0, 0, 1, 1] if n == 2 else [0] * 8)
                if cfg.get('sourceGif'):
                    cfg['motion'] = {'enabled': True, 'frames': 28, 'style': 'gentle'}
                    cfg['frameCount'] = 28
                    cfg['duration'] = 110
                cfg.pop('sourceGif', None)
                cfg.setdefault('box', [188, 42, 300, 154])
                cfg.setdefault('scale', 1.0)
                cfg.setdefault('offsetY', 0)
                cfg.setdefault('bob', [0, 0, -1, -1, 0, 1, 1, 0])
                cfg.setdefault('shadow', True)
                cfg.setdefault('duration', 160)
                write_json(CHAR_FILE, cfg)
                return self.send_json({'ok': True, 'views': len(sprites), 'state': state_payload()})
            if path == '/api/preview':
                colors = validate_colors(data.get('colors'))
                raw_cfg = data.get('character')
                # Preview must never fail because of character state: while
                # painting the pixel icon we only care about the status bar, so
                # an incomplete/absent character renders the stock robot instead
                # of returning 500 (which silently froze the live preview).
                cfg = {}
                if raw_cfg:
                    try:
                        cfg = validate_character(raw_cfg)
                    except Exception:
                        cfg = {}
                icon = preview_icon(data.get('icon') or '')
                bar = data.get('statusbar')
                ink = str(data.get('color') or '').strip().lower()
                if not re.fullmatch(r'#[0-9a-f]{6}', ink):
                    ink = None
                return self.send_bytes(png_bytes(render_preview(colors, cfg, icon, bar, ink)))
            if path == '/api/apply':
                theme_id = str(data.get('themeId') or '')
                if not re.fullmatch(r'[a-z0-9_-]{1,24}', theme_id):
                    raise ValueError('主题 ID 只能是小写字母/数字/下划线/连字符，且不超过 24 字符')
                colors = validate_colors(data.get('colors'))
                cfg = validate_character(data.get('character'))
                name = str(data.get('themeName') or theme_id)[:40]
                custom = read_json(THEMES_FILE, {}) or {}
                custom[theme_id] = {'name': name, **colors}
                write_json(THEMES_FILE, custom)
                cfg['theme'] = theme_id
                write_json(CHAR_FILE, cfg)
                compile_firmware = bool(data.get('compile', True))
                if compile_firmware:
                    if not STOCK.exists():
                        raise ValueError('缺少 inputs/ips-stock.bin，无法编译')
                    clang = find_clang()
                    if not clang:
                        raise ValueError('未找到 clang：请把 llvm-portable 放到程序目录，或安装 LLVM 并加入 PATH')
                    code, output = run_build(
                        ['ips', '--stock', str(STOCK), '--theme', theme_id, '--clang', clang])
                    if code != 0:
                        return self.send_json({'ok': False, 'error': '编译失败', 'log': output}, 500)
                    log = 'IPS 固件重新编译完成\n' + output
                else:
                    with LOCK:
                        assets._CHAR_CFG, assets._CHAR_SPRITES = None, ()
                        assets.generate(KEYS_FILE, theme_id, ASSETS_DIR, None)
                    log = '仅重新生成 S1 动画素材与预览图，未重编固件（主题色未改变时适用）'
                return self.send_json({'ok': True, 'log': log, 'state': state_payload()})
            return self.send_json({'error': '未知接口'}, 404)
        except Exception as e:
            return self.send_json({'ok': False, 'error': str(e), 'trace': traceback.format_exc(limit=3)}, 500)


def _shutdown_soon(delay=0.4):
    """Stop the HTTP server after the 退出程序 response has been flushed."""
    time.sleep(delay)
    srv = _SERVER
    if srv is not None:
        try:
            srv.shutdown()
        except Exception:
            pass


def serve(port=8766, block=True):
    """Start the studio HTTP server. Returns the server object."""
    global _SERVER
    LOCAL.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    _SERVER = srv
    if block:
        srv.serve_forever()
    return srv


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8766)
    a = p.parse_args()
    print(f'Customization studio: http://127.0.0.1:{a.port}/studio/  (Ctrl+C to stop)', flush=True)
    serve(a.port)
