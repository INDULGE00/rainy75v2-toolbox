// SPDX-License-Identifier: MIT
// 一键刷机向导：自动加载本机已编译固件、完整校验、锁定顺序、自动擦写与校时。
// 不修改仓库原有刷机逻辑，仅复用 hid.mjs / protocol.mjs 的既有校验与协议实现。
import {AppClient,FlashClient,wait} from './hid.mjs';
import {validateBuild,validateGif,TARGETS,sha256,screenSafeGif,S1_FRAME_MIN_MS} from './protocol.mjs';

const $=id=>document.getElementById(id);
const F={
 mainBin:'../build/main/rainy75v2-main.bin',mainManifest:'../build/main/manifest.json',
 ipsBin:'../build/ips/rainy75v2-ips.bin',ipsManifest:'../build/ips/manifest.json'
};
// Bundled snapshot (toolbox/firmware) is the default source: it is the exact
// firmware pair that was verified on this keyboard, and it survives a rebuild
// of build/ for a new theme.
const SNAP={
 mainBin:'../toolbox/firmware/main.bin',mainManifest:'../toolbox/firmware/main.json',
 ipsBin:'../toolbox/firmware/ips.bin',ipsManifest:'../toolbox/firmware/ips.json',
 info:'../toolbox/firmware/info.json',
 gif:'../toolbox/firmware/s1-full.gif',lite:'../toolbox/firmware/s1-lite.gif',
 blank:'../toolbox/firmware/s1-blank.gif',preview:'../toolbox/firmware/preview.png'
};
const gifPath=t=>`../build/ips/assets/robot-${t}.gif`;
const previewPath=t=>`../build/ips/assets/preview-${t}.png`;
const EXPECT={
 mainStock:'31a9eb80752c1f8c94951dd6e2e6776eeb216f47ba58919ca36f6e6d26f0e476',
 ipsStock:'32defab7902e57eb972a577fc6cbf3a7e57bc772d59b99f11038370412b77f41'
};
// Step count. Step 5 (S1 upload) and step 6 (RTC calibration) are deliberately
// separate: a single AppClient session doing both would fail at the BEGIN stage
// on some units, while each one on its own always succeeds.
const MAX=6;
let mainPlan=null,ipsPlan=null,gifBytes=null,liteBytes=null,blankBytes=null,armed=false,busy=false,stage=0,logged=false;
let source='snapshot',local={main:null,ips:null,gif:null,gifName:''};
const stamp=()=>new Date().toLocaleTimeString('zh-CN',{hour12:false});
function log(msg,kind='info'){
 const el=$('log'),line=`[${stamp()}] ${kind==='err'?'X ':kind==='ok'?'OK ':'   '}${msg}`;
 el.textContent=(logged?el.textContent+'\n':'')+line;logged=true;el.scrollTop=el.scrollHeight;
}
let quickActive=false;
function setProgress(label,p){
 const frac=Math.max(0,Math.min(1,p||0));
 const pct=Math.max(0,Math.min(100,Math.round((stage/MAX)*100+frac*(100/MAX))));
 $('bar-fill').style.width=pct+'%';$('phase').textContent=label;$('pct').textContent=pct+'%';
 // While a quick action runs, mirror the current sub-step percentage next to its
 // verdict badge - that is the number people actually watch during a long upload.
 const qp=$('quick-pct');
 if(qp)qp.textContent=quickActive?Math.round(frac*100)+'%':'';
}
function mark(n,state,text){
 $('li'+n).dataset.state=state||'';
 if(text!==undefined)$('t'+n).textContent=text;
 refresh();
}
function refresh(){
 const cur=stage+1;
 for(let n=1;n<=MAX;n++){
  $('s'+n).disabled=busy||!armed||stage>=MAX||n!==cur;
  const li=$('li'+n),state=li.dataset.state||'';
  li.className=state;
  if(armed&&stage<MAX&&n===cur&&state!=='failed')li.classList.add('active');
 }
 $('probe').disabled=busy||!armed;
 $('skip').disabled=busy||!armed||stage>=MAX;
 for(const b of document.querySelectorAll('[data-quick]'))b.disabled=busy||!armed;
 for(const id of ['s5lite','s5fix','s5restore'])$(id).disabled=busy||!armed||(id==='s5lite'&&!liteBytes)||(id==='s5fix'&&!blankBytes);
 syncArm();
}

