// SPDX-License-Identifier: MIT
// Rainy75 Windows suite UI: device, display layout, timers, telemetry, tool links.
const $=id=>document.getElementById(id);
const fmt=s=>String(Math.floor(s/60)).padStart(2,'0')+':'+String(Math.max(0,s)%60).padStart(2,'0');
const OPTIONS=[
 {group:'本机状态（现有固件已支持）',items:[
  ['clock','时钟'],['battery','电量'],['mode','连接模式'],['bigKey','大按键图标'],['character','角色动画']]},
 {group:'工具（需屏幕固件新增显示区）',items:[
  ['countdown','倒计时',true],['pomodoro','番茄钟',true]]},
 {group:'PC 增强（USB 有线 + 需屏幕固件）',items:[
  ['cpuTemp','CPU 温度',true],['netSpeed','网速',true],['weather','天气',true]]},
];
const TOOLS=[
 ['wizard','刷机向导','按顺序烧录主控 / 屏幕固件并校时'],
 ['studio','角色与主题定制台','上传 GIF、调主题色、自动配色、等比适配'],
 ['workbench','原版工作台','像素图标编辑、设备状态、校时与素材上传'],
 ['diagnose','时间诊断','只读排查时间不显示，一键校时 / 降低动画负载'],
];
let S=null,pendingDisplay=null,pendingLayout='balanced',netHistory=[],localRemaining=0;

async function api(path,opts){
 const r=await fetch(path,opts);
 return {status:r.status,data:await r.json()};
}
function post(path,obj){return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});}
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function dl(host,rows){host.replaceChildren();for(const [k,v] of rows){host.append(el('dt','',k),el('dd','',String(v)));}}
function rr(c,x,y,w,h,r,fill){c.beginPath();c.roundRect(x,y,w,h,r);c.fillStyle=fill;c.fill();}

async function load(){
 const r=await api('/api/status');
 if(!r.data.ok)return;
 S=r.data;
 pendingDisplay={...S.config.display};
 pendingLayout=S.config.layout||'balanced';
 localRemaining=S.timer.remaining;
 renderTop();renderOverview();renderLayout();renderTimerStatic();renderMonitor();renderTools();drawPreview();
}

function renderTop(){
 const d=S.device,p=$('device-pill'),m=$('mode-pill');
 p.textContent=d.connected?`已连接 · ${d.label} (${d.pids.join(', ')})`:'未检测到键盘';
 p.classList.toggle('bad',!d.connected);
 m.textContent=S.modeLabel;m.classList.toggle('accent',S.mode==='pc');m.classList.toggle('bad',S.mode==='iap');
 $('auto-mode').checked=Boolean(S.config.autoMode);
}
function renderOverview(){
 const d=S.device;
 dl($('device-info'),[['连接状态',d.connected?'在线':'离线'],['设备标识',d.pids.length?d.pids.join(' / '):'—'],
  ['当前模式',d.label],['自动切换',S.config.autoMode?'开启':'关闭']]);
 dl($('firmware-info'),[['主题',S.theme.name+' ('+S.theme.id+')'],['屏幕协议','L6 / 基础版'],
  ['本机服务','8765 工作台 · 8766 定制台 · 8770 套件']]);
 $('mode-desc').textContent=S.mode==='pc'
  ?'键盘通过 USB 正常模式连接，已自动进入 PC 增强模式：系统监控数据可在此采集与预览，倒计时/番茄钟由本机计时管理。'
  :S.mode==='iap'
   ?'键盘处于升级模式，请先到刷机向导完成烧录；此模式下不采集系统数据。'
   :'键盘未通过 USB 正常模式连接（或未插入），屏幕按独立模式工作：时钟、电量、按键与动画都由键盘本地驱动，不依赖电脑。';
 const q=$('quick-links');q.replaceChildren();
 for(const [key,name,desc] of TOOLS){
  const a=el('a');a.href=S.links[key];a.target='_blank';a.rel='noopener';
  a.append(document.createTextNode(name),el('small','',desc));q.append(a);
 }
}

