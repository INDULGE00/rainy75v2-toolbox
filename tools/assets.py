"""Generate editable UI headers and original robot GIFs. SPDX-License-Identifier: MIT."""
import argparse,json,os,re
from pathlib import Path
from PIL import Image,ImageDraw,GifImagePlugin

ROOT=Path(__file__).resolve().parents[1]
# Studio mode is opt-in via env var. With it off, generation stays byte-identical
# to the shipped assets/ GIFs so the repository's own contract tests keep passing.
STUDIO=os.environ.get('RAINY75_STUDIO')=='1'
# Key-card region moved up to y=52 (from y=57) to sit closer to the status bar;
# the factory only repaints y=7..20 so the bar itself cannot move lower.
BASE_REGIONS=[(40,52,120,76),(16,13,94,14),(225,10,24,20),(257,15,22,10),(287,17,23,7),(202,15,15,9)]
# Studio layout centres the big-key region inside the taller, RAINY-free card.
# Only the y coordinate moves; all mask sizes (and the mask total) stay put.
# Region 5 is the caps-lock lamp+letter in the top bar, left of the connection
# icon: filled disc + 'A' = caps on, hollow ring + 'a' = caps off.
STUDIO_REGIONS=[(40,55,120,76),*BASE_REGIONS[1:]]
REGIONS=BASE_REGIONS
def regions():return STUDIO_REGIONS if STUDIO else BASE_REGIONS
# Connection icons, 24x20 1-bit rows, drawn at ui_geo[2] (225,10) by native_ui.c.
# Index order is firmware-defined: 0=USB wired, 1=2.4G wireless, 2=Bluetooth.
# Connection mode is spelled out in a 2 px bold 5x7 font ("USB" / "RF" / "BT").
# Earlier pictograms relied on 1 px outlines, which this panel drops, so thin
# strokes read as "missing pixels"; letters at 2 px strokes survive and stay
# unambiguous at 24x14. Right side order: connection | caps lamp | battery.
MASK_TOTAL=1431
USB_ART = (
    '........................',
    '........................',
    '........................',
    '........................',
    '.##..##..#####.#####....',
    '.##..##.##.....##..##...',
    '.##..##.##.....##..##...',
    '.##..##..####..#####....',
    '.##..##.....##.##..##...',
    '.##..##.....##.##..##...',
    '..####..#####..#####....',
    '........................',
    '........................',
    '........................',
)
RF_ART = (
    '........................',
    '........................',
    '........................',
    '........................',
    '..#####..######.........',
    '..##..##.##.............',
    '..##..##.##.............',
    '..#####..#####..........',
    '..####...##.............',
    '..##.##..##.............',
    '..##..##.##.............',
    '........................',
    '........................',
    '........................',
)
BT_ART = (
    '........................',
    '........................',
    '........................',
    '........................',
    '..#####..######.........',
    '..##..##...##...........',
    '..##..##...##...........',
    '..#####....##...........',
    '..##..##...##...........',
    '..##..##...##...........',
    '..#####....##...........',
    '........................',
    '........................',
    '........................',
)


def _row_bits(rows):
    """Pack 24-wide art rows into three bytes each."""
    blob = []
    for row in rows:
        value = int(row.replace('#', '1').replace('.', '0'), 2)
        blob += [(value >> 16) & 255, (value >> 8) & 255, value & 255]
    return blob


ICONS = [_row_bits(USB_ART), _row_bits(RF_ART), _row_bits(BT_ART)]
# Lowercase 'a' for the caps-off lamp (the 5x7 cache font only carries
# uppercase ASCII, so the two case letters ship as their own 5x7 table).
LOWER_A=('00000','01110','00001','01111','10001','01111','00000')
def load(path):return json.loads(Path(path).read_text(encoding='utf8'))
def load_themes():
 themes=load(ROOT/'profiles/themes.json')
 if STUDIO:
  custom=ROOT/'local'/'themes.json'
  if custom.exists():themes.update(load(custom))
 return themes
try:
 from character import load_config as _character_config,load_sprites as _character_sprites
except ImportError:
 _character_config=_character_sprites=None
try:
 from motion import draw as _motion_draw,frame_count as _motion_frames
except ImportError:
 _motion_draw=_motion_frames=None
_CHAR_CFG=None
_CHAR_SPRITES=()
def character():
 """Optional local character override; only active in studio mode."""
 global _CHAR_CFG,_CHAR_SPRITES
 if not STUDIO:return None
 if _CHAR_CFG is None and _character_config:
  _CHAR_CFG=_character_config() or False
  if _CHAR_CFG and _CHAR_CFG.get('enabled'):_CHAR_SPRITES=_character_sprites(_CHAR_CFG)
 return _CHAR_CFG or None
