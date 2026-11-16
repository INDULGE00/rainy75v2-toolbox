"""Windows system telemetry for the Rainy75 suite. SPDX-License-Identifier: MIT.

Every probe degrades gracefully: if the OS / sensor / network is unavailable we
return an explicit unavailable result instead of inventing a number.
"""
from __future__ import annotations
import json, subprocess, time, urllib.request
from typing import Optional

try:
    import psutil
except ImportError:
    psutil = None

_WEATHER = {
    0: '晴', 1: '大部晴朗', 2: '局部多云', 3: '阴', 45: '雾', 48: '雾凇',
    51: '小毛毛雨', 53: '毛毛雨', 55: '强毛毛雨', 61: '小雨', 63: '中雨', 65: '大雨',
    71: '小雪', 73: '中雪', 75: '大雪', 80: '阵雨', 81: '中阵雨', 82: '强阵雨',
    95: '雷雨', 96: '雷雨伴冰雹', 99: '强雷雨伴冰雹',
}
_net_prev = None
_net_prev_at = 0.0


def _ps(cmd: str, timeout: int = 12) -> Optional[str]:
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() or None
    except Exception:
        return None


def cpu_usage():
    if psutil:
        try:
            return {'available': True, 'value': round(psutil.cpu_percent(interval=None), 1), 'unit': '%', 'label': 'CPU 使用率'}
        except Exception:
            pass
    out = _ps('(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average')
    try:
        return {'available': True, 'value': round(float(out), 1), 'unit': '%', 'label': 'CPU 使用率'}
    except (TypeError, ValueError):
        return {'available': False, 'label': 'CPU 使用率', 'reason': '系统未提供性能计数器'}


def cpu_temp():
    """ACPI thermal zone is often blocked without admin / unsupported by the OEM."""
    out = _ps('(Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature '
              '-ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty CurrentTemperature)')
    try:
        c = round(float(out) / 10.0 - 273.15, 1)
        if -20 <= c <= 120:
            return {'available': True, 'value': c, 'unit': '°C', 'label': 'CPU 温度'}
    except (TypeError, ValueError):
        pass
    return {'available': False, 'label': 'CPU 温度',
            'reason': '本机未暴露温度探头（部分机型需管理员或 LibreHardwareMonitor）；界面会改显示 CPU 使用率'}


def net_speed():
    global _net_prev, _net_prev_at
    now = time.time()
    if psutil:
        try:
            cur = psutil.net_io_counters()
            cur = (cur.bytes_sent, cur.bytes_recv)
            dt = max(0.2, now - _net_prev_at) if _net_prev_at else 1.0
            up = dn = 0.0
            if _net_prev:
                up = max(0.0, (cur[0] - _net_prev[0]) / dt / 1024)
                dn = max(0.0, (cur[1] - _net_prev[1]) / dt / 1024)
            _net_prev, _net_prev_at = cur, now
            return {'available': True, 'up': round(up, 1), 'down': round(dn, 1), 'unit': 'KB/s', 'label': '网速'}
        except Exception:
            pass
    return {'available': False, 'label': '网速', 'reason': '缺少 psutil，执行 pip install psutil 可启用'}


def weather(lat: float, lon: float):
    url = ('https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s'
           '&current=temperature_2m,relative_humidity_2m,weather_code&timezone=auto' % (lat, lon))
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            d = json.loads(r.read())
        cur = d.get('current') or {}
        code = int(cur.get('weather_code', -1))
        return {'available': True, 'temp': cur.get('temperature_2m'),
                'humidity': cur.get('relative_humidity_2m'),
                'desc': _WEATHER.get(code, '天气代码 %s' % code), 'label': '天气'}
    except Exception as e:
        return {'available': False, 'label': '天气', 'reason': '天气服务暂不可达（%s）' % type(e).__name__}


def snapshot(cfg):
    m = cfg.get('monitor', {})
    return {
        'cpuUsage': cpu_usage(),
        'cpuTemp': cpu_temp(),
        'net': net_speed(),
        'weather': weather(m.get('lat', 39.9042), m.get('lon', 116.4074)),
        'at': time.strftime('%H:%M:%S'),
    }
