"""Build the standalone Windows .exe for the Rainy75 toolbox.

  python toolbox/make_exe.py              # payload + PyInstaller onefile build
  python toolbox/make_exe.py --payload    # only rebuild payload.zip
  python toolbox/make_exe.py --no-clang   # smaller exe, no in-app compile

Payload contents: everything the offline app needs to run and to *recompile*
firmware (web UI, studio server, tools, firmware sources, factory inputs, the
current build, the current S1 animation, the bundled snapshot and clang + lld).

The default build is the "开箱即刷" one: factory inputs + toolbox/firmware are
included so the wizard can flash without asking for ips-stock.bin. Use
--compliant only when you must publish a build without factory binaries.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLBOX = ROOT / 'toolbox'
PAYLOAD = TOOLBOX / 'payload.zip'
DIST = ROOT / 'dist'

# Whole directories, minus the noise PyInstaller or the editor leaves behind.
DIRS = ['tools', 'web', 'studio', 'toolbox', 'profiles', 'inputs', 'build', 'firmware']
FILES = ['README.md', 'LICENSE', 'DISCLAIMER.md', 'THIRD_PARTY_NOTICES.md']
# User state that must survive a fresh extraction (studio settings + artwork).
LOCAL_FILES = ['themes.json', 'character.json', 'character.gif']
SKIP_SUFFIX = {'.pyc', '.pyo', '.log', '.zip', '.spec', '.bak'}
SKIP_NAMES = {'__pycache__', '.DS_Store', 'Thumbs.db', 'node_modules', 'pybuild', 'dist'}


def find_toolchain() -> tuple[Path | None, Path | None]:
    """Locate clang.exe and ld.lld.exe (portable llvm next to the repo)."""
    cands = [Path(os.environ.get('RAINY75_CLANG'))] if os.environ.get('RAINY75_CLANG') else []
    for base in (ROOT, ROOT.parent):
        cands += sorted(base.glob('llvm/bin/clang.exe')) + sorted(base.glob('llvm/*/bin/clang.exe'))
        cands += sorted(base.glob('llvm-portable/bin/clang.exe')) + sorted(base.glob('llvm-portable/*/bin/clang.exe'))
    for c in cands:
        if c and c.exists():
            lld = c.parent / 'ld.lld.exe'
            return c, (lld if lld.exists() else None)
    return None, None


def walk(folder: Path):
    for path in sorted(folder.rglob('*')):
        if not path.is_file():
            continue
        parts = set(path.parts)
        if parts & SKIP_NAMES or path.suffix.lower() in SKIP_SUFFIX:
            continue
        yield path


def build_payload(with_clang: bool = True, with_firmware: bool = True,
                  with_user_assets: bool = True) -> Path:
    entries: list[tuple[Path, str]] = []
    # `--compliant` drops everything that is not ours: the factory firmware blobs
    # (WOB copyright, not MIT) and the LLVM toolchain. Such an exe asks the user to
    # import their own ips-stock.bin and to bring pre-built .bin files.
    dirs = [d for d in DIRS if with_firmware or d not in ('build', 'inputs')]
    for name in dirs:
        folder = ROOT / name
        if not folder.is_dir():
            print(f'  skip (missing): {name}')
            continue
        for p in walk(folder):
            rel = p.relative_to(ROOT).as_posix()
            if not with_firmware and (rel.startswith('toolbox/firmware/')
                                      or rel.startswith('build/')
                                      or rel.startswith('inputs/')):
                continue
            entries.append((p, rel))
    for name in FILES:
        p = ROOT / name
        if p.exists():
            entries.append((p, name))
    for name in LOCAL_FILES:
        # User artwork (character.gif and its sprite frames) is often taken from
        # the internet; a public build must not carry third-party art.
        if not with_user_assets and name in ('character.gif', 'character.json'):
            continue
        p = ROOT / 'local' / name
        if p.exists():
            entries.append((p, f'local/{name}'))
    # Sprite frames referenced by local/character.json (small, but without them
    # a clean install cannot apply the preloaded character).
    views = ROOT / 'local' / 'views'
    if with_user_assets and views.is_dir():
        for p in walk(views):
            entries.append((p, p.relative_to(ROOT).as_posix()))

    if with_clang:
        clang, lld = find_toolchain()
        if not clang or not lld:
            print('ERROR: clang/ld.lld not found. Pass --no-clang to build without the compiler.')
            raise SystemExit(1)
        entries.append((clang, 'llvm/bin/clang.exe'))
        entries.append((lld, 'llvm/bin/ld.lld.exe'))
        print(f'  toolchain: {clang} ({clang.stat().st_size / 1e6:.0f} MB)')

    if PAYLOAD.exists():
        PAYLOAD.unlink()
    t0 = time.time()
    with zipfile.ZipFile(PAYLOAD, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, arc in entries:
            zf.write(src, arc)
    size = PAYLOAD.stat().st_size
    print(f'payload: {len(entries)} files -> {PAYLOAD.name} '
          f'({size / 1e6:.1f} MB, {time.time() - t0:.1f}s)')
    return PAYLOAD


def build_exe(name: str = 'Rainy75Toolbox') -> Path:
    # PyInstaller refuses --name together with a .spec file, so the spec owns the
    # internal name and we rename the artefact afterwards when a variant is wanted.
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
           '--distpath', str(DIST), '--workpath', str(TOOLBOX / 'pybuild'),
           str(TOOLBOX / 'Rainy75Toolbox.spec')]
    print('running:', ' '.join(cmd[-2:]))
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        raise SystemExit(f'PyInstaller failed with code {proc.returncode}')
    built = DIST / 'Rainy75Toolbox.exe'
    if not built.exists():
        raise SystemExit('PyInstaller reported success but no exe was produced')
    if name != 'Rainy75Toolbox':
        target = DIST / f'{name}.exe'
        target.unlink(missing_ok=True)
        shutil.copy2(built, target)
        return target
    return built


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--payload', action='store_true', help='only rebuild payload.zip')
    ap.add_argument('--no-clang', action='store_true', help='build a smaller exe without the compiler')
    ap.add_argument('--no-firmware', action='store_true',
                    help='leave out factory firmware (inputs/, build/, toolbox/firmware)')
    ap.add_argument('--no-user-assets', action='store_true',
                    help='leave out your own uploaded character art (local/character.gif, local/views)')
    ap.add_argument('--compliant', action='store_true',
                    help='publishable build: no factory firmware, no LLVM, no third-party art '
                         '(implies --no-clang --no-firmware --no-user-assets)')
    ap.add_argument('--out-name', default='Rainy75Toolbox',
                    help='exe base name (default Rainy75Toolbox)')
    args = ap.parse_args()

    with_clang = not (args.no_clang or args.compliant)
    with_firmware = not (args.no_firmware or args.compliant)
    with_user_assets = not (args.no_user_assets or args.compliant)
    build_payload(with_clang=with_clang, with_firmware=with_firmware,
                  with_user_assets=with_user_assets)
    if args.payload:
        return 0
    exe = build_exe(args.out_name)
    print(f'\nDONE: {exe}  ({exe.stat().st_size / 1e6:.1f} MB)')
    omitted = [k for k, v in (('compiler', with_clang), ('factory firmware', with_firmware),
                              ('user artwork', with_user_assets)) if not v]
    if omitted:
        print('NOTE: this build does not include ' + ', '.join(omitted)
              + ' - the user must supply them at runtime.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
