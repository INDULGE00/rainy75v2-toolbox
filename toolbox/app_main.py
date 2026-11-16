"""Frozen entry point for the Rainy75 toolbox .exe (single file, offline).

What it does, in order:

1. Work out a *writable* root. A PyInstaller onefile build unpacks itself into a
   throwaway temp directory, but the studio compiles firmware and writes preview
   images, so the app has to live somewhere persistent. On first launch the
   bundled ``payload.zip`` is expanded into ``%LOCALAPPDATA%\\Rainy75Toolbox\\app``.
2. Point the studio at that root (``RAINY75_ROOT``) and at the bundled clang
   (``RAINY75_CLANG``), then start the HTTP server *in this process* - a frozen
   exe cannot spawn ``python tools/studio.py``.
3. Open the toolbox in a Chrome/Edge app window with a dedicated profile, so
   closing that window ends the browser process and therefore this program.

Run from source for development: ``python toolbox/app_main.py --check``
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

# The studio server is imported from the extracted payload at runtime, so the
# freezer cannot see what it needs. Pull in its stdlib and PIL dependencies here
# so a single-file build actually contains them.
import base64  # noqa: F401,E402
import collections  # noqa: F401,E402
import contextlib  # noqa: F401,E402
import hashlib  # noqa: F401,E402
import html  # noqa: F401,E402
import http.client  # noqa: F401,E402
import http.server  # noqa: F401,E402
import importlib  # noqa: F401,E402
import io  # noqa: F401,E402
import json  # noqa: F401,E402
import math  # noqa: F401,E402
import mimetypes  # noqa: F401,E402
import re  # noqa: F401,E402
import shutil  # noqa: F401,E402
import socketserver  # noqa: F401,E402
import struct  # noqa: F401,E402
import urllib.parse  # noqa: F401,E402
import zlib  # noqa: F401,E402

import PIL  # noqa: F401,E402
import PIL.GifImagePlugin  # noqa: F401,E402
import PIL.Image  # noqa: F401,E402
import PIL.ImageChops  # noqa: F401,E402
import PIL.ImageDraw  # noqa: F401,E402
import PIL.ImageFilter  # noqa: F401,E402
import PIL.ImageFont  # noqa: F401,E402
import PIL.JpegImagePlugin  # noqa: F401,E402
import PIL.PngImagePlugin  # noqa: F401,E402

QUIET = False  # --check mode: never block on a modal dialog

# Loopback must never go through a system proxy. Windows machines running Clash /
# v2ray / corporate proxies export HTTP_PROXY, and urllib honours it even for
# 127.0.0.1 - which made the startup health check hang and the window never open.
_LOOPBACK = ['127.0.0.1', 'localhost', '::1']
_have = [p.strip() for p in os.environ.get('NO_PROXY', '').split(',') if p.strip()]
os.environ['NO_PROXY'] = ','.join(dict.fromkeys(_LOOPBACK + _have))
os.environ['no_proxy'] = os.environ['NO_PROXY']

APP_VERSION = '1.0.0'
APP_NAME = 'Rainy75Toolbox'
DEFAULT_PORT = 8766


def frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def user_base() -> Path:
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
    return Path(base) / APP_NAME


def log(msg: str) -> None:
    """Append to a log file; the app runs without a console."""
    try:
        logs = user_base() / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(logs / 'toolbox.log', 'a', encoding='utf-8') as fh:
            for line in str(msg).splitlines() or ['']:
                fh.write(f'[{stamp}] {line}\n')
    except Exception:
        pass


def fail(message: str) -> None:
    """Report a startup failure without a console window."""
    log('FATAL ' + message)
    if QUIET:
        print('FATAL ' + message)
        raise SystemExit(1)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, 'Rainy75 工具箱 · 启动失败', 0x10)
    except Exception:
        pass
    raise SystemExit(1)


def extract_payload(dest: Path) -> None:
    """Expand payload.zip into ``dest``, keeping the user's local/ and build/."""
    archive = Path(getattr(sys, '_MEIPASS', '.')) / 'payload.zip'
    if not archive.exists():
        fail(f'安装包损坏：缺少内置资源 {archive}')
    keep: dict[str, bytes] = {}
    for rel in ('local/character.json', 'local/themes.json', 'local/character.gif'):
        p = dest / rel
        if p.exists():
            keep[rel] = p.read_bytes()
    dest.mkdir(parents=True, exist_ok=True)
    log(f'extracting payload -> {dest}')
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)
    for rel, data in keep.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (dest / '.version').write_text(payload_signature(), encoding='utf-8')