// A phone-saved GIF is almost never 320x172, and S1 must be exactly that. Rather
// than making the user recompile the IPS just to get a background, ask the local
// studio server to render the frames into the theme background (same pipeline as
// 定制台, including frame sampling under the S1 budget) and upload the result.
function toBase64(bytes){
 let out='',chunk=0x8000;
 for(let i=0;i<bytes.length;i+=chunk)out+=String.fromCharCode.apply(null,bytes.subarray(i,i+chunk));
 return btoa(out);
}
// A full-screen capture (the studio preview or a photo of the screen) pasted
// into S1 shows a second copy of the whole UI inside the character box. Refuse
// it before any conversion. Only the simplest, reliable signal is used here:
// a landscape 320x172-like aspect at a sizable resolution. The studio backend
// additionally checks for straight UI borders.
function looksLikeCapture(bytes){
 if(bytes.length<13||bytes[0]!==0x47||bytes[1]!==0x49||bytes[2]!==0x46)return false;
 const w=bytes[6]|bytes[7]<<8,h=bytes[8]|bytes[9]<<8;
 return w>=300&&(w/h)>=1.62&&(w/h)<=2.10;
}
async function convertS1(bytes,src,why,budgetKB,skipCaptureCheck=false){
 // 512 KB keeps the S1 write inside the screen's remaining external flash even
 // when the studio setting was raised for a bigger slot.
 // Internal re-conversion of an already valid 320x172 S1 GIF must not be
 // mistaken for a capture; only user-picked source images are checked.
 if(!skipCaptureCheck&&looksLikeCapture(bytes))throw Error(why+'；所选 GIF 是整屏截图，贴进 S1 会出现两层界面。请只上传角色本身（透明背景 GIF），或先把角色从截图裁出来');
 const body={image:'data:image/gif;base64,'+toBase64(bytes),
             themeId:src.themeId&&src.themeId!=='custom'?src.themeId:undefined,
             layout:src.srcName==='build/'?'studio':'base',
             budgetBytes:(budgetKB?Number(budgetKB):512)*1024};
 let r;
 try{
  r=await fetch('../api/convert-s1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 }catch{
  throw Error(why+'；本机自动转换服务不可用（用工具箱 exe 打开，或先用主题定制台生成 320×172 的动画）');
 }
 if(!r.ok){
  const info=await r.json().catch(()=>({}));
  throw Error(why+'；自动转换失败：'+(info.error||('HTTP '+r.status)));
 }
 const out=await r.json();
 const bin=atob(String(out.gif||'').split(',',2)[1]||'');
 const raw=new Uint8Array(bin.length);
 for(let i=0;i<bin.length;i++)raw[i]=bin.charCodeAt(i);
 validateGif(raw);
 const src0=out.source||[0,0];
 log(`GIF 自动转换成 320×172：${src0[0]}×${src0[1]} / ${out.sourceFrames} 帧 → ${out.frames} 帧 / ${Math.round(out.bytes/1024)} KB（${out.layout==='studio'?'定制台布局':'默认布局'}）`,'warn');
 return raw;
}
async function fetchBytes(path){const r=await fetch(path);if(!r.ok)throw Error('读取失败 '+path+' (HTTP '+r.status+')');return new Uint8Array(await r.arrayBuffer());}
async function fetchJson(path){const r=await fetch(path);if(!r.ok)throw Error('读取失败 '+path+' (HTTP '+r.status+')');return r.json();}
async function optionalGif(url){
 if(!url)return null;
 const b=await fetchBytes(url).catch(()=>null);
 if(!b)return null;
 try{validateGif(b);return b;}catch{return null;}
}
async function themeIndex(){
 const [t,c]=await Promise.all([
  fetchJson('../profiles/themes.json').catch(()=>({})),
  fetchJson('../local/themes.json').catch(()=>({}))]);
 return {...t,...c};
}
async function readFileBytes(file){return new Uint8Array(await file.arrayBuffer());}
// A firmware picked from disk has no manifest, so synthesise a minimal one. The
// only real guarantee we can give is the exact image length; the stock baseline
// SHA cannot be checked, which is why the source is marked non-strict.
async function localManifest(target,bytes){
 const t=TARGETS[target];
 if(bytes.length!==t.bytes)throw Error(`${target==='main'?'主控':'屏幕'}固件长度不对：必须是 ${t.bytes.toLocaleString()} B，所选文件是 ${bytes.length.toLocaleString()} B`);
 return {format:'rainy75v2-tft/build-v1',target,applicationBase:t.base,iapPid:t.pid,bytes:bytes.length,sha256:await sha256(bytes)};
}
async function loadSnapshot(){
 const [info,mb,mm,ib,im]=await Promise.all([
  fetchJson(SNAP.info).catch(()=>null),
  fetchBytes(SNAP.mainBin),fetchJson(SNAP.mainManifest),
  fetchBytes(SNAP.ipsBin),fetchJson(SNAP.ipsManifest)]);
 const when=info&&info.capturedAt?info.capturedAt.slice(0,16).replace('T',' '):'';
 return {mb,mm,ib,im,themeId:(info&&info.theme)||im.theme||'ocean',
  gifUrl:SNAP.gif,liteUrl:SNAP.lite,blankUrl:SNAP.blank,previewUrl:SNAP.preview,
  label:'内置快照（'+when+' 打包）',strictStock:true,srcName:'toolbox/firmware'};
}
async function loadBuild(){
 const [mb,mm,ib,im]=await Promise.all([fetchBytes(F.mainBin),fetchJson(F.mainManifest),fetchBytes(F.ipsBin),fetchJson(F.ipsManifest)]);
 const themeId=im.theme;
 if(typeof themeId!=='string'||!/^[a-z0-9_-]+$/i.test(themeId))throw Error('屏幕清单缺少合法的主题 ID，请先用定制台重新编译');
 return {mb,mm,ib,im,themeId,
  gifUrl:gifPath(themeId),liteUrl:`../build/ips/assets/robot-${themeId}-lite.gif`,
  blankUrl:`../build/ips/assets/robot-${themeId}-blank.gif`,previewUrl:previewPath(themeId),
  label:'build/ 最新编译',strictStock:true,srcName:'build/'};
}
async function loadLocal(){
 // The public/compliant build ships no factory firmware, so the snapshot may not
 // exist at all - fall back to an empty base instead of failing the whole load.
 let base={};
 try{base=await loadSnapshot();}
 catch{base={label:'自选本地文件',strictStock:false,srcName:'本地文件',themeId:'custom',
  gifUrl:null,liteUrl:null,blankUrl:null,previewUrl:null};}
 const out={...base,label:'自选本地文件',strictStock:false,srcName:'本地文件'};
 if(local.main){out.mb=local.main;out.mm=await localManifest('main',local.main);}
 if(local.ips){out.ib=local.ips;out.im=await localManifest('ips',local.ips);}
 if(local.gif){out.gifBytes=local.gif;out.gifUrl=null;out.liteUrl=null;out.blankUrl=null;out.previewUrl=null;out.themeId='custom';}
 return out;
}
const loadSource=()=>source==='build'?loadBuild():source==='local'?loadLocal():loadSnapshot();

async function snapshotAvailable(){
 try{const r=await fetch(SNAP.info,{cache:'no-store'});return r.ok;}catch{return false;}
}

async function precheck(){
 const out=$('precheck');
 if(!globalThis.navigator?.hid){
  out.classList.add('bad');
  out.textContent='✗ 当前浏览器不支持 WebHID。请用桌面版 Chrome / Edge 打开本页（不能是内嵌预览，也不能用 file:// 打开）';
  log('预检失败：当前浏览器不支持 WebHID','err');
  syncArm();
  return false;
 }
 try{
  // The public build ships no factory firmware. If the snapshot is absent, switch
  // to "pick local files" instead of failing with a confusing 404.
  if(source==='snapshot'&&!(await snapshotAvailable())){
   source='local';paintSource();
   log('本版本不内置原厂固件（合规版不含 WOB 二进制），已自动切到「自选本地文件」：请分别选择主控固件、屏幕固件和动画 GIF','warn');
  }
  const src=await loadSource(),names=await themeIndex();
  const themeName=src.themeId==='custom'?'自定义':((names[src.themeId]||{}).name||src.themeId);
  if(src.strictStock){
   if(src.mm.stockSha256!==EXPECT.mainStock)throw Error('主控基线不是官方 0.64，拒绝刷写。请用 inputs/main-stock.bin（官方 0.64）重新编译主控；若你的键盘仍是旧 0x3F 基线，改用 inputs/main-stock-063beta1.bin 编译，并把「固件来源」切到「自选本地文件」再刷');
   if(src.im.stockSha256!==EXPECT.ipsStock)throw Error('屏幕原厂基线 SHA 不匹配，拒绝刷写');
   if(src.mm.stockVersion&&src.mm.stockVersion!=='0.64')throw Error('构建清单标注的版本不是 0.64（实际 '+(src.mm.stockVersion||'未知')+'），拒绝刷写：请用官方 0.64 原厂输入重新编译主控');
  }
  mainPlan=await validateBuild(src.mb,src.mm);
  ipsPlan=await validateBuild(src.ib,src.im);
  let g=src.gifBytes||await fetchBytes(src.gifUrl);
  try{validateGif(g);}
  catch(e){
   // A user-picked source GIF that is actually a screen capture would be
   // converted and baked into S1, producing a second, nested interface.
   if(looksLikeCapture(g)){
    const sw=g[6]|(g[7]<<8),sh=g[8]|(g[9]<<8);
    throw Error(`所选 GIF 是整屏截图（${sw}×${sh}），贴进 S1 会出现两层界面。请只上传角色本身（透明背景 GIF），或先把角色从截图里裁出来`);
   }
   g=await convertS1(g,src,e.message,undefined,true);
  }
  // Normalise frame delays up front, exactly like the diagnostic page's
  // "降低动画负载" fix. A GIF exported at 20-60 ms/frame starves the screen's
  // UART ACK polling during upload, which is why the normal flow failed while
  // the slowed diagnostic upload succeeded.
  const safe=screenSafeGif(g);
  if(safe&&safe.raised){
   g=safe.bytes;
   log(`动画帧时长过短（${safe.raised}/${safe.frames} 帧），已自动降到 ≥${S1_FRAME_MIN_MS} ms 以匹配屏幕解码能力（等同诊断页的「降低动画负载」）`,'warn');
  }
  gifBytes=g;
  liteBytes=await optionalGif(src.liteUrl);
  blankBytes=await optionalGif(src.blankUrl);
  if(src.previewUrl)$('preview-img').src=src.previewUrl;
  $('theme-name').textContent=themeName+' · UI '+(src.im.uiVersion||'?')+' / '+(src.im.protocol||'?');
  $('gif-path').textContent=src.gifBytes?(local.gifName||'自选 GIF'):src.gifUrl.replace('../','');
  $('wizard-title').textContent='Rainy75 V2 刷机向导 · '+themeName;
  document.title='Rainy75 V2 刷机向导（'+themeName+' / 官方 0.64）';
  out.classList.remove('bad');
  out.textContent=
`✓ WebHID 可用
✓ 固件来源：${src.label}
${src.strictStock?'':'⚠ 自定义固件：无法核对官方 0.64 基线，来源与正确性请自行确认（长度/目标/PID/SHA-256 仍会校验）\n'}`+
`✓ 主控 ${src.srcName}
   基线 ${src.strictStock?'官方 0.64':(src.mm.stockVersion||'自定义')} · 目标 main · IAP 36B0:3079 · 应用区 0x2000
   ${mainPlan.bytes.length.toLocaleString()} B · SHA-256 ${mainPlan.sha256}
✓ 屏幕 ${src.srcName}
   主题 ${themeName} (${src.themeId}) · UI ${src.im.uiVersion||'?'} / ${src.im.protocol||'?'} · IAP 36B0:3078 · 应用区 0x4000
   ${ipsPlan.bytes.length.toLocaleString()} B · SHA-256 ${ipsPlan.sha256}
✓ 素材 ${src.gifBytes?(local.gifName||'自选 GIF'):src.gifUrl.replace('../','')}
   ${g.length.toLocaleString()} B · 320×172 · 约 ${Math.ceil(g.length/232)} 个 HID 数据包 · 将写入 S1
${liteBytes?`✓ 精简排障版 ${liteBytes.length.toLocaleString()} B · 约 ${Math.ceil(liteBytes.length/232)} 包（大文件上传失败时可单独试它）`:'· 未找到精简排障版素材（可选）'}
✓ 目标 / PID / 长度 / SHA-256 全部校验通过，未做任何擦除`;
  log(`预检通过（${src.label}）：两份固件与动画素材均已校验，尚未连接或写入设备；S1 预计 ${Math.ceil(g.length/232)} 个数据包`);
 }catch(e){
  mainPlan=ipsPlan=gifBytes=null;
  out.classList.add('bad');out.textContent='✗ 预检失败：'+e.message;
  log('预检失败：'+e.message,'err');
 }
 syncArm();
 return Boolean(mainPlan&&ipsPlan&&gifBytes);
}

const checks=['c1','c2','c3','c4'];
function syncArm(){
 $('arm').disabled=busy||armed||!checks.every(c=>$(c).checked)||!Boolean(mainPlan&&ipsPlan&&gifBytes);
 for(const id of ['f-main','f-ips','f-gif'])$(id).disabled=busy||armed;
 for(const b of document.querySelectorAll('[data-src]'))b.disabled=busy||armed;
}
for(const id of checks)$(id).onchange=syncArm;
$('arm').onclick=()=>{armed=true;$('arm').disabled=true;$('arm').textContent='已解锁 · 请按 ①→⑥ 顺序执行';$('arm-note').textContent='刷机过程中请勿断电、拔线或切换到无线模式。';log('已确认 4 项前置条件，刷机步骤解锁（固件来源已锁定为 '+(source==='snapshot'?'内置快照':source==='build'?'build/ 最新编译':'自选本地文件')+'）');refresh();};

// ---- firmware source selector -------------------------------------------------
function paintSource(){
 for(const b of document.querySelectorAll('[data-src]'))b.classList.toggle('on',b.dataset.src===source);
 $('src-local').hidden=source!=='local';
}
for(const b of document.querySelectorAll('[data-src]'))b.onclick=async()=>{
 if(busy||armed)return;
 source=b.dataset.src;paintSource();
 mainPlan=ipsPlan=gifBytes=liteBytes=blankBytes=null;
 refresh();await precheck();paintSource();refresh();
};
async function pickLocal(input,slot){
 const f=input.files&&input.files[0];
 try{
  if(!f){local[slot]=null;if(slot==='gif')local.gifName='';}
  else{
   local[slot]=await readFileBytes(f);
   if(slot==='gif')local.gifName=f.name;
   log(`已选择本地${slot==='main'?'主控':slot==='ips'?'屏幕':'动画'}文件 ${f.name} · ${local[slot].length.toLocaleString()} B`);
  }
 }catch(e){log('读取本地文件失败：'+e.message,'err');}
 mainPlan=ipsPlan=gifBytes=null;
 await precheck();refresh();
}
$('f-main').onchange=()=>pickLocal($('f-main'),'main');
$('f-ips').onchange=()=>pickLocal($('f-ips'),'ips');
$('f-gif').onchange=()=>pickLocal($('f-gif'),'gif');
paintSource();

async function run(n,fn,label){
 if(busy||!armed||n!==stage+1)return;
 busy=true;$('skip').disabled=true;refresh();
 mark(n,'','进行中…');setProgress(label,0);log(`步骤 ${n} 开始：${label}。即将弹出设备选择器，请按页面提示选择对应 PID`);
 try{
  await fn();stage=n;mark(n,'done','完成');setProgress(label+' · 完成',0);
  log(`步骤 ${n} 完成：${label}`,'ok');
 }catch(e){
  mark(n,'failed','失败 · 可重试本步');
  log(`步骤 ${n} 失败：${e.message||e}`,'err');
  if(e.cause?.message)log('内部原因：'+e.cause.message,'err');
  log('排查：设备选择器选对 PID、USB 直连键盘本体、关闭 WOB 官方驱动页；若提示「屏幕协议不匹配 / 主控不是 V7.1」说明还没刷 ①~④，不能用跳过。⑤ 与 ⑥ 已刻意拆开：上传与校时各自独立连接，失败只会落在其中一步，直接重试该步即可。','err');
 }finally{busy=false;refresh();}
}

$('s1').onclick=()=>run(1,async()=>{
 const app=await AppClient.connect();
 await app.enterIap('main');
 log('已在 36B0:3075 发送主控升级命令，设备将重新枚举为 36B0:3079');
 setProgress('等待主控重新枚举…',0.4);
 const seen=await waitForPid(0x3079,15000);
 if(seen)log('主控已进入升级模式（36B0:3079 已出现）','ok');
 else log('等待超时：选择器里如果只有 3075，请稍等几秒再点一次②','warn');
 setProgress('主控已进入升级模式',1);
},'主控进入升级模式');

$('s2').onclick=()=>run(2,async()=>{
 const f=await FlashClient.connect(mainPlan);
 try{
  await f.flash((phase,p)=>setProgress('主控 · '+phase,p));
 }catch(e){await f.io.close().catch(()=>{});throw e;}
 log('主控烧录与全字节回读校验完成，等待设备重启…');
 await wait(2500);
},'烧录键盘主控');

// Steps 3-6 are plain functions so the quick actions below can replay only the
// part that actually needs redoing (theme colour = screen firmware, animation =
// S1 asset, clock = RTC). Screen firmware and S1 live in separate storage, so
// re-flashing the main controller is NOT required for any of those.
// After a "reboot into IAP" command the device re-enumerates with a different
// PID. The chooser has to be opened *after* that happens, otherwise the user
// sees only the old device and gets "设备型号或 HID 描述符不匹配".
const PID_APP = 0x3075;
async function waitForPid(pid, timeout = 15000) {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    try {
      const list = await navigator.hid.getDevices();
      if (list.some(d => d.productId === pid)) return true;
    } catch { /* getDevices can throw right after unplug */ }
    await wait(400);
  }
  return false;
}
function connectHint(e, pid, label) {
  const msg = String(e?.message || e);
  if (!/不匹配|not found|NotFound/i.test(msg)) return e;
  return Error(`设备选择器里没有出现 ${label}（36B0:${pid.toString(16)}）：`
    + '键盘可能还在重启，等 2~3 秒再点一次；连续失败就拔插 USB、切有线档后重试。'
    + '（原始信息：' + msg + '）');
}

