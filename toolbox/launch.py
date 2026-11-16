"""Rainy75 V2 toolbox launcher (offline, single window).

Starts one local server (the customization studio already serves the whole
project, including /toolbox/ and /web/flash-wizard.html), then opens the toolbox
in a Chrome/Edge app window so it looks and behaves like an installed program.

  python toolbox/launch.py            # start + open window, keep running
  python toolbox/launch.py --check    # start, self-test, exit
  python toolbox/launch.py --port 8790 --no-browser

Console output stays ASCII: Chinese Windows consoles default to cp936 and would
garble anything else.
"""
from __future__ import annotations
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def find_browser() -> str | None:
    pf = os.environ.get('PROGRAMFILES', r'C:\Program Files')
    pf86 = os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')
    local = os.environ.get('LOCALAPPDATA', '')
    candidates = [
        rf'{pf}\Google\Chrome\Application\chrome.exe',
        rf'{pf86}\Google\Chrome\Application\chrome.exe',
        rf'{local}\Google\Chrome\Application\chrome.exe',
        rf'{pf86}\Microsoft\Edge\Application\msedge.exe',
        rf'{pf}\Microsoft\Edge\Application\msedge.exe',
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def main() -> int:
    try:  # keep the console informative while the server child keeps running
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8766)
    ap.add_argument('--check', action='store_true', help='self-test then exit')
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args()

    port = args.port
    child = None
    if http_ok(f'http://127.0.0.1:{port}/api/state'):
        print(f'already running on {port}, reusing it')
    else:
        while not port_free(port):
            port += 1
            if port > args.port + 20:
                print('no free port near', args.port)
                return 1
        print(f'starting studio server on 127.0.0.1:{port} ...')
        child = subprocess.Popen(
            [sys.executable, str(ROOT / 'tools' / 'studio.py'), '--port', str(port)],
            cwd=str(ROOT),
        )
        deadline = time.time() + 45
        while time.time() < deadline:
            if http_ok(f'http://127.0.0.1:{port}/api/state'):
                break
            if child.poll() is not None:
                print('server exited during startup - see the error above')
                return 1
            time.sleep(0.3)
        else:
            if child.poll() is None:
                child.terminate()
            print('server did not answer within 45s')
            return 1

    base = f'http://127.0.0.1:{port}'
    url = base + '/toolbox/'
    pages = {
        '/toolbox/': 'toolbox hub',
        '/web/flash-wizard.html': 'flash wizard',
        '/studio/index.html': 'theme studio',
        '/web/diagnose.html': 'diagnostics',
        '/toolbox/firmware/info.json': 'firmware snapshot',
    }
    bad = []
    for path, name in pages.items():
        ok = http_ok(base + path)
        print(f'  {"OK  " if ok else "FAIL"}  {path}  ({name})')
        if not ok:
            bad.append(name)
    if bad:
        print('WARNING: not all pages answered:', ', '.join(bad))
    print(f'toolbox: {url}')

    if not args.check and not args.no_browser:
        exe = find_browser()
        if exe:
            subprocess.Popen([exe, f'--app={url}', '--window-size=1400,940',
                              '--no-first-run', '--no-default-browser-check'])
            print('opened in app window:', Path(exe).name)
        else:
            webbrowser.open(url)
            print('opened in default browser')

    if args.check:
        if child and child.poll() is None:
            child.terminate()
        return 0 if not bad else 1

    print('keep this window open; close it (or press Ctrl+C) to stop the server')
    try:
        if child:
            child.wait()
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        if child and child.poll() is None:
            child.terminate()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