def payload_signature() -> str:
    """Identify the bundled payload so a rebuilt exe re-extracts automatically."""
    archive = Path(getattr(sys, '_MEIPASS', '.')) / 'payload.zip'
    try:
        h = hashlib.sha256()
        with open(archive, 'rb') as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b''):
                h.update(chunk)
        return f'{APP_VERSION}:{h.hexdigest()[:16]}'
    except Exception:
        return APP_VERSION


def resolve_root() -> Path:
    """Return the writable application root and unpack the payload if needed."""
    here = Path(__file__).resolve()
    if not frozen():
        return here.parents[1]
    dest = user_base() / 'app'
    marker = dest / '.version'
    want = payload_signature()
    try:
        current = marker.read_text(encoding='utf-8').strip()
    except Exception:
        current = ''
    if current != want or not (dest / 'web' / 'flash-wizard.html').exists():
        try:
            extract_payload(dest)
        except SystemExit:
            raise
        except Exception:
            fail('解压内置资源失败：\n\n' + traceback.format_exc(limit=3))
    return dest


def port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def http_ok(url: str, timeout: float = 2.0) -> bool:
    """GET ``url`` over a direct socket - deliberately not urllib, which would
    route loopback requests through HTTP_PROXY when that env var is set."""
    parts = urllib.parse.urlsplit(url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=timeout)
    try:
        conn.request('GET', parts.path or '/')
        resp = conn.getresponse()
        resp.read(1024)
        return 200 <= resp.status < 400
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def find_title_window(keyword: str = 'Rainy75', timeout: float = 0.0) -> bool:
    """True if a visible top-level window whose title contains ``keyword`` exists.

    The Chrome ``--app`` window belongs to a child process, so this is the only
    reliable way to know the page actually appeared instead of silently failing.
    """
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if keyword in buf.value:
                    found.append(buf.value)
        return True

    deadline = time.time() + timeout
    while True:
        found.clear()
        try:
            user32.EnumWindows(visit, 0)
        except Exception:
            return False
        if found:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.4)


def find_browser() -> str | None:
    pf = os.environ.get('PROGRAMFILES', r'C:\Program Files')
    pf86 = os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')
    local = os.environ.get('LOCALAPPDATA', '')
    for c in (rf'{pf}\Google\Chrome\Application\chrome.exe',
              rf'{pf86}\Google\Chrome\Application\chrome.exe',
              rf'{local}\Google\Chrome\Application\chrome.exe',
              rf'{pf86}\Microsoft\Edge\Application\msedge.exe',
              rf'{pf}\Microsoft\Edge\Application\msedge.exe'):
        if c and Path(c).exists():
            return c
    return None


def start_server(root: Path, port: int):
    """Import the studio module and serve in a background thread."""
    sys.path.insert(0, str(root / 'tools'))
    os.environ['RAINY75_ROOT'] = str(root)
    clang = root / 'llvm' / 'bin' / 'clang.exe'
    if clang.exists():
        os.environ.setdefault('RAINY75_CLANG', str(clang))
    import studio  # noqa: E402  (needs RAINY75_ROOT set first)

    srv = studio.serve(port, block=False)
    thread = threading.Thread(target=srv.serve_forever, daemon=True, name='rainy75-http')
    thread.start()
    return srv, thread


def open_window(url: str) -> subprocess.Popen | None:
    exe = find_browser()
    if not exe:
        webbrowser.open(url)
        return None
    profile = user_base() / 'browser'
    profile.mkdir(parents=True, exist_ok=True)
    # A dedicated profile gives this window its own browser process, so we can
    # tell when it closes. It also keeps the HID chooser settings consistent.
    args = [exe, f'--app={url}', '--window-size=1400,940',
            f'--user-data-dir={profile}', '--no-first-run',
            '--no-default-browser-check', '--disable-features=Translate']
    return subprocess.Popen(args)


def open_default_browser(url: str) -> bool:
    """Last resort: hand the URL to whatever the user has registered."""
    try:
        os.startfile(url)  # noqa: S606 - Windows shell open
        return True
    except Exception:
        log('os.startfile failed: ' + traceback.format_exc(limit=2))
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def wait_until_closed(still_serving, grace_misses: int = 5) -> str:
    """Block until the app window is gone or the server is told to stop.

    Chrome re-creates its window while the first page loads and the launcher
    process exits on its own, so a single negative probe means nothing: only a
    run of consecutive misses counts as "the user closed the window".
    """
    misses = 0
    while still_serving():
        if find_title_window('Rainy75', 1.2):
            misses = 0
        else:
            misses += 1
            if misses >= grace_misses:
                return 'app window closed'
        time.sleep(0.4)
    return 'server stopped'