async function step3(){
 const app=await AppClient.connect();
 // Advisory only: a screen running stale/broken firmware may not answer the
 // capability query, and that must not stop us from reaching IAP (that is the
 // only way back to a working image).
 try{
  const {flashKiB,series}=await app.probeIpsTarget();
  log(`屏幕芯片：${flashKiB} KiB 片内 Flash / 系列 ${series}`,'ok');
 }catch(e){
  log('屏幕没有应答容量查询（'+e.message+'）：继续进入升级模式，刷完即可恢复','warn');
 }
 await app.enterIap('ips');
 log('已在 36B0:3075 发送屏幕升级命令，设备将重新枚举为 36B0:3078');
 setProgress('等待屏幕重新枚举…',0.4);
 const seen=await waitForPid(0x3078,15000);
 if(seen)log('屏幕已进入升级模式（36B0:3078 已出现），可以烧录了','ok');
 else log('等待超时：没在已授权设备里看到 36B0:3078。下一步的选择器里如果只有 3075，请稍等几秒再点一次④','warn');
 setProgress('屏幕已进入升级模式',1);
}
async function step4(){
 let f;
 try{f=await FlashClient.connect(ipsPlan);}
 catch(e){throw connectHint(e,0x3078,'屏幕升级设备');}
 try{
  await f.flash((phase,p)=>setProgress('屏幕 · '+phase,p));
 }catch(e){await f.io.close().catch(()=>{});throw e;}
 log('屏幕烧录与全字节回读校验完成，等待设备重启…');
 await wait(2500);
 // Prove which firmware is actually running: a stale image is the usual reason
 // "刷完没变化" — the build tag lives in the patched UI, not in the banner.
 try{
  // Reuses the already-granted device; guarded so a reboot or a missing
  // permission can never stall the remaining quick-action steps.
  const check=await Promise.race([AppClient.connect(),
    new Promise((_,rej)=>setTimeout(()=>rej(Error('设备重新枚举超时')),8000))]);
  try{
   const tag=await check.queryIps(17);
   log(tag===0x1314
     ? `已确认屏幕正在运行 UI 1.3.14（build 0x${tag.toString(16)}）`
     : `屏幕回报的 UI 构建是 0x${tag.toString(16)}，不是本版 0x1314：可能刷的是旧固件`, tag===0x1314?'ok':'warn');
  }finally{await check.close().catch(()=>{});}
 }catch(e){log('烧录后回读构建号失败（不影响使用）：'+e.message,'warn');}
}
// Extract the device status code from whatever layer raised it (the ack object,
// the "素材指令返回状态 N" message, or the JSDOM-ish last-ack dump inside an
// "指令应答超时：{...status:255...}" message).
function statusOf(e){
 if(!e)return null;
 if(Number.isInteger(e.status))return e.status;
 const m=String(e.message||'').match(/状态\s*(\d+)|"status":(\d+)/);
 return m?Number(m[1]||m[2]):null;
}
function uploadProgress(label){
 let last=-1;
 return p=>{
  setProgress(label,p);
  const pct=Math.round(p*100);
  if(pct>=last+10){last=pct;log(`${label} ${pct}%`);setQuickDetail(`${label} ${pct}%`);}
 };
}
// S1 write with self-repair: BEGIN is sometimes refused (status 4 = slot full,
// 255 = file table not settled) right after an interrupted write. Writing the
// 454 B placeholder first rewrites the same file name and frees the slot, then
// the real animation goes in - all inside one HID session to avoid extra
// device-picker dialogs.
// Fallback used only if the first (already normalised) upload still fails.
// screenSafeGif only raises short delays; it never speeds up a slow GIF.
const slowGif=screenSafeGif;
async function uploadS1(app){
 const attempt=async(label,bytes)=>{
  log(`${label}：${(bytes.length/1024).toFixed(0)} KB / 约 ${Math.ceil(bytes.length/232)} 包`, 'info');
  await app.upload(bytes,{replaceConfirmed:true,progress:uploadProgress(label)});
 };
 let working=gifBytes;
 try{
  await attempt('写入 S1 动画',working);
  return 'full';
 }catch(e){
  const st=statusOf(e);
  // 4 = slot full, 255 = file table not settled. Both are cleared by rewriting
  // the 454 B placeholder under the same name first.
  if((st===4||st===255)&&blankBytes){
   log(`上传被拒（状态 ${st}）：先写入 454 B 占位素材释放同名 S1 文件…`,'warn');
   await app.upload(blankBytes,{replaceConfirmed:true});
   await wait(2500);
   try{await attempt('重试写入 S1 动画',working);return 'full';}
   catch(e2){log(`仍然失败：${e2.message}`,'warn');}
  }else{
   log(`上传失败：${e.message}`,'warn');
  }
 }
 // Automatic degradation: slower frame delay first (no size change), then a
 // re-converted, smaller animation, then the shipped lite fallback.
 const slowed=slowGif(working,150);
 if(slowed){
  log(`自动降级：把 ${slowed.frames} 帧的时长改成 150 ms 后重传（等于诊断页的「降低动画负载」）…`,'warn');
  try{await attempt('写入降速 S1 动画',slowed.bytes);log('降速后上传成功','ok');return 'slowed';}
  catch(e){log(`降速重传仍失败：${e.message}`,'warn');}
 }
 try{
  const small=await convertS1(working,{themeId:local.themeId,srcName:'build/'},'动画仍然传不进去','256',true);
  const slowedSmall=slowGif(small,150);
  log('自动降级：改用 256 KB 上限重新生成后再传（帧数更少）…','warn');
  await attempt('写入小体积 S1 动画',slowedSmall?slowedSmall.bytes:small);
  log('小体积动画上传成功','ok');
  return 'small';
 }catch(e){log(`小体积重试失败：${e.message}`,'warn');}
 if(liteBytes){
  log('自动降级：改用内置精简版（24 帧 / 245 KB）…','warn');
  await attempt('写入精简版 S1',liteBytes);
  log('已写入精简版动画：屏幕现在可用。想要更长的动画，请到定制台把「动画体积上限」调到 256 KB 重新生成后再传','warn');
  return 'lite';
 }
 throw Error('S1 写入连续失败（完整 / 降速 / 小体积 / 精简版都试过）。请确认 USB 直连有线档，或在 WOB 官方驱动里删掉不用的图片腾出空间');
}

