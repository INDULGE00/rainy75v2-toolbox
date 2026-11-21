"""Rainy75 Windows suite: unified local console. SPDX-License-Identifier: MIT.

Only listens on 127.0.0.1. Device detection, telemetry, display configuration,
countdown / pomodoro state and links to the existing flash / studio tools.
Run: python suite/server.py --port 8770  (or double click suite/start.bat)
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, threading, time, traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'local'
CONFIG = LOCAL / 'suite-config.json'
sys.path.insert(0, str(Path(__file__).resolve().parent))
import monitor  # noqa: E402

LINKS = {
    'wizard': 'http://127.0.0.1:8765/web/flash-wizard.html',
    'studio': 'http://127.0.0.1:8766/studio/',
    'workbench': 'http://127.0.0.1:8765/web/',
    'diagnose': 'http://127.0.0.1:8765/web/diagnose.html',
}
CITIES = {
    '北京': (39.9042, 116.4074), '上海': (31.2304, 121.4737),
    '广州': (23.1291, 113.2644), '深圳': (22.5431, 114.0579),
    '成都': (30.5728, 104.0668), '杭州': (30.2741, 120.1551),
}
DEFAULT_CONFIG = {
    'display': {'clock': True, 'battery': True, 'mode': True, 'bigKey': True, 'character': True,
                'countdown': False, 'pomodoro': False, 'cpuTemp': False, 'netSpeed': False, 'weather': False},
    'layout': 'balanced',
    'monitor': {'intervalSec': 5, 'city': '北京', 'lat': 39.9042, 'lon': 116.4074},
    'timer': {'mode': 'pomodoro', 'countdownSec': 300, 'workMin': 25, 'breakMin': 5, 'rounds': 4},
    'autoMode': True,
}
_lock = threading.Lock()
_cache = {'monitor': None, 'at': 0.0}
_timer = {'running': False, 'endsAt': 0.0, 'remaining': 0, 'phase': 'work', 'round': 1, 'finished': False}


def read_config():
    try:
        raw = json.loads(CONFIG.read_text(encoding='utf8'))
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        for k, v in raw.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        return cfg
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT_CONFIG))


def write_config(cfg):
    LOCAL.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def detect_device():
    cmd = ("Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
           "Where-Object { $_.DeviceID -match 'VID_36B0' } | ForEach-Object { $_.DeviceID }")
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', cmd],
                           capture_output=True, text=True, timeout=20)
        text = r.stdout or ''
    except Exception as e:
        return {'connected': False, 'pids': [], 'error': str(e)}
    pids = sorted(set(re.findall(r'PID_([0-9A-Fa-f]{4})', text.upper())))
    state = 'offline'
    if '3079' in pids:
        state = 'iap-main'
    elif '3078' in pids:
        state = 'iap-ips'
    elif '3075' in pids:
        state = 'app'
    elif '3071' in pids:
        state = 'receiver'
    return {'connected': state != 'offline', 'pids': pids, 'state': state,
            'label': {'app': 'USB 正常模式', 'iap-main': '主控升级模式', 'iap-ips': '屏幕升级模式',
                      'receiver': '2.4G 接收器', 'offline': '未检测到键盘'}[state]}


def theme():
    try:
        m = json.loads((ROOT / 'build' / 'ips' / 'manifest.json').read_text(encoding='utf8'))
        tid = m.get('theme', 'ocean')
        custom = json.loads((LOCAL / 'themes.json').read_text(encoding='utf8'))
        shipped = json.loads((ROOT / 'profiles' / 'themes.json').read_text(encoding='utf8'))
        c = {**shipped, **custom}.get(tid, {})
        return {'id': tid, 'name': c.get('name', tid), **{k: v for k, v in c.items() if k != 'name'}}
    except Exception:
        return {'id': 'ocean', 'name': '大肥鱼', 'background': '#eaf2fd', 'shell': '#a9c6ef',
                'ink': '#22418c', 'accent': '#3f7fd8', 'panel': '#f7fbff'}


def timer_view():
    t = dict(_timer)
    if t['running']:
        t['remaining'] = max(0, int(t['endsAt'] - time.time()))
        if t['remaining'] == 0:
            advance()
            t = dict(_timer)
    return t


def duration_for(cfg, phase):
    t = cfg.get('timer', {})
    if t.get('mode') == 'countdown':
        return int(t.get('countdownSec', 300))
    return int(t.get('workMin', 25) if phase == 'work' else t.get('breakMin', 5)) * 60


def _advance_unlocked():
    cfg = read_config()
    nxt = 'break' if _timer['phase'] == 'work' else 'work'
    if nxt == 'work':
        _timer['round'] = _timer['round'] + 1
    _timer['phase'] = nxt
    _timer['running'] = False
    _timer['remaining'] = duration_for(cfg, nxt)
    _timer['finished'] = False


def advance():
    with _lock:
        _advance_unlocked()


def timer_action(body):
    cfg = read_config()
    action = body.get('action')
    with _lock:
        if action == 'start':
            if _timer['remaining'] <= 0 or _timer['finished']:
                _timer['remaining'] = duration_for(cfg, _timer['phase'])
            _timer['endsAt'] = time.time() + _timer['remaining']
            _timer['running'] = True
            _timer['finished'] = False
        elif action == 'pause':
            if _timer['running']:
                _timer['remaining'] = max(0, int(_timer['endsAt'] - time.time()))
            _timer['running'] = False
        elif action == 'reset':
            _timer['running'] = False
            _timer['phase'] = 'work'
            _timer['round'] = 1
            _timer['finished'] = False
            _timer['remaining'] = duration_for(cfg, 'work')
        elif action == 'skip':
            _advance_unlocked()
    return timer_view()


def collector():
    """Background telemetry so /api/status never blocks on WMI / network calls."""
    while True:
        cfg = read_config()
        try:
            _cache['monitor'] = monitor.snapshot(cfg)
            _cache['at'] = time.time()
        except Exception as e:
            _cache['monitor'] = {'error': str(e), 'at': time.strftime('%H:%M:%S')}
        time.sleep(max(2, int(cfg.get('monitor', {}).get('intervalSec', 5))))


def telemetry():
    return _cache['monitor'] or {'pending': True, 'at': time.strftime('%H:%M:%S')}


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript'}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' blob: data:; connect-src 'self'; object-src 'none'")
        super().end_headers()

    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        size = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(size) or b'{}')

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == '/api/status':
                cfg = read_config()
                dev = detect_device()
                auto = bool(cfg.get('autoMode', True))
                mode = 'pc' if (auto and dev.get('state') == 'app') else 'standalone'
                if dev.get('state', '').startswith('iap'):
                    mode = 'iap'
                return self.send_json({
                    'ok': True, 'config': cfg, 'device': dev, 'mode': mode,
                    'modeLabel': {'pc': 'PC 增强模式', 'standalone': '独立模式',
                                  'iap': '固件升级模式'}[mode],
                    'timer': timer_view(), 'monitor': telemetry(),
                    'theme': theme(), 'links': LINKS, 'cities': CITIES,
                })
            if path == '/api/theme':
                return self.send_json({'ok': True, 'theme': theme()})
            return super().do_GET()
        except Exception as e:
            return self.send_json({'ok': False, 'error': str(e)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.body()
            if path == '/api/config':
                cfg = read_config()
                for k, v in data.items():
                    if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                        cfg[k].update(v)
                    else:
                        cfg[k] = v
                city = cfg.get('monitor', {}).get('city')
                if city in CITIES:
                    cfg['monitor']['lat'], cfg['monitor']['lon'] = CITIES[city]
                write_config(cfg)
                _cache['monitor'] = None
                return self.send_json({'ok': True, 'config': cfg})
            if path == '/api/timer':
                return self.send_json({'ok': True, 'timer': timer_action(data)})
            if path == '/api/refresh':
                cfg = read_config()
                _cache['monitor'] = monitor.snapshot(cfg)
                _cache['at'] = time.time()
                return self.send_json({'ok': True, 'monitor': _cache['monitor']})
            return self.send_json({'ok': False, 'error': '未知接口'}, 404)
        except Exception as e:
            return self.send_json({'ok': False, 'error': str(e), 'trace': traceback.format_exc(limit=2)}, 500)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8770)
    a = p.parse_args()
    LOCAL.mkdir(parents=True, exist_ok=True)
    _timer['remaining'] = duration_for(read_config(), 'work')
    threading.Thread(target=collector, daemon=True).start()
    print('Rainy75 suite: http://127.0.0.1:%d/suite/  (Ctrl+C to stop)' % a.port, flush=True)
    ThreadingHTTPServer(('127.0.0.1', a.port), Handler).serve_forever()
