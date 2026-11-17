/* SPDX-License-Identifier: MIT */
#include "native_ui.h"
#include "cache_font.h"
#include "ui_assets.h"
#define R(a) (*(volatile u32*)(a))
#define LCD_BUSY R(0x20001c6c)
extern u8 __live_bss_start__,__live_bss_end__;
static struct {
 u8 masks[STATUS_MASK_BYTES];
 u32 pointer,object,time,key_at,caps_at;
 u32 keys[8];
 u16 x,y,w,h,key;
 u8 active,suspended,has_surface,dirty,key_dirty,status_dirty,known,battery,charge,mode,modifiers,caps,key_pos;
} ui;
static u32 clock_ms(void){return ((u32(*)(void))0x0803a2bb)();}
static void zero(u8 *p,unsigned n){while(n--)*p++=0;}
static void ack(unsigned status,u16 seq){
 u8 p[8]={0xbe,0x1a,8,13,(u8)status,(u8)seq,(u8)(seq>>8),0xed};unsigned i,spins;
 for(i=0;i<8;i++){for(spins=0;spins<4096;spins++)if(R(0x40004c00)&0x40u)break;if(spins==4096)return;R(0x40004c04)=p[i];}
}
static void clear(unsigned slot){zero(ui.masks+ui_geo[slot].offset,ui_geo[slot].bytes);}
static void dot(unsigned slot,unsigned x,unsigned y){
 const UiRegion *r=&ui_geo[slot];unsigned bit;
 if(x>=r->w||y>=r->h)return;bit=y*r->w+x;ui.masks[r->offset+(bit>>3)]|=(u8)(128u>>(bit&7));
}
/* cache_font stores 7 rows x 5 bits per glyph, MSB first (5 bytes each). */
static unsigned row5(const u8 *g,unsigned j){
 unsigned off=j*5u,o=off>>3u,shift=16u-(off&7u)-5u,w=(unsigned)g[o]<<8;
 if(o<4u)w|=g[o+1u];
 return (w>>shift)&31u;
}
static void text(unsigned slot,const u8 *s,unsigned n,unsigned scale){
 const UiRegion *r=&ui_geo[slot];unsigned i,j,k,dx,dy,x,y,width;
 while(scale>1&&n&&(n*6u-1u)*scale>r->w)scale--;
 width=n?(n*6u-1u)*scale:0;x=width>r->w?0:(r->w-width)/2;y=r->h>7*scale?(r->h-7*scale)/2:0;clear(slot);
 for(i=0;i<n;i++)for(j=0;j<7;j++)for(k=0;k<5;k++)if(row5(cache_font[glyph_index(s[i])],j)&(16u>>k))
  for(dy=0;dy<scale;dy++)for(dx=0;dx<scale;dx++)dot(slot,x+(i*6+k)*scale+dx,y+j*scale+dy);
}
static void key_mask(void){
 unsigned i,j,x,y,dx,dy,scale,k=ui.key;u8 s[4];const BigGlyph *g;
 if(k>=0xfff8u)k=(k&7u)+224u;
 if(k==231)k=227;
 for(i=0;i<sizeof big_glyphs/sizeof big_glyphs[0];i++)if(big_glyphs[i].key==k){
  g=&big_glyphs[i];clear(0);scale=6;x=(ui_geo[0].w-g->w*scale)/2;y=(ui_geo[0].h-g->h*scale)/2;
  for(j=0;j<g->h;j++)for(i=0;i<g->w;i++)if(g->rows[j]&(1u<<(g->w-1-i)))for(dy=0;dy<scale;dy++)for(dx=0;dx<scale;dx++)dot(0,x+i*scale+dx,y+j*scale+dy);
  return;
 }
 i=k;
 if(!i){text(0,(const u8*)"--",2,6);return;}
 if(i==224||i==228){text(0,(const u8*)"CTRL",4,5);return;}
 if(i==226||i==230){text(0,(const u8*)"ALT",3,5);return;}
 if(i==41){text(0,(const u8*)"ESC",3,5);return;}
 if(i>=4&&i<=29)s[0]=(u8)('A'+i-4);
 else if(i>=30&&i<=39)s[0]=(ui.modifiers&1u)?(u8)"!@#$%^&*()"[i-30]:(u8)(i==39?'0':'1'+i-30);
 else if(i>=45&&i<=56)s[0]=(u8)((ui.modifiers&1u)?"_+{}|~:\"~<>?":"-=[]\\#;'`,./")[i-45];
 else if(i>=401&&i<=405){s[0]='F';s[1]='N';if(i==401)text(0,s,2,6);else{s[2]=(u8)('1'+i-401);text(0,s,3,5);}return;}
 else if((i>=58&&i<=69)||(i>=104&&i<=115)){
  i=i>=104?i-91:i-57;s[0]='F';if(i>=10){s[1]=(u8)('0'+i/10);s[2]=(u8)('0'+i%10);text(0,s,3,5);}else{s[1]=(u8)('0'+i);text(0,s,2,6);}return;
 }else{
  switch(i){case 41:s[0]=140;break;case 43:s[0]=130;break;case 57:s[0]=141;break;case 73:s[0]=143;break;case 76:s[0]=142;break;case 224:case 228:s[0]=132;break;case 225:case 229:s[0]=131;break;case 226:case 230:s[0]=133;break;case 227:case 231:s[0]=139;break;default:s[0]='?';break;}
 }
 text(0,s,1,9);
}
/* Copy a pre-rendered (compile-time) bitmap into one mask slot; slots without
   static data are zeroed so a stale frame never survives. */