async function step5(){
 const app=await AppClient.connect();
 try{
  const mode = await uploadS1(app);
  if (mode === 'lite') {
   log('S1 已写入（降级为精简版 24 帧）','warn');
  } else {
   log('S1 角色动画已写入并应答','ok');
  }
  log('下一步 ⑥ 会重新连一次设备，只写 RTC 时间，不会重传动画');
 }finally{await app.close().catch(()=>{});}
 // Give the screen time to finish parsing the file before the RTC session opens,
 // otherwise the NEXT step's BEGIN can be answered with status 4.
 await wait(1500);
}
async function step6(){
 const app=await AppClient.connect();
 try{
  setProgress('校时并读回核对主控与屏幕',0.3);
  const s=await app.calibrate({timeZone:Intl.DateTimeFormat().resolvedOptions().timeZone||'Asia/Shanghai'});
  log(`校时通过 · 屏幕时间 ${s.screenTime?.text||'--:--:--'} · 电量 ${s.battery===null?'--':s.battery+'%'} · 连接模式 ${s.mode}`,'ok');
 }finally{await app.close().catch(()=>{});}
}

$('s3').onclick=()=>run(3,step3,'屏幕进入升级模式');
$('s4').onclick=()=>run(4,step4,'烧录屏幕固件');
$('s5').onclick=()=>run(5,step5,'上传 S1 动画');
$('s6').onclick=()=>run(6,async()=>{
 await step6();
 log('刷机完成：可以关闭网页、拔线，键盘切无线后屏幕仍独立显示','ok');
},'写入当前时间');