def draw_character(im,theme,phase,cfg,sprites):
 """Paste one transparent character view in place of the geometric robot."""
 x0,y0,x1,y1=[int(v) for v in cfg.get('box',[188,42,300,154])]
 if (cfg.get('motion') or {}).get('enabled') and _motion_draw:
  return _motion_draw(im,theme,phase,cfg,sprites,(x0,y0,x1,y1))
 scale=float(cfg.get('scale',1.0));offset=int(cfg.get('offsetY',0))
 # A frame-by-frame GIF already carries its own motion. The legacy 8-phase bob
 # was being applied on top of it, making the character visibly jitter up/down.
 gif_playback=bool(cfg.get('sourceGif')) or (cfg.get('motion') or {}).get('style')=='gif'
 bob=0 if gif_playback else (cfg.get('bob') or [0]*8)[phase%8]
 seq=cfg.get('sequence') or [0]*8;sprite=sprites[seq[phase%len(seq)]%len(sprites)]
 # Contain-fit: any source aspect ratio, never stretched, never leaves the character box.
 ratio=min((x1-x0)/sprite.width,(y1-y0)/sprite.height)*scale
 width=max(1,round(sprite.width*ratio));height=max(1,round(sprite.height*ratio))
 view=sprite.resize((width,height),Image.Resampling.LANCZOS)
 if cfg.get('shadow',True):
  ImageDraw.Draw(im).ellipse((x0+6,y1-6,x1-6,y1+4),fill=theme['shell'])
 im.paste(view,(x0+((x1-x0)-width)//2,y1-height+bob+offset),view)
def rgb565(color):
 n=int(color.removeprefix('#'),16);return ((n>>19)&31)<<11|((n>>10)&63)<<5|((n>>3)&31)
def validate_keys(profile):
 seen=set()
 if profile.get('idleTimeoutMs')!=0:raise ValueError('This version retains the last key; idleTimeoutMs must be 0')
 for g in profile['glyphs']:
  rows=g['rows'];key=g['key']
  if key in seen or not isinstance(key,int) or not 1<=key<=65535:raise ValueError('Duplicate/invalid key')
  seen.add(key)
  if not rows or len(rows)>11 or not 1<=len(rows[0])<=16:raise ValueError('Glyph must be 1..16 x 1..11 cells')
  if any(len(row)!=len(rows[0]) or set(row)-{'0','1'} for row in rows):raise ValueError('Invalid glyph cells')
  if len(rows[0])*6>120 or len(rows)*6>76:raise ValueError('Glyph does not fit key region')
 return profile

# --------------------------------------------------------------------------
# Status bar: left slot (time / custom text / rice+fish) and up to three
# right-hand widgets (connection, caps, battery, typing speed, report rate,
# debounce). The layout is baked at compile time so the firmware only walks a
# generated table; see profiles/statusbar.json for the knobs.
# --------------------------------------------------------------------------
STATUSBAR_FILE = ROOT / 'profiles' / 'statusbar.json'
STATUS_TEXT_MAX = 6
STATUS_BOWLS_MAX = 5
# width/height of the icon and value boxes, plus the widget kind the firmware
# switches on: 0 conn, 1 caps, 2 battery, 3 typing speed, 4/5 static values.
STATUS_WIDGETS = {
    'conn':     (24, 14, 0, 0, 0),
    'caps':     (15, 9, 0, 0, 1),
    'battery':  (22, 10, 23, 7, 2),
    'speed':    (10, 10, 23, 7, 3),
    'keys':     (12, 10, 29, 7, 6),
    'rate':     (15, 10, 35, 7, 4),
    'debounce': (19, 10, 33, 7, 5),
}
STATUS_UNITS = {'rate': 'Hz', 'debounce': 'ms'}
STATUS_RIGHT_MAX = 3
STATUS_GAP = 9
STATUS_BAND_Y = 7
STATUS_BAND_H = 14
STATUS_RIGHT_EDGE = 310
CJK_FONTS = ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf',
             'C:/Windows/Fonts/simsun.ttc', 'C:/Windows/Fonts/Deng.ttf',
             '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')


_STATUSBAR_OVERRIDE = None


def status_config():
    """Read and sanitise profiles/statusbar.json (or a live preview override)."""
    cfg = _STATUSBAR_OVERRIDE if _STATUSBAR_OVERRIDE is not None else (
        load(STATUSBAR_FILE) if STATUSBAR_FILE.exists() else {})
    left = cfg.get('left') or {}
    kind = left.get('type', 'time')
    if kind not in ('time', 'text', 'rice'):
        kind = 'time'
    text = ''.join(str(left.get('text') or ''))[:STATUS_TEXT_MAX]
    bowls = max(0, min(STATUS_BOWLS_MAX, int(left.get('bowls') or 0)))
    fish = 1 if int(left.get('fish') or 0) else 0
    if kind == 'text' and not text:
        kind, text = 'time', ''
    right = []
    for wid in cfg.get('right') or []:
        if wid in STATUS_WIDGETS and wid not in right:
            right.append(wid)
    right = right[:STATUS_RIGHT_MAX]
    values = {}
    for key in ('rate', 'debounce'):
        values[key] = str((cfg.get('values') or {}).get(key) or '--')[:4]
    return {'kind': kind, 'text': text, 'bowls': bowls, 'fish': fish,
            'right': right, 'values': values}


_cjk_cache = {}


def cjk_glyph(ch, size=16):
    """Render one character to a 16x16 1-bit cell using a system CJK font."""
    key = (ch, size)
    if key in _cjk_cache:
        return _cjk_cache[key]
    from PIL import ImageFont
    for path in CJK_FONTS:
        if not Path(path).exists():
            continue
        try:
            font = ImageFont.truetype(path, size - 1)
        except OSError:
            continue
        im = Image.new('L', (size, size), 0)
        ImageDraw.Draw(im).text((0, -1), ch, font=font, fill=255)
        im = im.point(lambda v: 255 if v >= 96 else 0)
        rows = []
        for y in range(size):
            row = ''
            for x in range(size):
                row += '1' if im.getpixel((x, y)) else '0'
            rows.append(row)
        _cjk_cache[key] = rows
        return rows
    raise ValueError('需要系统中文字体来生成自定义文字（Windows 一般自带 msyh.ttc）')


def _symbol(size, painter):
    im = Image.new('1', size, 0)
    painter(ImageDraw.Draw(im))
    return im


# 1-bit art copied from the reference grid the user drew (1 cell = 1 px).
RATE_ART = (
    '..#####.#####..',
    '..#####.#####..',
    '..##.##.##.##..',
    '..##.##.##.##..',
    '..##.##.##.##..',
    '..##.##.##.##..',
    '..##.##.##.##..',
    '..##.##.##.##..',
    '####.#####.####',
    '####.#####.####',
)
DEBOUNCE_ART = (
    '......#............',
    '.....###...........',
    '....#####..........',
    '...###.###.....#...',
    '..###...##....#####',
    '#####....##...###..',
    '...#.....###.###...',
    '..........#####....',
    '...........###.....',
    '............#......',
)


def _art(rows):
    im = Image.new('1', (len(rows[0]), len(rows)), 0)
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell == '#':
                im.putpixel((x, y), 1)
    return im


def _sym_rate():
    """Two n's on a shared baseline, exactly as drawn in the reference grid."""
    return _art(RATE_ART)


def _sym_debounce():
    """Heartbeat waveform from the same reference grid."""
    return _art(DEBOUNCE_ART)


def _sym_speed():
    """Speedometer: ring with tick marks, needle to the upper right."""
    def paint(d):
        d.ellipse((0, 0, 9, 9), outline=1)
        d.point((5, 2), fill=1)
        d.point((7, 7), fill=1)
        d.line((4, 5, 7, 2), fill=1)
        d.rectangle((4, 4, 5, 5), fill=1)
    return _symbol((10, 10), paint)


# 12x10 keyboard glyph: a 2px-stroke keycap grid (three keys + space bar).
KEYS_ART = (
    '.##########.',
    '.#..#..#..#.',
    '.##########.',
    '.#..#..#..#.',
    '.##########.',
    '............',
    '.##########.',
    '.#........#.',
    '.##########.',
    '............',
)


def _sym_keys():
    return _art(KEYS_ART)


def _sym_bowl():
    def paint(d):
        d.pieslice((2, 0, 12, 8), 180, 360, fill=1)
        d.line((0, 7, 14, 7), fill=1)
        d.line((0, 8, 14, 8), fill=1)
        d.line((2, 9, 12, 9), fill=1)
        d.line((4, 10, 10, 10), fill=1)
        d.line((6, 11, 8, 11), fill=1)
    return _symbol((15, 12), paint)


def _sym_fish():
    def paint(d):
        d.ellipse((0, 1, 8, 10), outline=1)
        d.polygon([(10, 3), (13, 1), (13, 10), (10, 8)], fill=1)
        d.point((2, 4), fill=1)
    return _symbol((14, 12), paint)


# Rice-bowl icon for the left slot: the shape is a dome sitting in a bowl,
# distilled from the reference photo. It doubles as the "empty" variant after
# an edge pass, and can be replaced by any image through local/left-icon.png.
# Default rice bowl, 20x14 - exactly the pixel-editor / repaint-band limit.
RICE_ART = (
    '......########......',
    '...##############...',
    '.##################.',
    '.##################.',
    '####################',
    '####################',
    '..##............##..',
    '..##............##..',
    '...##..........##...',
    '...##..........##...',
    '....##........##....',
    '....##........##....',
    '.....##########.....',
    '.....##########.....',
)


def _outline(im):
    """Turn a filled 1-bit shape into its 1-pixel border."""
    w, h = im.size
    out = Image.new('1', (w, h), 0)
    for y in range(h):
        for x in range(w):
            if not im.getpixel((x, y)):
                continue
            edge = x == 0 or y == 0 or x == w - 1 or y == h - 1
            if not edge:
                edge = not (im.getpixel((x - 1, y)) and im.getpixel((x + 1, y))
                            and im.getpixel((x, y - 1)) and im.getpixel((x, y + 1)))
            if edge:
                out.putpixel((x, y), 1)
    return out


_LEFT_ICON_OVERRIDE = None


def left_icon():
    """Rice glyph: the pixel-editor drawing in local/left-icon.json if present."""
    if _LEFT_ICON_OVERRIDE is not None:
        return _LEFT_ICON_OVERRIDE
    custom = ROOT / 'local' / 'left-icon.json'
    if custom.exists():
        try:
            data = load(custom)
            rows = [str(r) for r in data.get('rows') or []]
            if rows and len({len(r) for r in rows}) == 1 and set(''.join(rows)) <= {'0', '1'}:
                return _art([r.replace('0', '.').replace('1', '#') for r in rows])
        except Exception:
            pass
    return _art(RICE_ART)


def left_icon_color(theme=None):
    """Custom ink colour for the left icon; defaults to the theme ink."""
    data = {}
    if _LEFT_ICON_OVERRIDE is None:
        custom = ROOT / 'local' / 'left-icon.json'
        if custom.exists():
            try:
                data = load(custom) or {}
            except Exception:
                data = {}
    raw = str(data.get('color') or '').strip()
    if re.fullmatch(r'#[0-9a-fA-F]{6}', raw):
        return raw.lower()
    return theme['ink'] if theme else None


def tight_icon(im):
    """Crop to the drawn pixels so repeated copies sit at a natural gap.

    An icon that only fills part of the editor used to keep its empty margins,
    which put a large blank gap between bowls. Cropping makes the spacing follow
    the artwork instead of the grid.
    """
    bb = im.getbbox()
    if bb and bb[2] > bb[0] and bb[3] > bb[1]:
        return im.crop(bb)
    return im


def _pack(im):
    """Pack a 1-bit image row-major, MSB first (same order as firmware dot())."""
    out = bytearray()
    acc = 0
    n = 0
    for y in range(im.height):
        for x in range(im.width):
            acc = (acc << 1) | (1 if im.getpixel((x, y)) else 0)
            n += 1
            if n == 8:
                out.append(acc)
                acc = 0
                n = 0
    if n:
        out.append(acc << (8 - n))
    return bytes(out)


LOWER_EXTRA = {
    'z': ('00000', '11111', '00010', '00100', '01000', '11111', '00000'),
    's': ('00000', '01111', '10000', '01110', '00001', '11110', '00000'),
    'm': ('00000', '00000', '11010', '10101', '10101', '10101', '00000'),
}


def _paste_text(im, text, x, y, font):
    pos = x
    for ch in text:
        glyph = LOWER_EXTRA.get(ch) or font.get(ch) or font.get('?')
        for yy, row in enumerate(glyph):
            for xx, cell in enumerate(row):
                if cell == '1' and 0 <= pos + xx < im.width and 0 <= y + yy < im.height:
                    im.putpixel((pos + xx, y + yy), 1)
        pos += 6
    return pos


def status_layout(theme):
    """Compute regions, widget table and pre-rendered (static) bitmaps."""
    cfg = status_config()
    font = load(ROOT / 'profiles' / 'font.json')['ascii']
    regions = [(40, 52, 120, 76)] if not STUDIO else [(40, 55, 120, 76)]
    static = {}
    widgets = []
    # ---- left slot (region 1) ----
    if cfg['kind'] == 'rice':
        icon = tight_icon(left_icon())
        gap = 3
        width = 5 * icon.width + 4 * gap
        # Vertically centre a short icon inside the band instead of pinning it.
        iy = STATUS_BAND_Y + max(0, (STATUS_BAND_H - icon.height) // 2)
        regions.append((16, iy, width, icon.height))
        rice = {'w': icon.width, 'h': icon.height, 'filled': _pack(icon),
                'color': left_icon_color(theme)}
    elif cfg['kind'] == 'time':
        # text() draws 7 rows * scale 2 = 14 px; keep the whole glyph inside
        # the factory-repainted band y=7..20.
        regions.append((16, STATUS_BAND_Y, 94, STATUS_BAND_H))
    elif cfg['kind'] == 'text':
        # Mixed ASCII + CJK: ASCII uses the project 5x7 font at 2x (12 px
        # advance, crisp), CJK uses a 14-row system-font cell (16 px advance).
        plan = []
        for ch in cfg['text']:
            if ord(ch) < 128:
                plan.append((ch, 12))
            else:
                plan.append((ch, 16))
        width = max(16, sum(adv for _, adv in plan) - 2)
        res = (16, STATUS_BAND_Y, width, STATUS_BAND_H)
        regions.append(res)
        im = Image.new('1', (width, STATUS_BAND_H), 0)
        pos = 0
        for ch, adv in plan:
            if ord(ch) < 128:
                glyph = font.get(ch) or font.get('?')
                for y, row in enumerate(glyph):
                    for x, cell in enumerate(row):
                        if cell != '1':
                            continue
                        for dy in range(2):
                            for dx in range(2):
                                px, py = pos + x * 2 + dx, 3 + y * 2 + dy
                                if px < width and py < STATUS_BAND_H:
                                    im.putpixel((px, py), 1)
            else:
                cg = cjk_glyph(ch, STATUS_BAND_H)
                for y, row in enumerate(cg):
                    for x, cell in enumerate(row):
                        if cell == '1' and pos + x < width:
                            im.putpixel((pos + x, y), 1)
            pos += adv
        static[1] = _pack(im)
    else:
        width = max(15, cfg['bowls'] * 17 + (17 if cfg['fish'] else 0))
        regions.append((16, 14, width, 12))
        im = Image.new('1', (width, 12), 0)
        bowl, fish = _sym_bowl(), _sym_fish()
        pos = 0
        for _ in range(cfg['bowls']):
            im.paste(bowl, (pos, 0))
            pos += 17
        if cfg['fish']:
            im.paste(fish, (pos + 2, 0))
        static[1] = _pack(im)
    # ---- right widgets, right-aligned with a uniform gap ----
    specs = []
    for wid in cfg['right']:
        iw, ih, tw, th, kind = STATUS_WIDGETS[wid]
        specs.append({'id': wid, 'kind': kind, 'iw': iw, 'ih': ih, 'tw': tw, 'th': th,
                      'total': iw + ((1 if kind >= 3 else 3) + tw if tw else 0)})
    x = STATUS_RIGHT_EDGE
    for spec in reversed(specs):
        x -= spec['total']
        spec['x'] = x
        x -= STATUS_GAP
    for spec in specs:
        # Symbol widgets sit on the same baseline as their value text so the row
        # reads as one line; round badges stay optically centred.
        # 3/4/5 (speed / rate / debounce) share the value baseline; badges and
        # the key counter are optically centred so they line up with battery.
        iy = ((STATUS_BAND_Y + STATUS_BAND_H - 1 - spec['ih']) if spec['kind'] in (3, 4, 5)
              else STATUS_BAND_Y + (STATUS_BAND_H - spec['ih']) // 2)
        icon_slot = len(regions)
        regions.append((spec['x'], iy, spec['iw'], spec['ih']))
        text_slot = 0
        if spec['tw']:
            ty = STATUS_BAND_Y + (STATUS_BAND_H - spec['th']) // 2
            text_slot = len(regions)
            # symbol rows sit tighter than the badge rows so each item reads as
            # one unit instead of two distant parts
            gap = 1 if spec['kind'] >= 3 else 3
            regions.append((spec['x'] + spec['iw'] + gap, ty, spec['tw'], spec['th']))
        widgets.append({'kind': spec['kind'], 'icon': icon_slot, 'text': text_slot})
        if spec['kind'] == 3:                      # typing speed: static icon only
            icon = _sym_speed()
            im = Image.new('1', (spec['iw'], spec['ih']), 0)
            im.paste(icon, ((spec['iw'] - icon.width) // 2, (spec['ih'] - icon.height) // 2))
            static[icon_slot] = _pack(im)
        elif spec['kind'] == 6:                    # cumulative key presses
            im = Image.new('1', (spec['iw'], spec['ih']), 0)
            im.paste(_sym_keys(), ((spec['iw'] - 12) // 2, (spec['ih'] - 10) // 2))
            static[icon_slot] = _pack(im)
        elif spec['kind'] in (4, 5):               # report rate / debounce
            icon = _sym_rate() if spec['kind'] == 4 else _sym_debounce()
            im = Image.new('1', (spec['iw'], spec['ih']), 0)
            im.paste(icon, ((spec['iw'] - icon.width) // 2, (spec['ih'] - icon.height) // 2))
            static[icon_slot] = _pack(im)
            tim = Image.new('1', (spec['tw'], spec['th']), 0)
            key = 'rate' if spec['kind'] == 4 else 'debounce'
            raw = ''.join(ch for ch in cfg['values'][key] if ch.isdigit())
            label = (raw + STATUS_UNITS[key]) if raw else '--'
            used = _paste_text(tim, label, 0, 0, font)
            tim = tim.crop((0, 0, max(1, min(spec['tw'], used - 1)), spec['th']))
            pad = Image.new('1', (spec['tw'], spec['th']), 0)
            pad.paste(tim, ((spec['tw'] - tim.width) // 2, 0))
            static[text_slot] = _pack(pad)
    total = sum((w * h + 7) // 8 for _, _, w, h in regions)
    return {'cfg': cfg, 'regions': regions, 'widgets': widgets,
            'static': static, 'rice': rice if cfg['kind'] == 'rice' else None,
            'total': total}

def headers(keys,theme,out):
 out.mkdir(parents=True,exist_ok=True);font=load(ROOT/'profiles/font.json')
 chars=[chr(c) for c in range(32,97)]+list('{|}~')
 grids=[font['ascii'][c] for c in chars]+[g['rows'] for g in font['icons']]
 rows=['/* SPDX-License-Identifier: MIT; generated editable pixel cells. */','static const unsigned char cache_font[][5]={']
 packed=[]
 for glyph in grids:
  bits=''.join(format(int(r,2),'05b') for r in glyph)
  packed.append([int(bits[i:i+8].ljust(8,'0'),2) for i in range(0,35,8)])
 rows+=[' {'+','.join(str(v) for v in g)+'},' for g in packed]
 rows+=['};','static unsigned glyph_index(unsigned c){if(c>=97&&c<=122)c-=32;if(c>=128&&c<144)return 69+c-128;if(c>=32&&c<=126)return c-32-(c>=123?26:0);return 31;}']
 (out/'cache_font.h').write_text('\n'.join(rows)+'\n',encoding='utf8')
 rows=['/* SPDX-License-Identifier: MIT; generated from profiles. */','#define UI_IDLE_MS 0u','#define UI_USB_RAW 1','#define UI_RF_RAW 0',
         '#define UI_INK '+str(rgb565(theme['ink']))+'u','#define UI_BG '+str(rgb565(theme['background']))+'u',
         '#define UI_PANEL '+str(rgb565(theme['panel']))+'u',
         'typedef struct {u16 x,y,offset,bytes;u8 w,h;} UiRegion;','static const UiRegion ui_geo[]={']
 layout=status_layout(theme)
 offset=0
 for i,(x,y,w,h) in enumerate(layout['regions']):
  size=(w*h+7)//8
  rows.append(' {'+','.join(map(str,[x,y,offset,size,w,h]))+'},');offset+=size
 rows+=['};','#define STATUS_REGION_COUNT '+str(len(layout['regions']))+'u',
        '#define STATUS_MASK_BYTES '+str(layout['total'])+'u',
        '#define STATUS_LEFT_KIND '+str({'time':0,'text':1,'rice':2}[layout['cfg']['kind']])+'u',
        'typedef struct {u8 kind,icon,text;} StatusWidget;','static const StatusWidget status_right[]={']
 for w in layout['widgets']:
  rows.append(' {'+','.join(map(str,[w['kind'],w['icon'],w['text']]))+'},')
 if not layout['widgets']:
  rows.append(' {0,1,0},')
 rows+=['};']
 rice=layout.get('rice')
 # draw_rice() is compiled unconditionally, so left_icon_filled must exist in
 # every build - otherwise selecting time/text fails at link time. When rice
 # is not the active mode, still emit the default bowl as harmless data.
 icon = left_icon()
 filled = rice['filled'] if rice else _pack(icon)
 rows+=['#define LEFT_ICON_W '+str(rice['w'] if rice else icon.width)+'u',
        '#define LEFT_ICON_H '+str(rice['h'] if rice else icon.height)+'u',
        # Ink colour for region 1; only kicks in for the icon mode so time /
        # text keep the normal theme ink.
        '#define LEFT_ICON_RGB '+(str(rgb565(rice['color']))+'u' if rice else 'UI_INK'),
        'static const u8 left_icon_filled[]={',' '+','.join(str(b) for b in filled)+',','};']
 blob=bytearray();offs=[]
 for i in range(len(layout['regions'])):
  if i in layout['static']:
   offs.append(len(blob));blob+=layout['static'][i]
  else:
   offs.append(0xffff)
 rows+=['static const u16 status_static_off[]={']
 rows.append(' '+','.join(str(o) for o in offs)+',')
 rows+=['};','static const u8 status_static_data[]={']
 if not blob:
  blob=bytearray([0])
 rows.append(' '+','.join(str(b) for b in blob)+',')
 rows+=['};','typedef struct {u16 key;u8 w,h;u16 rows[11];} BigGlyph;','static const BigGlyph big_glyphs[]={']
 for g in keys['glyphs']:
  rows.append(' {'+','.join(map(str,[g['key'],len(g['rows'][0]),len(g['rows'])]))+',{'+','.join(str(int(r,2)) for r in g['rows'])+'}},')
 rows+=['};','static const u8 connection_icons[3][42]={']+[' {'+','.join(map(str,r))+'},' for r in ICONS]+['};']
 case_a=[font['ascii']['A'],LOWER_A]
 rows+=['static const u8 case_glyphs[2][7]={']+[' {'+','.join(str(int(r,2)) for r in g)+'},' for g in case_a]+['};']
 (out/'ui_assets.h').write_text('\n'.join(rows)+'\n',encoding='utf8')
 return layout
def base_frame(theme,phase=0):
 im=Image.new('RGB',(320,172),theme['background']);d=ImageDraw.Draw(im)
 if STUDIO:
  # Card starts just under the y=7..20 status band and keeps the original
  # bottom edge, so the gap above the key area is small without wasting space
  # below the character.
  d.rounded_rectangle((8,25,312,164),radius=16,fill=theme['shell'])
  d.rounded_rectangle((12,29,308,160),radius=12,fill=theme['background'])
  d.rounded_rectangle((24,37,176,152),radius=12,fill=theme['ink'])
  d.rounded_rectangle((27,40,173,149),radius=9,fill=theme['panel'])
 else:
  d.rounded_rectangle((7,24,312,165),radius=16,fill=theme['shell'])
  d.rounded_rectangle((12,29,307,160),radius=13,fill=theme['background'])
  d.rounded_rectangle((24,34,176,145),radius=13,fill=theme['ink'])
  d.rounded_rectangle((27,37,173,142),radius=10,fill=theme['panel'])
 cfg=character()
 if cfg and cfg.get('enabled') and _CHAR_SPRITES:
  draw_character(im,theme,phase,cfg,_CHAR_SPRITES)
 else:
  # Original geometric robot: no third-party character/sprite source.
  bob=[0,0,-1,-1,0,1,1,0][phase%8];x,y=218,70+bob
  d.ellipse((205,143,297,151),fill=theme['shell'])
  d.line((x+37,y-12,x+37,y),fill=theme['ink'],width=3);d.rectangle((x+33,y-17,x+41,y-10),fill=theme['accent'])
  d.rounded_rectangle((x,y,x+74,y+50),radius=8,fill=theme['ink'])
  d.rounded_rectangle((x+3,y+3,x+71,y+47),radius=6,fill=theme['panel'])
  if phase==4:
   d.line((x+15,y+19,x+25,y+19),fill=theme['ink'],width=3);d.line((x+49,y+19,x+59,y+19),fill=theme['ink'],width=3)
  else:
   d.rectangle((x+17,y+13,x+24,y+22),fill=theme['ink']);d.rectangle((x+50,y+13,x+57,y+22),fill=theme['ink'])
  d.line((x+28,y+32,x+46,y+32),fill=theme['ink'],width=3)
  d.rectangle((x+20,y+51,x+55,y+68),fill=theme['accent'])
  d.rectangle((x+14,y+69,x+31,y+73),fill=theme['ink']);d.rectangle((x+44,y+69,x+61,y+73),fill=theme['ink'])
  d.line((x+14,y+54,x+5,y+62),fill=theme['ink'],width=3);d.line((x+61,y+54,x+70,y+60-(phase%3)),fill=theme['ink'],width=3)
 if not STUDIO:
  # Pixel label uses this project's cell grids, not a system font.
  font=load(ROOT/'profiles/font.json')['ascii']
  for i,c in enumerate('RAINY'):
   for yy,row in enumerate(font[c]):
    for xx,cell in enumerate(row):
     if cell=='1':d.point((73+i*6+xx,151+yy),fill=theme['ink'])
 return im
def _unpack(blob,w,h):
    im=Image.new('1',(w,h),0);i=0
    for y in range(h):
        for x in range(w):
            byte=blob[i>>3];bit=7-(i&7);i+=1
            if byte&(1<<bit):im.putpixel((x,y),1)
    return im

def preview_frame(theme,keys,key=227,icon_color=None):
    """Software preview: real status-bar layout plus a sample key glyph."""
    im=base_frame(theme);d=ImageDraw.Draw(im);font=load(ROOT/'profiles/font.json')['ascii']
    layout=status_layout(theme)
    if icon_color and layout.get('rice') is not None:
        layout['rice']['color']=icon_color
    def put(mask,rx,ry):
        for y in range(mask.height):
            for x in range(mask.width):
                if mask.getpixel((x,y)):d.point((rx+x,ry+y),fill=theme['ink'])
    def text_at(value,x,y,scale):
        for i,c in enumerate(value):
            for yy,row in enumerate(font[c]):
                for xx,cell in enumerate(row):
                    if cell=='1':d.rectangle((x+(i*6+xx)*scale,y+yy*scale,x+(i*6+xx+1)*scale-1,y+(yy+1)*scale-1),fill=theme['ink'])
    for i,(rx,ry,rw,rh) in enumerate(layout['regions']):
        if i==0:continue
        blob=layout['static'].get(i)
        if blob:put(_unpack(blob,rw,rh),rx,ry)
    cfg=layout['cfg']
    if cfg['kind']=='rice':
        rx,ry,rw,rh=layout['regions'][1]
        rice=layout.get('rice') or {}
        icon=tight_icon(left_icon());gap=3
        ink=rice.get('color') or theme['ink']
        for i in range(5):
            for y in range(icon.height):
                for x in range(icon.width):
                    if icon.getpixel((x,y)):d.point((rx+i*(icon.width+gap)+x,ry+y),fill=ink)
    if cfg['kind']=='time':
        rx,ry,rw,rh=layout['regions'][1]
        text_at('12:34:56',rx,ry,2)
    for w in layout['widgets']:
        rx,ry,rw,rh=layout['regions'][w['icon']]
        if w['kind']==0:
            mask=Image.new('1',(rw,rh),0)
            packed=ICONS[0]
            for yy in range(min(rh,13)):
                for xx in range(rw):
                    byte=packed[yy*3+(xx>>3)]
                    if byte&(128>>(xx&7)):mask.putpixel((xx,yy),1)
            put(mask,rx,ry)
        elif w['kind']==1:
            mask=Image.new('1',(rw,rh),0);md=ImageDraw.Draw(mask)
            md.ellipse((0,0,8,8),fill=1)
            for yy,row in enumerate(font['A']):
                for xx,cell in enumerate(row):
                    if cell=='1':mask.putpixel((10+xx,1+yy),1)
            put(mask,rx,ry)
        elif w['kind']==2:
            mask=Image.new('1',(rw,rh),0);md=ImageDraw.Draw(mask)
            md.rectangle((0,0,rw-3,rh-1),outline=1)
            md.rectangle((2,2,rw-6,rh-3),fill=1)
            md.rectangle((rw-2,3,rw-1,rh-4),fill=1)
            put(mask,rx,ry)
            tx,ty,tw,th=layout['regions'][w['text']]
            text_at('84%',tx,ty,1)
        elif w['kind']==3:
            tx,ty,tw,th=layout['regions'][w['text']]
            text_at('246',tx,ty,1)
        elif w['kind']==6:
            tx,ty,tw,th=layout['regions'][w['text']]
            text_at('12345',tx,ty,1)
    gx,gy,gw,gh=layout['regions'][0]
    g=next((g for g in keys['glyphs'] if g['key']==key),None)
    if g:
        x=gx+(gw-len(g['rows'][0])*6)//2;y=gy+(gh-len(g['rows'])*6)//2
        for yy,row in enumerate(g['rows']):
            for xx,cell in enumerate(row):
                if cell=='1':d.rectangle((x+xx*6,y+yy*6,x+xx*6+5,y+yy*6+5),fill=theme['ink'])
    return im

def save_cache_gif(frames,path,duration=120):
 # Keep the previous surface while the native decoder prepares the next frame.
 # Image.save(disposal=1) crops later frames even with optimize=False. Encode
 # each image explicitly so every frame restores the clean background.
 indexed=[frame.quantize(colors=256) for frame in frames]
 header,_=GifImagePlugin.getheader(indexed[0],info={'loop':0})
 with Path(path).open('wb') as output:
  for block in header:output.write(block)
  for i,frame in enumerate(indexed):
   for block in GifImagePlugin.getdata(frame,duration=duration,disposal=1,include_color_table=i>0):output.write(block)
  output.write(b';')

def validate_cache_gif(path,theme):
 bg=rgb565(theme['background'])
 with Image.open(path) as gif:
  if gif.size!=(320,172):raise ValueError('Cache GIF must be 320x172')
  for i in range(gif.n_frames):
   gif.seek(i)
   if not gif.tile or gif.tile[0][1]!=(0,0,320,172):raise ValueError('Cache GIF requires complete frames')
   if gif.disposal_method!=1:raise ValueError('Cache GIF must retain the previous frame (disposal=1)')
   if 'transparency' in gif.info:raise ValueError('Cache GIF frames must be opaque')
   color=gif.convert('RGB').getpixel((10,60))
   if rgb565('#%02x%02x%02x'%color)==bg:raise ValueError('Cache frame marker equals player background')
def generate(keys_path,theme_name,out,header_dir=None):
 keys=validate_keys(load(keys_path));themes=load_themes()
 if theme_name not in themes:raise ValueError('Unknown theme')
 theme=themes[theme_name];out=Path(out);out.mkdir(parents=True,exist_ok=True)
 if header_dir:headers(keys,theme,Path(header_dir))
 cfg=character();duration=int(cfg.get('duration',120)) if cfg else 120
 count=_motion_frames(cfg) if cfg and _motion_frames else 8
 frames=[base_frame(theme,i) for i in range(count)]
 save_cache_gif(frames,out/f'robot-{theme_name}.gif',duration)
 validate_cache_gif(out/f'robot-{theme_name}.gif',theme)
 # Screen-safe fallbacks: 150 ms/frame (the rate the diagnostic page uses to
 # fix UART starvation) and a tiny 24-frame variant for tight external flash.
 # These are uploaded by the wizard when the full animation is refused, so
 # they must exist in every build/snapshot.
 def fallback(path,seq,ms):
  cut=[frames[round(i*(len(frames)-1)/max(1,len(seq)-1))] for i in range(len(seq))] if len(seq)<len(frames) else frames
  save_cache_gif(cut,path,ms)
  validate_cache_gif(path,theme)
 fallback(out/f'robot-{theme_name}-lite.gif',range(min(24,len(frames))),150)
 blank=Image.new('RGB',(320,172),theme['background'])
 # Keep the marker pixel distinct from the background so the cache contract holds.
 ImageDraw.Draw(blank).point((10,60),fill=theme['ink'])
 save_cache_gif([blank],out/f'robot-{theme_name}-blank.gif',400)
 validate_cache_gif(out/f'robot-{theme_name}-blank.gif',theme)
 preview_frame(theme,keys).save(out/f'preview-{theme_name}.png')
 return out/f'robot-{theme_name}.gif'
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--keys',type=Path,default=ROOT/'profiles/keys.json');p.add_argument('--theme',default='pink');p.add_argument('--out',type=Path,default=ROOT/'build/assets');p.add_argument('--headers',type=Path)
 a=p.parse_args();print(generate(a.keys,a.theme,a.out,a.headers))