function renderLayout(){
 const host=$('display-options');host.replaceChildren();
 for(const g of OPTIONS){
  const box=el('div','opt-group');box.append(el('strong','',g.group));
  for(const [key,label,needs] of g.items){
   const l=el('label','opt');const cb=el('input');cb.type='checkbox';cb.checked=Boolean(pendingDisplay[key]);
   cb.onchange=()=>{pendingDisplay[key]=cb.checked;drawPreview();};
   l.append(cb,document.createTextNode(label));
   if(needs)l.append(el('span','tag','需固件'));
   box.append(l);
  }
  host.append(box);
 }
 for(const b of $('layout-presets').querySelectorAll('button'))b.classList.toggle('active',b.dataset.layout===pendingLayout);
}
function layoutNote(){
 const extra=OPTIONS.slice(1).flatMap(g=>g.items.filter(([k])=>pendingDisplay[k]).map(([k,l])=>l));
 const count=extra.length;
 $('layout-note').textContent=count
  ?`已选 ${count} 项增强内容：${extra.join('、')}。虚线框表示需要屏幕固件支持，当前仅为排版预览。`
  :'当前只显示现有固件已支持的项目；勾选上方增强项可预览未来布局。';
}
function drawPreview(){
 const c=$('preview').getContext('2d');c.setTransform(2,0,0,2,0,0);
 const t=S.theme,d=pendingDisplay;
 c.fillStyle=t.background;c.fillRect(0,0,320,172);
 rr(c,8,36,304,128,16,t.shell);rr(c,12,40,296,120,12,t.background);
 c.font='500 10px sans-serif';c.fillStyle=t.ink;
 if(d.clock)c.fillText('12:34',16,26);
 if(d.mode)c.fillText('USB',240,26);
 if(d.battery)c.fillText('84%',274,26);
 if(d.bigKey){rr(c,24,48,152,104,12,t.ink);rr(c,27,51,146,98,9,t.panel);}
 if(d.character){
  rr(c,188,46,112,58,9,t.panel);
  c.fillStyle=t.accent;c.beginPath();c.ellipse(244,84,24,19,0,0,Math.PI*2);c.fill();
  c.fillStyle=t.ink;c.fillRect(238,66,12,4);
 }
 const extras=OPTIONS.slice(1).flatMap(g=>g.items.filter(([k])=>d[k]));
 const label=k=>({countdown:'05:00',pomodoro:'专注 25:00',cpuTemp:'CPU 48°C',netSpeed:'↓ 1.2 MB/s',weather:'晴 22°C'})[k]||k;
 const place=pendingLayout==='compact'
  ? extras.map((e,i)=>({e,x:150+i*32,y:30,w:30,h:11}))
  : pendingLayout==='columns'
   ? extras.map((e,i)=>({e,x:30,y:100+Math.floor(i/2)*18,w:66+(i%2)*68,h:14}))
   : extras.map((e,i)=>({e,x:190,y:108+i*11,w:108,h:10}));
 for(const p of place){
  c.setLineDash([2,2]);c.strokeStyle=t.accent;c.lineWidth=.7;
  c.beginPath();c.roundRect(p.x,p.y,p.w,p.h,3);c.stroke();c.setLineDash([]);
  c.fillStyle=t.ink;c.font='9px sans-serif';
  c.fillText(label(p.e[0]),p.x+3,p.y+p.h-2,p.w-5);
 }
 layoutNote();
}

function renderTimerStatic(){
 const t=S.config.timer;
 $('countdown-sec').value=t.countdownSec;$('work-min').value=t.workMin;
 $('break-min').value=t.breakMin;$('rounds').value=t.rounds;
 for(const b of $('timer-mode').querySelectorAll('button'))b.classList.toggle('active',b.dataset.mode===t.mode);
 renderTimer();
}
function renderTimer(){
 const t=S.timer;
 $('timer-display').textContent=fmt(localRemaining);
 $('timer-phase').textContent=t.running
  ?`${t.phase==='work'?'专注中':'休息中'} · 第 ${t.round} 轮`
  :t.finished?'已完成':`${t.phase==='work'?'专注':'休息'} · 第 ${t.round} 轮（已暂停）`;
 $('timer-start').disabled=t.running;$('timer-pause').disabled=!t.running;
}
function renderMonitor(){
 const m=S.monitor||{},host=$('monitor-cards');host.replaceChildren();
 const card=(title,big,sub,ok,bars)=>{
  const c=el('div','card mon-card'+(ok?'':' unavailable'));c.append(el('h2','',title),el('div','big',big),el('div','sub',sub));
  if(bars){const b=el('div','bars');for(const v of bars){const i=el('i');i.style.height=Math.max(2,Math.min(46,v))+'px';b.append(i);}c.append(b);}
  host.append(c);
 };
 const cpu=m.cpuTemp&&m.cpuTemp.available?m.cpuTemp:(m.cpuUsage||{available:false});
 card('CPU',cpu.available?`${cpu.value}${cpu.unit}`:'暂不可用',
   cpu.available?cpu.label:(cpu.reason||'无数据'),Boolean(cpu.available));
 const net=m.net||{available:false};
 if(net.available)netHistory.push(net.down);
 if(netHistory.length>14)netHistory.shift();
 const peak=Math.max(1,...netHistory);
 card('网速',net.available?`↓ ${net.down} ${net.unit}`:'暂不可用',
   net.available?`↑ ${net.up} ${net.unit} · 下行趋势`:(net.reason||'无数据'),Boolean(net.available),
   netHistory.map(v=>v/peak*46));
 const w=m.weather||{available:false};
 card('天气',w.available?`${w.temp}°C`:'暂不可用',
   w.available?`${w.desc} · 湿度 ${w.humidity}% · ${S.config.monitor.city}`:(w.reason||'无数据'),Boolean(w.available));
 $('interval').value=S.config.monitor.intervalSec;
 const sel=$('city');sel.replaceChildren();
 for(const name of Object.keys(S.cities)){const o=el('option','',name);o.value=name;if(name===S.config.monitor.city)o.selected=true;sel.append(o);}
 $('monitor-at').textContent='最近采集 '+(m.at||'—');
}
function renderTools(){
 const host=$('tool-cards');host.replaceChildren();
 for(const [key,name,desc] of TOOLS){
  const c=el('div','card tool-card');c.append(el('h2','',name),el('p','muted',desc),el('code','',S.links[key]));
  const a=el('a','','打开 →');a.href=S.links[key];a.target='_blank';a.rel='noopener';c.append(a);host.append(c);
 }
}

