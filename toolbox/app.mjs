// SPDX-License-Identifier: MIT
// Toolbox shell: one window, three local tools, no network access needed.
const $=id=>document.getElementById(id);
const TOOLS={
  wizard:{url:'../web/flash-wizard.html',title:'刷机向导'},
  studio:{url:'../studio/index.html',title:'主题定制台'},
  diagnose:{url:'../web/diagnose.html',title:'显示诊断'}
};
const loaded=new Set();
let current='wizard';

function show(name){
  if(!TOOLS[name])return;
  current=name;
  for(const b of document.querySelectorAll('[data-tab]'))b.classList.toggle('on',b.dataset.tab===name);
  const frame=$('frame');
  // Lazy: only mount a tool the first time it is opened, so the wizard does not
  // re-run its pre-check every time you switch tabs.
  if(!loaded.has(name)||frame.dataset.tool!==name){
    frame.src=TOOLS[name].url;
    frame.dataset.tool=name;
    loaded.add(name);
  }
  $('hint').hidden=name!=='wizard';
}
for(const b of document.querySelectorAll('[data-tab]'))b.onclick=()=>show(b.dataset.tab);
$('reload').onclick=()=>{const f=$('frame');f.src=TOOLS[current].url+'?t='+Date.now();};
$('open-ext').onclick=()=>window.open(new URL(TOOLS[current].url,location.href).href,'_blank');
// Clean exit. With the app window the process ends when the window closes, but
// when the page was opened in a normal browser tab the server must be told to
// stop, otherwise the exe would linger in the background.
$('quit').onclick=async()=>{
  if(!confirm('退出会停止本地服务。如果正在刷机请先等它完成，否则可能中断写入。\n\n确定退出？'))return;
  $('quit').disabled=true;$('quit').textContent='正在退出…';
  try{await fetch('/api/quit',{method:'POST'});}catch(e){}
  document.body.innerHTML='<div class="bye"><h1>已退出</h1><p>本地服务已停止，可以直接关闭这个窗口。<br>需要时重新双击 Rainy75Toolbox.exe 即可。</p></div>';
};

async function json(url){
  const r=await fetch(url,{cache:'no-store'});
  if(!r.ok)throw Error('HTTP '+r.status);
  return r.json();
}
function chip(id,text,kind){const el=$(id);el.textContent=text;el.className='chip'+(kind?' '+kind:'');}

async function loadSnapshotChip(){
  try{
    const info=await json('./firmware/info.json');
    const when=(info.capturedAt||'').slice(0,16).replace('T',' ');
    const sha=(info.ips&&info.ips.sha256||'').slice(0,8);
    chip('chip-fw',`快照 ${when} · 屏幕 ${sha}…`,/^\d{4}/.test(when)?'ok':'warn');
  }catch{
    // Publishable build: no factory firmware is bundled, this is expected.
    chip('chip-fw','未内置原厂固件（合规版）· 首次使用请导入','warn');
  }
}
async function loadStateChip(){
  try{
    const st=await json('/api/state');
    const themes=st.themes||{};
    const id=st.themeId||'';
    const name=(themes[id]&&themes[id].name)||id||'未知';
    chip('chip-theme',`构建主题 ${name} · S1 ${st.gifFrames||'?'} 帧`,'ok');
    const ready=st.stockReady&&Boolean(st.clang);
    const why=!st.stockReady
      ? '先在定制台 ⓪ 导入你自己的原厂屏幕固件'
      : (!st.clang ? '未找到 clang：只能刷已编译好的固件，不能重新编译' : '');
    chip('chip-build',ready?'编译依赖就绪（原厂基线 + clang）':('编译依赖缺失：'+why),ready?'ok':'warn');
  }catch(e){
    chip('chip-theme','定制台接口不可用','warn');
    chip('chip-build',String(e.message||e),'warn');
  }
}

loadSnapshotChip();
loadStateChip();
const wanted=new URLSearchParams(location.search).get('tab');
show(TOOLS[wanted]?wanted:'wizard');
