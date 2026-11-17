"""Generate editable UI headers and original robot GIFs. SPDX-License-Identifier: MIT."""
import argparse,json,os
from pathlib import Path
from PIL import Image,ImageDraw,GifImagePlugin

ROOT=Path(__file__).resolve().parents[1]
# Studio mode is opt-in via env var. With it off, generation stays byte-identical
# to the shipped assets/ GIFs so the repository's own contract tests keep passing.
STUDIO=os.environ.get('RAINY75_STUDIO')=='1'
BASE_REGIONS=[(40,57,120,76),(16,13,94,14),(225,10,24,20),(257,15,22,10),(287,17,23,7),(202,15,15,9)]
# Studio layout centres the big-key region inside the taller, RAINY-free card.
# Only the y coordinate moves; all mask sizes (and the mask total) stay put.
# Region 5 is the caps-lock lamp+letter in the top bar, left of the connection
# icon: filled disc + 'A' = caps on, hollow ring + 'a' = caps off.
STUDIO_REGIONS=[(40,62,120,76),*BASE_REGIONS[1:]]
REGIONS=BASE_REGIONS
def regions():return STUDIO_REGIONS if STUDIO else BASE_REGIONS
# Connection icons, 24x20 1-bit rows, drawn at ui_geo[2] (225,10) by native_ui.c.
# Index order is firmware-defined: 0=USB wired, 1=2.4G wireless, 2=Bluetooth.
# Pictograms instead of letter abbreviations, drawn 1.5x larger than the first
# 16x16 set so they read at arm's length: the USB-A plug stands on its cable
# (hollow shell + two pins), 2.4G spells the full "2.4G" in the 5x7 pixel font
# (a bare "2.4" left users unsure whether it meant 2.4 GHz), Bluetooth is the
# rune. The status bar right side is a single right-aligned group:
# caps lamp | connection icon | battery | percentage.
MASK_TOTAL=1431
ICONS=[
 [13824,13824,13824,131008,131008,98496,98496,98496,98496,98496,98496,131008,131008,7168,7168,7168,7168,7168,7168,7168],
 [0,0,0,0,0,0,7340318,8913696,525600,1050926,2101154,4227362,16285982,0,0,0,0,0,0,0],
 [0,4096,6144,6144,5120,135936,69760,69760,54016,13312,6144,6144,13312,13312,54016,69760,135936,5120,5120,6144],
]
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
    'conn':     (24, 19, 0, 0, 0),
    'caps':     (15, 9, 0, 0, 1),
    'battery':  (22, 10, 23, 7, 2),
    'speed':    (15, 15, 23, 7, 3),
    'rate':     (16, 14, 35, 7, 4),
    'debounce': (17, 14, 29, 7, 5),
}
STATUS_UNITS = {'rate': 'Hz', 'debounce': 'ms'}
STATUS_RIGHT_MAX = 3
STATUS_GAP = 9
STATUS_RIGHT_EDGE = 310
CJK_FONTS = ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf',
             'C:/Windows/Fonts/simsun.ttc', 'C:/Windows/Fonts/Deng.ttf',
             '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')


def status_config():
    """Read and sanitise profiles/statusbar.json."""
    cfg = load(STATUSBAR_FILE) if STATUSBAR_FILE.exists() else {}
    left = cfg.get('left') or {}
    kind = left.get('type', 'time')
    if kind not in ('time', 'text'):
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


def _sym_rate():
    """Two lowercase n's sharing a baseline that runs past both sides."""
    def paint(d):
        for ox in (1, 6, 9, 14):
            d.rectangle((ox, 3, ox + 1, 12), fill=1)
        d.rectangle((1, 3, 7, 4), fill=1)
        d.rectangle((9, 3, 15, 4), fill=1)
        d.rectangle((0, 12, 15, 12), fill=1)
    return _symbol((16, 14), paint)


def _sym_debounce():
    """Symmetric heartbeat: flat baseline, one solid peak."""
    def paint(d):
        d.line([(0, 10), (5, 10)], fill=1, width=2)
        d.polygon([(5, 10), (8, 2), (11, 10)], fill=1)
        d.line([(11, 10), (17, 10)], fill=1, width=2)
    return _symbol((18, 14), paint)