// Quick actions: run exactly the listed steps, in order, regardless of where the
// ①→⑥ state machine currently is. They share the same code paths (and therefore
// the same safety checks) as the full flow, they just do not demand that the
// earlier steps were performed in this browser session.
const QUICK={
 qtime:[{n:6,fn:step6,label:'写入当前时间'}],
 qgif:[{n:5,fn:step5,label:'上传 S1 动画'}],
 qtheme:[{n:3,fn:step3,label:'屏幕进入升级模式'},{n:4,fn:step4,label:'烧录屏幕固件'}],
 qthemeall:[{n:3,fn:step3,label:'屏幕进入升级模式'},{n:4,fn:step4,label:'烧录屏幕固件'},{n:5,fn:step5,label:'上传 S1 动画'}],
 // Screen already sitting in its IAP (dark screen after an interrupted write):
 // no ③ needed, straight to writing the firmware.
 qrescue:[{n:4,fn:step4,label:'直接烧录屏幕固件（设备已在 IAP）'}],
};

// Live progress for the quick actions: one row per sub-step plus an overall
// state, so "did it work?" is answerable at a glance instead of by reading logs.
function paintQuick(label,items,states,overall){
 const box=$('quick-run');if(!box)return;
 box.hidden=false;
 $('quick-run-title').textContent=label;
 const st=$('quick-run-state');
 st.textContent=overall.text;st.className='qstate '+overall.cls;
 const sig=items.map(i=>i.n).join(',')+'|'+states.map(s=>s.cls).join(',');
 const list=$('quick-steps');
 if(list.dataset.sig!==sig){
  list.dataset.sig=sig;
  list.innerHTML=items.map((it,i)=>{
   const s=states[i]||{cls:'wait',text:'待执行'};
   return `<span class="qstep ${s.cls}"><i>${i+1}</i>${it.label}<b>${s.text}</b></span>`;
  }).join('');
 }
}
function setQuickDetail(text){const el=$('quick-detail');if(el)el.textContent=text;}

