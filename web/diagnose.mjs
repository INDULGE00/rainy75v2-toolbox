// SPDX-License-Identifier: MIT
// Read-only clock diagnostics plus two explicit, user-triggered repairs.
import {AppClient} from './hid.mjs';
import {decodeTime,screenSafeGif} from './protocol.mjs';

const $=id=>document.getElementById(id);
const hex=v=>'0x'+(v>>>0).toString(16).toUpperCase().padStart(4,'0');
let client=null,lastReport=null,logged=false;
function log(msg,kind='info'){
 const el=$('report'),line=`[${new Date().toLocaleTimeString('zh-CN',{hour12:false})}] ${kind==='err'?'X ':kind==='ok'?'OK ':'   '}${msg}`;
 el.textContent=(logged?el.textContent+'\n':'')+line;logged=true;el.scrollTop=el.scrollHeight;
}
async function read(c,label,fn){
 try{const v=await fn();log(`${label}: ${typeof v==='number'?hex(v)+' ('+v+')':String(v)}`);return v;}
 catch(e){log(`${label}: 读取失败 — ${e.message}`,'err');return null;}
}
function verdict(text,bad){const v=$('verdict');v.textContent=text;v.classList.toggle('bad',Boolean(bad));}

const slowGif=screenSafeGif;
// The GIF to repair must be the one the wizard would upload, not a hardcoded
// theme name (older builds used "ocean" which no longer ships). Prefer the
// current build asset, then the bundled snapshot; allow a local file to be
// picked so a custom character animation can be slowed as well.
async function repairSource(){
 const info=await fetch('../toolbox/firmware/info.json').then(r=>r.ok?r.json():null).catch(()=>null);
 const theme=info?.theme||'pink';
 for(const url of [`../build/ips/assets/robot-${theme}.gif`,'../toolbox/firmware/s1-full.gif']){
  const r=await fetch(url).catch(()=>null);
  if(r?.ok)return {url,bytes:new Uint8Array(await r.arrayBuffer())};
 }
 throw Error('找不到可修复的 S1 GIF：请在主题定制台重新生成动画，或用刷机向导重新上传');
}

$('connect').onclick=async()=>{
 try{
  $('connect').disabled=true;
  client=await AppClient.connect();
  $('disconnect').disabled=false;
  log('已连接，开始只读查询…','ok');
  const c=client;
  const cap=await read(c,'主控能力 (期望 0x4350)',()=>c.queryMain(9));
  const valid=await read(c,'主控 RTC 锚点有效标志',()=>c.queryMain(8));
  const rtcLo=await read(c,'主控 RTC 秒数低 16 位',()=>c.queryMain(6));
  const rtcHi=await read(c,'主控 RTC 秒数高 16 位',()=>c.queryMain(7));
  const state=await read(c,'屏幕时钟源 (0x401 无效 / 0x402 已同步)',()=>c.queryIps(4));
  const bcdLo=await read(c,'屏幕 BCD 时间低 16 位',()=>c.queryIps(5));
  const bcdHi=await read(c,'屏幕 BCD 时间高 16 位',()=>c.queryIps(6));
  const battery=await read(c,'电量原始值',()=>c.queryIps(2));
  const mode=await read(c,'连接模式 (1=USB / 0=2.4G / 2..4=蓝牙)',()=>c.queryIps(3));
  await read(c,'按键累计次数 (开机起)',()=>c.queryIps(18));
  await read(c,'大写锁定 (1=大写 A / 0=小写 a，屏幕本地计数)',()=>c.queryIps(16));
  if(bcdLo!==null&&bcdHi!==null){
   const t=decodeTime((bcdHi*65536+bcdLo)>>>0);
   log(`屏幕当前时间: ${t?t.text:'--:--:--（无效）'}`,t?'ok':'err');
  }
  lastReport={cap,valid,state,rtcHi,rtcLo,mode};
  $('calibrate').disabled=false;$('slow').disabled=false;
  if(cap!==null&&cap!==0x4350){
   verdict('主控没有 V7.1 补丁：时间功能依赖它，请走完整刷机向导（① ② 步）',true);
  }else if(state===0x401||valid===0){
   verdict('时间锚点无效：点「重新校时」即可恢复（常见于完全断电后）',true);
  }else if(state===0x402){
   verdict('固件与 RTC 状态正常，但画面不刷新：多半是 60ms 高帧率 GIF 挤掉了串口时间推送，点「降低动画负载」',true);
  }else{
   verdict('状态已读取，请按日志判断；可先校时，再降低动画负载',false);
  }
 }catch(e){log('诊断失败：'+e.message,'err');verdict('连接或读取失败：'+e.message,true);}
 finally{$('connect').disabled=false;}
};

$('disconnect').onclick=async()=>{await client?.close().catch(()=>{});client=null;$('disconnect').disabled=true;$('calibrate').disabled=true;$('slow').disabled=true;log('已断开');};

$('calibrate').onclick=async()=>{
 if(!client)return;
 try{
  $('calibrate').disabled=true;
  $('fix').textContent='正在校时并读回核对（约 10~40 秒）…';
  log('开始校时…');
  const s=await client.calibrate({timeZone:Intl.DateTimeFormat().resolvedOptions().timeZone||'Asia/Shanghai'});
  log(`校时通过：屏幕时间 ${s.screenTime?.text||'--:--:--'}，电量 ${s.battery===null?'--':s.battery+'%'}`,'ok');
  $('fix').textContent='校时完成。若时间过一会儿又停住，请继续点「降低动画负载」。';
  $('fix').classList.remove('bad');
 }catch(e){log('校时失败：'+e.message,'err');$('fix').textContent='校时失败：'+e.message;$('fix').classList.add('bad');}
 finally{$('calibrate').disabled=false;}
};

$('slow').onclick=async()=>{
 if(!client)return;
 try{
  $('slow').disabled=true;
  const picked=await repairSource();
  const {bytes,frames}=slowGif(picked.bytes,150);
  log(`已把 ${frames} 帧的时长改为 150ms，来源 ${picked.url.split('/').pop()}，准备覆盖上传 S1…`);
  $('fix').textContent='正在上传 S1 素材，请保持 USB 连接…';
  await client.upload(bytes,{replaceConfirmed:true,progress:p=>{if(p===1)log('S1 上传已应答','ok');}});
  log('完成：屏幕解码负载降到原来的约 40%，时间/状态推送应恢复正常','ok');
  $('fix').textContent='已修复。请观察屏幕时间与电量是否恢复刷新。';
  $('fix').classList.remove('bad');
 }catch(e){log('降速上传失败：'+e.message,'err');$('fix').textContent='失败：'+e.message;$('fix').classList.add('bad');}
 finally{$('slow').disabled=false;}
};