def ensure_stdio() -> None:
    """Give a console-less (windowed) build usable stdio.

    PyInstaller sets sys.stdout/sys.stderr to None when built with console=False.
    Anything that writes to them then raises AttributeError - and http.server
    logs every /api/ request to stderr, which silently killed those requests and
    made the app look dead even though it was listening. Point both at a log
    file so logging works and crashes stay debuggable.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        path = user_base() / 'logs' / 'console.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(path, 'a', encoding='utf-8', buffering=1)
    except Exception:
        stream = open(os.devnull, 'w', encoding='utf-8')
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def main() -> int:
    if not frozen():
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except Exception:
            pass
    else:
        ensure_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--check', action='store_true', help='start, self-test, exit')
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args()
    global QUIET
    QUIET = args.check

    try:
        root = resolve_root()
        log(f'root={root} frozen={frozen()} no_proxy={os.environ.get("NO_PROXY")}')
        port, srv, srv_thread, reused = args.port, None, None, False
        if http_ok(f'http://127.0.0.1:{port}/api/state'):
            reused = True
            print(f'another instance already serves {port}; reusing it')
            log(f'reusing existing server on {port}')
        else:
            while not port_free(port):
                port += 1
                if port > args.port + 20:
                    fail('127.0.0.1 上 8766 起 20 个端口都被占用，无法启动本地服务。\n\n'
                         '请关闭占用端口的程序后重试，或先用 --port 8790 手动指定端口。')
            log(f'starting server on {port}')
            srv, srv_thread = start_server(root, port)
            deadline = time.time() + 60
            while time.time() < deadline:
                if http_ok(f'http://127.0.0.1:{port}/api/state'):
                    break
                time.sleep(0.3)
            else:
                fail('本地服务没有在 60 秒内响应。\n\n'
                     '端口 ' + str(port) + ' 已被本程序监听但页面接口无应答。\n'
                     '请把下面的日志发给开发者：\n' + str(user_base() / 'logs' / 'toolbox.log'))

        base = f'http://127.0.0.1:{port}'
        pages = {'/toolbox/': 'toolbox hub',
                 '/web/flash-wizard.html': 'flash wizard',
                 '/studio/index.html': 'theme studio',
                 '/web/diagnose.html': 'diagnostics',
                 '/toolbox/firmware/info.json': 'firmware snapshot'}
        # The publishable build intentionally ships no factory firmware, so a
        # missing snapshot is not a failure there.
        optional = {'/toolbox/firmware/info.json'}
        bad = []
        for path, name in pages.items():
            ok = http_ok(base + path)
            print(f'  {"OK  " if ok else "FAIL"}  {path}  ({name})')
            log(f'{"OK" if ok else "FAIL"} {path}')
            if not ok and path not in optional:
                bad.append(name)
        if bad:
            log('WARNING not all pages answered: ' + ', '.join(bad))

        if args.check:
            print('all pages ok' if not bad else 'some pages failed')
            if srv:
                srv.shutdown()
            return 0 if not bad else 1

        url = base + '/toolbox/'
        print('toolbox:', url)
        log(f'serving {url}')
        if args.no_browser:
            # Serve only: useful for debugging or pointing an existing browser at it.
            print('no window requested; serving until Ctrl+C')
            try:
                while srv_thread is None or srv_thread.is_alive():
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
            if srv:
                srv.shutdown()
            return 0

        srv_thread_alive = (lambda: srv_thread.is_alive()) if srv_thread else (lambda: True)
        proc = open_window(url)
        if find_title_window('Rainy75', 20.0):
            log('app window is visible')
        else:
            # Chrome/Edge app mode failed or is unavailable: fall back to the
            # default browser so the user still gets a working page.
            log('no app window within 20s; falling back to the default browser')
            if not open_default_browser(url):
                fail('没能自动打开浏览器。\n\n请手动在浏览器里访问：\n' + url +
                     '\n\n（推荐 Chrome / Edge，WebHID 只在 Chromium 内核浏览器里可用）')
            log('opened in the default browser; the window close cannot be detected, '
                'use the 退出程序 button in the page to stop the app')

        if proc is not None:
            log(f'browser launcher pid {proc.pid} (window tracked by title)')
        reason = wait_until_closed(srv_thread_alive)
        log(f'exiting: {reason}')
        if srv:
            srv.shutdown()
        return 0
    except SystemExit:
        raise
    except Exception:
        fail('程序异常退出：\n\n' + traceback.format_exc(limit=4))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
