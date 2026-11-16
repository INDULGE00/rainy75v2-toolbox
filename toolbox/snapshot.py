"""Bundle the currently compiled firmware into toolbox/firmware as a snapshot.

The toolbox ships this snapshot so the flashing wizard always has the exact
firmware that is known to work, even after build/ gets recompiled for a new
theme. Run again after any recompile you want to freeze.

Usage: python toolbox/snapshot.py
"""
from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / 'firmware'


def read_json(p: Path):
    return json.loads(p.read_text(encoding='utf8'))


def main() -> int:
    main_bin = ROOT / 'build/main/rainy75v2-main.bin'
    main_man = ROOT / 'build/main/manifest.json'
    ips_bin = ROOT / 'build/ips/rainy75v2-ips.bin'
    ips_man = ROOT / 'build/ips/manifest.json'
    for p in (main_bin, main_man, ips_bin, ips_man):
        if not p.exists():
            print(f'missing: {p.relative_to(ROOT)}  (run the builder first)', file=sys.stderr)
            return 1

    mm, im = read_json(main_man), read_json(ips_man)
    theme = im.get('theme') or 'ocean'
    assets = ROOT / 'build/ips/assets'
    gif = assets / f'robot-{theme}.gif'
    lite = assets / f'robot-{theme}-lite.gif'
    blank = assets / f'robot-{theme}-blank.gif'
    preview = assets / f'preview-{theme}.png'
    if not gif.exists():
        print(f'missing: {gif.relative_to(ROOT)}', file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(main_bin, OUT / 'main.bin')
    shutil.copyfile(main_man, OUT / 'main.json')
    shutil.copyfile(ips_bin, OUT / 'ips.bin')
    shutil.copyfile(ips_man, OUT / 'ips.json')
    shutil.copyfile(gif, OUT / 's1-full.gif')
    for src, dst in ((lite, 's1-lite.gif'), (blank, 's1-blank.gif'), (preview, 'preview.png')):
        if src.exists():
            shutil.copyfile(src, OUT / dst)
        else:
            (OUT / dst).unlink(missing_ok=True)

    try:
        from PIL import Image
        with Image.open(gif) as probe:
            frames = getattr(probe, 'n_frames', 1)
            duration = probe.info.get('duration') or 0
    except Exception:  # PIL optional at snapshot time
        frames, duration = 0, 0

    info = {
        'capturedAt': __import__('datetime').datetime.now().astimezone().isoformat(timespec='seconds'),
        'theme': theme,
        'themeName': theme,
        'main': {'bytes': mm.get('bytes'), 'sha256': mm.get('sha256'),
                 'stockSha256': mm.get('stockSha256'), 'stockVersion': mm.get('stockVersion')},
        'ips': {'bytes': im.get('bytes'), 'sha256': im.get('sha256'),
                'stockSha256': im.get('stockSha256'), 'uiVersion': im.get('uiVersion'),
                'protocol': im.get('protocol')},
        's1': {'bytes': gif.stat().st_size, 'frames': frames, 'frameMs': duration,
               'packets': -(-gif.stat().st_size // 232)},
    }
    (OUT / 'info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print(f'\nsnapshot -> {OUT.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