async function quick(key,label,btn){
 if(busy||!armed)return;
 const items=QUICK[key];
 busy=true;$('skip').disabled=true;refresh();
 for(const b of document.querySelectorAll('[data-quick]'))b.classList.remove('ok','err','run');
 if(btn)btn.classList.add('run');
 const states=items.map(()=>({cls:'wait',text:'待执行'}));
 const paint=overall=>paintQuick(label,items,states,overall);
 quickActive=true;
 paint({cls:'run',text:'进行中'});
 setQuickDetail('准备连接设备…');
 $('quick-pct').textContent='0%';
 log(`【快捷】${label}：连续执行 ${items.length} 个动作，不重刷主控。设备选择器出现时请选中对应 PID`);
 let failed=null;
 try{
  for(let i=0;i<items.length;i++){
   const it=items[i];
   states[i]={cls:'run',text:'进行中…'};paint({cls:'run',text:'进行中'});
   mark(it.n,'','进行中…');setProgress(it.label,0);setQuickDetail(it.label);
   $('quick-pct').textContent=`第 ${i+1}/${items.length} 步`;
   log(`【快捷】开始：${it.label}`);
   await it.fn();
   stage=Math.max(stage,it.n);mark(it.n,'done','完成');
   states[i]={cls:'ok',text:'✓ 完成'};paint({cls:'run',text:'进行中'});
   await wait(400);
  }
  quickActive=false;
  setProgress(label+' · 完成',1);
  setQuickDetail('全部完成');
  paint({cls:'ok',text:'✓ 成功'});
  $('quick-pct').textContent='完成';
  if(btn){btn.classList.remove('run');btn.classList.add('ok');}
  log(`【快捷】${label} 完成，可以拔线了`,'ok');
 }catch(e){
  failed=e;
  quickActive=false;
  const i=states.findIndex(s=>s.cls==='run');
  if(i>=0)states[i]={cls:'err',text:'✗ 失败'};
  paint({cls:'err',text:'✗ 失败'});
  $('quick-pct').textContent='已停止';
  const msg=String(e.message||e);
  setQuickDetail('失败：'+msg);
  if(btn){btn.classList.remove('run');btn.classList.add('err');}
  log(`【快捷】${label} 失败：${msg}`,'err');
  const st=statusOf(e);
  if(st===4||st===255){
   log('这个状态是屏幕拒绝了写入请求（文件表没整理好/空间不足）。下一步依次试：①「清理并重试上传」；②「直接烧录屏幕固件（设备已在 IAP）」重刷屏幕；③ 用精简版动画确认是不是包数过多。','err');
  }else{
   log('提示：若报「屏幕协议不匹配 / 主控不是 V7.1」，说明这台键盘的主控还是原厂固件，需要先完整执行 ①→④ 一次（之后就能一直用快捷操作）。','err');
  }
 }finally{busy=false;refresh();}
}
for(const b of document.querySelectorAll('[data-quick]')){
 b.onclick=()=>quick(b.dataset.quick,b.dataset.label||b.textContent.trim(),b);
}