for(const b of document.querySelectorAll('.nav button'))b.onclick=()=>{
 for(const x of document.querySelectorAll('.nav button'))x.classList.toggle('active',x===b);
 for(const v of document.querySelectorAll('.view'))v.classList.toggle('hidden',v.id!=='view-'+b.dataset.view);
 if(b.dataset.view==='layout')drawPreview();
};
for(const b of $('layout-presets').querySelectorAll('button'))b.onclick=()=>{
 pendingLayout=b.dataset.layout;renderLayout();drawPreview();
};
$('save-layout').onclick=async()=>{
 const r=await post('/api/config',{display:pendingDisplay,layout:pendingLayout});
 $('save-layout').textContent=r.data.ok?'已保存 ✓':'保存失败';setTimeout(()=>$('save-layout').textContent='保存显示配置',1400);
 if(r.data.ok)S.config.display={...pendingDisplay};
};
for(const b of $('timer-mode').querySelectorAll('button'))b.onclick=()=>{
 for(const x of $('timer-mode').querySelectorAll('button'))x.classList.toggle('active',x===b);
 post('/api/config',{timer:{mode:b.dataset.mode}}).then(()=>post('/api/timer',{action:'reset'})).then(load);
};
$('save-timer').onclick=async()=>{
 const t={countdownSec:+$('countdown-sec').value,workMin:+$('work-min').value,
  breakMin:+$('break-min').value,rounds:+$('rounds').value};
 const r=await post('/api/config',{timer:t});
 $('save-timer').textContent=r.data.ok?'已保存 ✓':'保存失败';setTimeout(()=>$('save-timer').textContent='保存设置',1400);
};
for(const [id,action] of [['timer-start','start'],['timer-pause','pause'],['timer-skip','skip'],['timer-reset','reset']]){
 $(id).onclick=async()=>{const r=await post('/api/timer',{action});S.timer=r.data.timer;localRemaining=r.data.timer.remaining;renderTimer();};
}
$('save-monitor').onclick=async()=>{
 const m={intervalSec:+$('interval').value,city:$('city').value};
 const r=await post('/api/config',{monitor:m});
 $('save-monitor').textContent=r.data.ok?'已保存 ✓':'保存失败';setTimeout(()=>$('save-monitor').textContent='保存设置',1400);
 if(r.data.ok)await load();
};
$('refresh-monitor').onclick=async()=>{await api('/api/refresh');await load();};
$('refresh').onclick=load;
$('auto-mode').onchange=async()=>{
 const r=await post('/api/config',{autoMode:$('auto-mode').checked});
 if(r.data.ok)await load();
};

setInterval(()=>{if(!S)return;if(S.timer.running&&localRemaining>0)localRemaining--;renderTimer();},1000);
setInterval(async()=>{if(!S)return;const r=await api('/api/status');if(!r.data.ok)return;
 const was=S.timer.running;S=r.data;if(!was||localRemaining<=0)localRemaining=S.timer.remaining;
 renderTop();renderOverview();renderTimerStatic();renderMonitor();drawPreview();},8000);
await load();