static void blit(unsigned slot){
 const u8 *src=status_static_data+status_static_off[slot];u8 *dst=ui.masks+ui_geo[slot].offset;unsigned n=ui_geo[slot].bytes;
 if(status_static_off[slot]==0xffffu){while(n--)*dst++=0;return;}
 while(n--)*dst++=*src++;
}
static void draw_conn(unsigned slot){
 const UiRegion *ir=&ui_geo[slot];unsigned x,y,icon=ui.mode==UI_USB_RAW?0:ui.mode==UI_RF_RAW?1:2;
 if(!ui.known||ui.mode>=5)return;
 for(y=0;y<ir->h;y++){u32 row=connection_icons[icon][y];for(x=0;x<ir->w;x++)if(row&(1u<<(ir->w-1-x)))dot(slot,x,y);}
}
static void draw_caps(unsigned slot){
 unsigned x,y;const u16 *g=case_glyphs[ui.caps?0:1];
 for(y=0;y<9;y++)for(x=0;x<9;x++){
  int dx=(int)x-4,dy=(int)y-4;unsigned d2=(unsigned)(dx*dx+dy*dy);
  if(ui.caps){if(d2<=18u)dot(slot,x,y);}
  else if(d2<=18u&&d2>=9u)dot(slot,x,y);
 }
 for(y=0;y<7;y++)for(x=0;x<5;x++)if(g[y]&(16u>>x))dot(slot,10+x,y+1);
}
static void draw_battery(unsigned icon_slot,unsigned text_slot){
 unsigned x,y,value=ui.known?ui.battery:255,bit;u8 s[4];
 const UiRegion *ir=&ui_geo[icon_slot];
 for(y=0;y<ir->h;y++)for(x=0;x<ir->w;x++){
  bit=(x<20&&(x==0||x==19||y==0||y==9))||(x>=20&&y>=3&&y<8);
  if(x>=2&&x<18&&y>=2&&y<8)bit=value<=100?(x-2)*100u<16u*value:(y>=4&&y<6&&x>=7&&x<13);
  if(bit)dot(icon_slot,x,y);
 }
 if(!text_slot)return;
 if(value>100)text(text_slot,(const u8*)"--",2,1);
 else{unsigned n=0;if(value>=100){s[n++]='1';s[n++]='0';s[n++]='0';}else{if(value>=10)s[n++]=(u8)('0'+value/10);s[n++]=(u8)('0'+value%10);}s[n++]='%';text(text_slot,s,n,1);}
}
/* Keys typed in the last ten seconds, scaled to keys per minute (CPM). */
static void draw_speed(unsigned text_slot){
 u32 now=clock_ms();unsigned j,n=0,v;u8 s[3];
 for(j=0;j<8;j++)if(ui.keys[j]&&(u32)(now-ui.keys[j])<10000u)n++;
 v=n*6u;if(v>999u)v=999u;
 j=0;
 if(v>=100u)s[j++]=(u8)('0'+v/100u);
 if(v>=10u)s[j++]=(u8)('0'+(v/10u)%10u);
 s[j++]=(u8)('0'+v%10u);
 text(text_slot,s,j,1);
}
static void status_build(void){
 unsigned i;
 for(i=1;i<STATUS_REGION_COUNT;i++)blit(i);
 for(i=0;i<sizeof status_right/sizeof status_right[0];i++){
  const StatusWidget *w=&status_right[i];
  if(w->kind==0)draw_conn(w->icon);
  else if(w->kind==1)draw_caps(w->icon);
  else if(w->kind==2)draw_battery(w->icon,w->text);
  else if(w->kind==3&&w->text)draw_speed(w->text);
 }
}
static void refresh(void){
 u32 t;u8 s[8];unsigned i,shift;
 if(ui.key_dirty){key_mask();ui.key_dirty=0;ui.dirty=1;}
 if(ui.status_dirty){status_build();ui.status_dirty=0;ui.time=0xfffffffeu;ui.dirty=1;}
 t=rtc_value();if(STATUS_LEFT_KIND==0&&t!=ui.time){
  ui.time=t;
  if(t==0xffffffffu)text(1,(const u8*)"--:--:--",8,2);
  else{for(i=0;i<8;i++){if(i==2||i==5)s[i]=':';else{shift=i<2?20-i*4:i<5?24-i*4:28-i*4;s[i]=(u8)('0'+((t>>shift)&15u));}}text(1,s,8,2);}
  ui.dirty=1;
 }
}
static u32 current_object(void){u32 o=R(0x2003ede8);return o>=0x20000000u&&o<=0x2005f000u-0x65cu?o:0;}
static int surface_matches(void){return ui.has_surface&&ui.object==current_object()&&R(ui.object+0x658)==ui.pointer&&*(volatile u16*)0x2003edba==ui.w&&*(volatile u16*)0x2003edbc==ui.h&&*(volatile u16*)0x2003edbe==ui.x&&*(volatile u16*)0x2003edc0==ui.y;}
void rainy_hook_cached_draw(u16 x,u16 y,u16 w,u16 h,const u8 *p){
 u32 address=(u32)p,size=(u32)w*h*2;unsigned i,x0,y0,x1,y1,px,py,bit,at,color;const UiRegion *r;
 if(!ui.suspended&&w&&h&&w<=320&&h<=172&&x+w<=320&&y+h<=172&&address>=0x20000000u&&address<=0x2005f000u-size&&current_object()){
  if(LCD_BUSY)return;
  if(!ui.active){ui.active=1;ui.key_dirty=ui.status_dirty=1;ui.time=0xfffffffeu;}
  refresh();
  for(i=0;i<STATUS_REGION_COUNT;i++){
   r=&ui_geo[i];x0=x>r->x?x:r->x;y0=y>r->y?y:r->y;x1=x+w<r->x+r->w?x+w:r->x+r->w;y1=y+h<r->y+r->h?y+h:r->y+r->h;
   for(py=y0;py<y1;py++)for(px=x0;px<x1;px++){
    bit=(py-r->y)*r->w+px-r->x;color=ui.masks[r->offset+(bit>>3)]&(128u>>(bit&7))?UI_INK:(i?UI_BG:UI_PANEL);
    at=((py-y)*w+px-x)*2;((u8*)p)[at]=(u8)color;((u8*)p)[at+1]=(u8)(color>>8);
   }
  }
  ui.pointer=address;ui.object=current_object();ui.x=x;ui.y=y;ui.w=w;ui.h=h;
  ui.has_surface=R(ui.object+0x658)==address;ui.dirty=0;
 }
 ((void(*)(u16,u16,u16,u16,const u8*))0x0805d6f3)(x,y,w,h,p);
}
int rainy_hook_start(void){volatile u8 *p=&__live_bss_start__;while(p<&__live_bss_end__)*p++=0;return ((int(*)(void))0x0807a601)();}
void rainy_hook_gui(void){if(!ui.active)((void(*)(void))0x0802dca9)();}
void rainy_hook_misc(void){if(!ui.active)((void(*)(void))0x0805b031)();}
void rainy_hook_image(void){
 u32 now=clock_ms();if(!ui.suspended)rtc_tick(now);
 if(UI_IDLE_MS&&ui.key&&(u32)(now-ui.key_at)>=UI_IDLE_MS){ui.key=0;ui.key_dirty=1;}
 if(!ui.active){((void(*)(void))0x0805b245)();return;}
 refresh();
 if(!LCD_BUSY){((void(*)(void))0x0805b245)();if(!LCD_BUSY&&ui.dirty&&surface_matches())rainy_hook_cached_draw(ui.x,ui.y,ui.w,ui.h,(const u8*)ui.pointer);}
}
void rainy_hook_native_key(int key,unsigned raw5,unsigned raw6){
 ui.modifiers=(u8)raw6;
 if((u16)key){ui.keys[ui.key_pos&7u]=clock_ms();ui.key_pos=(u8)((ui.key_pos+1u)&7u);if(ui.status_dirty==0)ui.status_dirty=1;}
 if((u16)key==57&&(u32)(clock_ms()-ui.caps_at)>40u){ui.caps^=1u;ui.caps_at=clock_ms();ui.status_dirty=1;}
 if((u16)key){ui.key=(u16)key;ui.key_at=clock_ms();ui.key_dirty=1;}
 ((void(*)(int,unsigned,unsigned))0x0805ac73)(key,raw5,raw6);
}
void rainy_hook_native_status(unsigned battery,unsigned charge,unsigned mode){
 ui.battery=battery>100?100:(u8)battery;ui.charge=(u8)charge;ui.mode=(u8)mode;ui.known=1;ui.status_dirty=1;
 ((void(*)(unsigned,unsigned,unsigned))0x0805ae0b)(battery,charge,mode);
}
static int valid(const u8 *p,u16 n){unsigned i,sum=0;if(n<11||n>241||p[0]!=0xbe||p[1]!=0x1a||p[2]!=n||p[7]||p[n-1]!=0xed)return 0;for(i=3;i<(unsigned)n-3;i++)sum+=p[i];return (sum&65535u)==(unsigned)(p[n-3]|(p[n-2]<<8));}
void rainy_hook_ips(const u8 *p,u16 n){
 u16 seq;unsigned op,v;
 if(!p||n<4)return;
 if(rtc_receive(p,n,clock_ms()))return;
 if(p[3]!=13){if(ui.active&&p[3]!=10&&p[3]!=11){ack(FORMAT,0);return;}((void(*)(const u8*,u16))0x080596ad)(p,n);return;}
 if(!valid(p,n)){ack(FORMAT,0);return;}seq=(u16)(p[5]|(p[6]<<8));op=p[4];
 if(op==0&&n==11){ack(0xa5,0x364c);return;}
 if((op==2||op==5)&&n==11){if(LCD_BUSY){ack(BUSY,seq);return;}ui.suspended=op==2;ui.active=0;ui.has_surface=0;ack(DONE,seq);return;}
 if(op==12&&n==18){ack(rtc_schedule(p+8,seq,clock_ms()),seq);return;}
 if(op==11&&n==11){
  switch(seq){case 0:v=0x5536;break;case 1:v=ui.key;break;case 2:v=ui.known?(ui.battery|(ui.charge<<8)):0xffff;break;case 3:v=ui.known?ui.mode:0xffff;break;case 4:v=rtc_state();break;case 5:v=rtc_value()&65535u;break;case 6:v=rtc_value()>>16;break;case 7:v=ui.active;break;case 8:v=ui.modifiers;break;case 14:v=*(volatile u16*)0x1ffff7e0u;break;case 15:v=*(volatile u8*)0x1ffff7f3u;break;case 16:v=ui.caps;break;case 17:v=0x1303;break; /* UI build tag: 1.3.3 */default:ack(RANGE,seq);return;}
  ack(0xb0+seq,(u16)v);return;
 }
 ack(FORMAT,seq);
}