// Independent helpers: they do NOT advance the ①→⑥ state machine, so a failed
// upload or a failed calibration can be retried / isolated on its own.
async function withApp(fn){const app=await AppClient.connect();try{return await fn(app);}finally{await app.close().catch(()=>{});}}
async function auxRun(label,fn){
 if(busy||!armed||!gifBytes)return;
 busy=true;refresh();log(label+'：即将弹出设备选择器，请选 36B0:3075');
 try{await fn();log('✓ '+label+' 完成','ok');}
 catch(e){log(label+' 失败：'+(e.message||e),'err');}
 finally{busy=false;refresh();}
}
function uploadLogger(){
 let last=-1;
 return p=>{const pct=Math.round(p*100);if(pct>=last+10){last=pct;log(`S1 写入 ${pct}%`);}};
}
$('s5lite').onclick=()=>auxRun('上传精简版 S1（排障）',async()=>{
 if(!liteBytes)throw Error('精简版素材不可用');
 await withApp(app=>app.upload(liteBytes,{replaceConfirmed:true,progress:uploadLogger()}));
 log('精简版 24 帧 / 200ms 已写入；若它成功而完整版失败，说明问题是包数过多/总线拥塞，可在定制台减少帧数或调大每帧时长');
});
// BEGIN 状态 4 = 设备拒绝开始传输。最常见原因是外置 Flash 里旧的 S1 文件
// 没被释放，新文件更大就放不下。先用 454 B 占位素材覆盖同名文件释放空间，
// 再传目标动画；若仍失败自动回退到精简版，保证屏幕始终有可用底图。
$('s5restore').onclick=()=>auxRun('恢复干净底图（消除界面嵌套）',async()=>{
 // Always use the bundled, known-clean robot GIF, never the user's current
 // source: a nested image came from a screenshot baked into S1, and the only
 // reliable way to clear it is to overwrite S1 with a pristine base image.
 const clean=await fetchBytes(SNAP.gif).catch(()=>null);
 if(!clean)throw Error('内置干净底图素材不可用');
 const restore=async()=>{
  log('第 1 步：写入 454 B 占位素材，覆盖 S1 里可能残留的嵌套画面…');
  if(blankBytes){await withApp(app=>app.upload(blankBytes,{replaceConfirmed:true}));await wait(2000);}
  else log('没有占位素材，直接覆盖底图','warn');
  await withApp(app=>app.upload(clean,{replaceConfirmed:true,progress:uploadLogger()}));
 };
 try{await restore();log('✓ 已用内置原版机器人底图覆盖 S1：屏幕上的嵌套界面应已消失','ok');}
 catch(e){
  log('完整底图写入失败：'+e.message+'，尝试精简版…','warn');
  if(!liteBytes)throw Error('精简版也不可用，无法恢复干净底图');
  await withApp(app=>app.upload(liteBytes,{replaceConfirmed:true,progress:uploadLogger()}));
  log('✓ 已写入精简版干净底图，嵌套界面应已消失','ok');
 }
});
$('s5fix').onclick=()=>auxRun('清理并重试上传（两步法）',async()=>{
 if(!blankBytes)throw Error('占位素材不可用');
 await withApp(async app=>{
  log('第 1 步：写入 454 B 占位素材，覆盖并释放同名旧 S1 文件…');
  await app.upload(blankBytes,{replaceConfirmed:true});
  log('占位素材已写入，等待设备完成文件替换…');
  await wait(2000);
  log('第 2 步：上传完整动画…');
  try{
   await app.upload(gifBytes,{replaceConfirmed:true,progress:uploadLogger()});
   log('✓ 完整动画已写入 S1','ok');
  }catch(e){
   log('完整动画仍被拒绝：'+e.message,'err');
   log('自动回退：改用精简版（24 帧 / 250 KB），确保屏幕有可用动画…');
   if(!liteBytes)throw Error('精简版也不可用，请用 WOB 官方驱动删除多余图片/动画腾出空间');
   await app.upload(liteBytes,{replaceConfirmed:true,progress:uploadLogger()});
   log('✓ 已回退为精简版动画。完整版需要更多 Flash 空间，请在 WOB 官方驱动删除多余图片/动画后再试','ok');
  }
 });
});