def _sym_speed():
    """Speedometer: ring with tick marks, needle to the upper right."""
    def paint(d):
        d.ellipse((1, 1, 14, 14), outline=1)
        for tx, ty in ((8, 3), (12, 6), (10, 11)):
            d.point((tx, ty), fill=1)
        d.line((7, 7, 11, 4), fill=1, width=2)
        d.rectangle((6, 6, 8, 8), fill=1)
    return _symbol((15, 15), paint)


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
    regions = [(40, 57, 120, 76)] if not STUDIO else [(40, 62, 120, 76)]
    static = {}
    widgets = []
    # ---- left slot (region 1) ----
    if cfg['kind'] == 'time':
        regions.append((16, 13, 94, 14))
    elif cfg['kind'] == 'text':
        width = max(16, len(cfg['text']) * 18 - 2)
        res = (16, 11, width, 16)
        regions.append(res)
        im = Image.new('1', (width, 16), 0)
        pos = 0
        for ch in cfg['text']:
            glyph = cjk_glyph(ch, 16)
            for y, row in enumerate(glyph):
                for x, cell in enumerate(row):
                    if cell == '1' and pos + x < width:
                        im.putpixel((pos + x, y), 1)
            pos += 18
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
                      'total': iw + (3 + tw if tw else 0)})
    x = STATUS_RIGHT_EDGE
    for spec in reversed(specs):
        x -= spec['total']
        spec['x'] = x
        x -= STATUS_GAP
    for spec in specs:
        iy = 20 - spec['ih'] // 2
        icon_slot = len(regions)
        regions.append((spec['x'], iy, spec['iw'], spec['ih']))
        text_slot = 0
        if spec['tw']:
            ty = 20 - spec['th'] // 2
            text_slot = len(regions)
            regions.append((spec['x'] + spec['iw'] + 3, ty, spec['tw'], spec['th']))
        widgets.append({'kind': spec['kind'], 'icon': icon_slot, 'text': text_slot})
        if spec['kind'] == 3:                      # typing speed: static icon only
            icon = _sym_speed()
            im = Image.new('1', (spec['iw'], spec['ih']), 0)
            im.paste(icon, ((spec['iw'] - icon.width) // 2, (spec['ih'] - icon.height) // 2))
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
            'static': static, 'total': total}

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
        '#define STATUS_LEFT_KIND '+str(0 if layout['cfg']['kind']=='time' else 1)+'u',
        'typedef struct {u8 kind,icon,text;} StatusWidget;','static const StatusWidget status_right[]={']
 for w in layout['widgets']:
  rows.append(' {'+','.join(map(str,[w['kind'],w['icon'],w['text']]))+'},')
 if not layout['widgets']:
  rows.append(' {0,1,0},')
 rows+=['};']
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
 # 24x19 pictograms, packed as three bytes per row (saves ~57 B over u32 rows).
 packed_icons=[]
 for icon in ICONS:
  blob=[]
  for row in icon[:19]:
   blob += [(row>>16)&255,(row>>8)&255,row&255]
  packed_icons.append(blob)
 rows+=['};','static const u8 connection_icons[3][57]={']+[' {'+','.join(map(str,r))+'},' for r in packed_icons]+['};']
 case_a=[font['ascii']['A'],LOWER_A]
 rows+=['static const u16 case_glyphs[2][7]={']+[' {'+','.join(str(int(r,2)) for r in g)+'},' for g in case_a]+['};']
 (out/'ui_assets.h').write_text('\n'.join(rows)+'\n',encoding='utf8')
 return layout
def base_frame(theme,phase=0):
 im=Image.new('RGB',(320,172),theme['background']);d=ImageDraw.Draw(im)
 if STUDIO:
  # Cleaner grid: 4px frame inset, 12px side margins, key card vertically centred.
  d.rounded_rectangle((8,36,312,164),radius=16,fill=theme['shell'])
  d.rounded_rectangle((12,40,308,160),radius=12,fill=theme['background'])
  d.rounded_rectangle((24,48,176,152),radius=12,fill=theme['ink'])
  d.rounded_rectangle((27,51,173,149),radius=9,fill=theme['panel'])
 else:
  d.rounded_rectangle((7,37,312,165),radius=16,fill=theme['shell'])
  d.rounded_rectangle((12,42,307,160),radius=13,fill=theme['background'])
  d.rounded_rectangle((24,45,176,145),radius=13,fill=theme['ink'])
  d.rounded_rectangle((27,48,173,142),radius=10,fill=theme['panel'])
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

def preview_frame(theme,keys,key=227):
    """Software preview: real status-bar layout plus a sample key glyph."""
    im=base_frame(theme);d=ImageDraw.Draw(im);font=load(ROOT/'profiles/font.json')['ascii']
    layout=status_layout(theme)
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
    if cfg['kind']=='time':
        rx,ry,rw,rh=layout['regions'][1]
        text_at('12:34:56',rx,ry,2)
    for w in layout['widgets']:
        rx,ry,rw,rh=layout['regions'][w['icon']]
        if w['kind']==0:
            mask=Image.new('1',(rw,rh),0)
            for yy,row in enumerate(ICONS[0][:rh]):
                for xx in range(rw):
                    if row&(1<<(rw-1-xx)):mask.putpixel((xx,yy),1)
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
   color=gif.convert('RGB').getpixel((22,39))
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
 preview_frame(theme,keys).save(out/f'preview-{theme_name}.png')
 return out/f'robot-{theme_name}.gif'
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--keys',type=Path,default=ROOT/'profiles/keys.json');p.add_argument('--theme',default='pink');p.add_argument('--out',type=Path,default=ROOT/'build/assets');p.add_argument('--headers',type=Path)
 a=p.parse_args();print(generate(a.keys,a.theme,a.out,a.headers))
