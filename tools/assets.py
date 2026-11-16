"""Generate editable UI headers and original robot GIFs. SPDX-License-Identifier: MIT."""
import argparse,json,os
from pathlib import Path
from PIL import Image,ImageDraw,GifImagePlugin

ROOT=Path(__file__).resolve().parents[1]
# Studio mode is opt-in via env var. With it off, generation stays byte-identical
# to the shipped assets/ GIFs so the repository's own contract tests keep passing.
STUDIO=os.environ.get('RAINY75_STUDIO')=='1'
BASE_REGIONS=[(40,57,120,76),(16,13,94,14),(233,12,16,16),(264,17,20,8),(287,17,23,7),(214,14,13,9)]
# Studio layout centres the big-key region inside the taller, RAINY-free card.
# Only the y coordinate moves; all mask sizes (and the mask total) stay put.
# Region 5 is the caps-lock lamp+letter in the top bar, left of the connection
# icon: filled disc + 'A' = caps on, hollow ring + 'a' = caps off.
STUDIO_REGIONS=[(40,62,120,76),*BASE_REGIONS[1:]]
REGIONS=BASE_REGIONS
def regions():return STUDIO_REGIONS if STUDIO else BASE_REGIONS
# Connection icons, 16x16 1-bit rows, drawn at (233,12) by native_ui.c.
# Index order is firmware-defined: 0=USB wired, 1=2.4G wireless, 2=Bluetooth.
# Pictograms instead of letter abbreviations. Wired is a USB-A plug standing on
# its cable (hollow shell + two pins on top), so it cannot be confused with the
# battery bar drawn right next to it; 2.4G spells "2.4G" in 4x6 glyphs that span
# the full 16 px (a bare "2.4" left users unsure whether it meant 2.4 GHz);
# Bluetooth is the rune.
# Region, array shape and mask allocation are unchanged.
MASK_TOTAL=1393
ICONS=[
 [0,1632,1632,4080,2064,2064,2064,2064,2064,2064,4080,384,384,384,384,384],
 [0,0,0,0,0,24679,37032,4392,8683,16425,62503,0,0,0,0,0],
 [256,384,320,4384,2320,1312,832,384,384,832,1312,2320,4384,320,384,256],
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
def headers(keys,theme,out):
 out.mkdir(parents=True,exist_ok=True);font=load(ROOT/'profiles/font.json')
 chars=[chr(c) for c in range(32,97)]+list('{|}~')
 grids=[font['ascii'][c] for c in chars]+[g['rows'] for g in font['icons']]
 rows=['/* SPDX-License-Identifier: MIT; generated editable pixel cells. */','static const unsigned char cache_font[][7]={']
 rows+=[' {'+','.join(str(int(r,2)) for r in glyph)+'},' for glyph in grids]
 rows+=['};','static unsigned glyph_index(unsigned c){if(c>=97&&c<=122)c-=32;if(c>=128&&c<144)return 69+c-128;if(c>=32&&c<=126)return c-32-(c>=123?26:0);return 31;}']
 (out/'cache_font.h').write_text('\n'.join(rows)+'\n',encoding='utf8')
 rows=['/* SPDX-License-Identifier: MIT; generated from profiles. */','#define UI_IDLE_MS 0u','#define UI_USB_RAW 1','#define UI_RF_RAW 0','typedef struct {u16 x,y,fg,bg,offset,bytes;u8 w,h;} UiRegion;','static const UiRegion ui_geo[]={']
 offset=0
 for i,(x,y,w,h) in enumerate(regions()):
  size=(w*h+7)//8;bg=theme['panel'] if i==0 else theme['background']
  rows.append(' {'+','.join(map(str,[x,y,rgb565(theme['ink']),rgb565(bg),offset,size,w,h]))+'},');offset+=size
 rows+=['};','typedef struct {u16 key;u8 w,h;u16 rows[11];} BigGlyph;','static const BigGlyph big_glyphs[]={']
 for g in keys['glyphs']:
  rows.append(' {'+','.join(map(str,[g['key'],len(g['rows'][0]),len(g['rows'])]))+',{'+','.join(str(int(r,2)) for r in g['rows'])+'}},')
 rows+=['};','static const u16 connection_icons[3][16]={']+[' {'+','.join(map(str,r))+'},' for r in ICONS]+['};']
 case_a=[font['ascii']['A'],LOWER_A]
 rows+=['static const u16 case_glyphs[2][7]={']+[' {'+','.join(str(int(r,2)) for r in g)+'},' for g in case_a]+['};']
 if offset!=MASK_TOTAL:raise ValueError('Unexpected mask allocation')
 (out/'ui_assets.h').write_text('\n'.join(rows)+'\n',encoding='utf8')
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
def preview_frame(theme,keys,key=227):
 im=base_frame(theme);d=ImageDraw.Draw(im);font=load(ROOT/'profiles/font.json')['ascii']
 def text(value,x,y,scale):
  for i,c in enumerate(value):
   for yy,row in enumerate(font[c]):
    for xx,cell in enumerate(row):
     if cell=='1':d.rectangle((x+(i*6+xx)*scale,y+yy*scale,x+(i*6+xx+1)*scale-1,y+(yy+1)*scale-1),fill=theme['ink'])
 text('12:34:56',16,13,2);text('84%',287,17,1)
 d.rectangle((264,17,280,24),outline=theme['ink']);d.rectangle((267,20,276,22),fill=theme['ink']);d.rectangle((281,19,282,22),fill=theme['ink'])
 for yy,row in enumerate(ICONS[0]):
  for xx in range(16):
   if row&(1<<(15-xx)):d.point((233+xx,12+yy),fill=theme['ink'])
 cx,cy=regions()[5][0],regions()[5][1]
 for yy in range(7):
  for xx in range(7):
   if (xx-3)**2+(yy-3)**2<=10:d.point((cx+xx,cy+2+yy),fill=theme['ink'])
 for yy,row in enumerate(font['A']):
  for xx,cell in enumerate(row):
   if cell=='1':d.point((cx+8+xx,cy+2+yy),fill=theme['ink'])
 gx,gy,gw,gh=regions()[0]
 g=next(g for g in keys['glyphs'] if g['key']==key);x=gx+(gw-len(g['rows'][0])*6)//2;y=gy+(gh-len(g['rows'])*6)//2
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