$('probe').onclick=async()=>{
 if(busy)return;busy=true;refresh();
 try{
  const app=await AppClient.connect();
  try{
   const s=await app.status();
   log(`只读状态：主控 V7.1 / 屏幕 L6 已确认 · 时间 ${s.screenTime?.text||'--:--:--'} · 电量 ${s.battery===null?'--':s.battery+'%'} · 最近键码 ${s.key}`,'ok');
  }finally{await app.close().catch(()=>{});}
 }catch(e){log('只读状态读取失败：'+e.message+'（若尚未刷入新固件，原厂固件无 V7.1/L6 能力属正常）','err');}
 finally{busy=false;refresh();}
};

$('skip').onclick=()=>{
 if(stage>=MAX||busy)return;
 const n=stage+1;mark(n,'skipped','已跳过');stage=n;setProgress('已跳过第 '+n+' 步',0);
 log('已手动跳过步骤 '+n+'（仅在确认设备已进入升级模式时使用）');
 refresh();
};
$('copylog').onclick=async()=>{
 try{await navigator.clipboard.writeText($('log').textContent);$('copylog').textContent='已复制';setTimeout(()=>$('copylog').textContent='复制诊断日志',1500);}
 catch(e){$('copylog').textContent='复制失败，请手动选中';}
};

await precheck();
refresh();
