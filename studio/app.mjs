// SPDX-License-Identifier: MIT
// Local customization studio: edit character sprites + theme colors, rebuild in one click.
const $ = id => document.getElementById(String(id).replace(/^#/, ''));
// getElementById cannot take a compound selector; the pixel editor needs one.
const $$ = sel => document.querySelector(sel);
const COLOR_FIELDS = [
  ['background', '整屏底色'], ['panel', '键帽 / 面板底色'], ['shell', '外边框 / 阴影'],
  ['ink', '文字与线条'], ['accent', '点缀色'],
];
const SEQ = {
  turn: [0, 0, 1, 1, 2, 2, 1, 1],
  front: [0, 0, 0, 0, 0, 0, 0, 0],
  two: [0, 0, 1, 1, 0, 0, 1, 1],
  flip: [0, 0, 2, 2, 0, 0, 2, 2],
};
const DEFAULT_CHAR = {
  enabled: true, name: '自定义角色', files: [], sequence: SEQ.turn,
  box: [188, 42, 300, 154], scale: 1.0, offsetY: 0,
  bob: [0, 0, -1, -1, 0, 1, 1, 0], shadow: true, duration: 160,
};
let S = null, appliedColors = {}, timer = null, logged = false, busy = false;

function log(msg, kind = 'info') {
  const el = $('log'), prefix = kind === 'err' ? 'X ' : kind === 'ok' ? 'OK ' : '   ';
  const line = `[${new Date().toLocaleTimeString('zh-CN', { hour12: false })}] ${prefix}${msg}`;
  el.textContent = (logged ? el.textContent + '\n' : '') + line;
  logged = true; el.scrollTop = el.scrollHeight;
}
async function api(path, opts) {
  const r = await fetch(path, opts);
  if ((r.headers.get('content-type') || '').includes('json')) return { status: r.status, data: await r.json() };
  return { status: r.status, blob: await r.blob() };
}
function setBusy(on) {
  busy = on;
  for (const id of ['apply', 'assets-only', 'reset']) $(id).disabled = on || !S || !S.sprites.length;
}
function seqKey(seq, n) {
  if (n < 2) return 'front';
  if (n < 3) return 'two';
  for (const [k, v] of Object.entries(SEQ)) if (JSON.stringify(v) === JSON.stringify(seq)) return k;
  return 'turn';
}
function safeSeq(key, n) {
  if (n < 2) return SEQ.front;
  if (n < 3) return key === 'front' ? SEQ.front : SEQ.two;
  return SEQ[key] || SEQ.turn;
}
function collectColors() {
  const out = {};
  for (const [k] of COLOR_FIELDS) out[k] = $('#color-' + k).value.toLowerCase();
  return out;
}
function collectCharacter() {
  const style = $('#motion-style').value;
  const cfg = {
    ...S.character,
    enabled: true,
    name: $('#char-name').value.trim() || '自定义角色',
    files: S.character.files,
    theme: $('#theme-id').value.trim(),
    sequence: safeSeq($('#sequence').value, S.sprites.length),
    scale: parseFloat($('#scale').value),
    offsetY: parseInt($('#offsetY').value, 10),
    duration: parseInt($('#duration').value, 10),
    shadow: $('#shadow').checked,
    removeBg: $('#remove-bg').checked,
    box: S.character.box || DEFAULT_CHAR.box,
    bob: S.character.bob || DEFAULT_CHAR.bob,
  };
  if (S.character.sourceGif) {
    cfg.motion = { enabled: false, frames: cfg.frameCount || 8, style: 'gif' };
    cfg.frameCount = cfg.frameCount || 8;
    cfg.sequence = S.character.sequence;
    cfg.bob = [0, 0, 0, 0, 0, 0, 0, 0]; // GIF 自带动作，禁止叠加合成浮动
    return cfg;
  }
  if (style === 'lively') {
    cfg.motion = { enabled: true, frames: 28, style: 'gentle' };
    cfg.frameCount = 28;
  } else {
    cfg.motion = { enabled: false, frames: 8, style: 'off' };
    cfg.frameCount = 8;
    cfg.sequence = style === 'idle' ? SEQ.front.slice() : safeSeq($('#sequence').value, S.sprites.length);
  }
  return cfg;
}
function syncMotionUI() {
  const gifMode = Boolean(S && S.character.sourceGif);
  const lively = $('#motion-style').value === 'lively';
  $('#sequence').disabled = lively || gifMode;
  $('#sequence').title = gifMode ? '正在逐帧播放上传的 GIF，此选项不适用' : (lively ? '温和动作模式由程序生成，此选项不适用' : '');
  $('#motion-style').disabled = gifMode;
}
function colorChanged() {
  if ($('#theme-id').value.trim() !== S.themeId) return true;
  const now = collectColors();
  return COLOR_FIELDS.some(([k]) => (now[k] || '').toLowerCase() !== (appliedColors[k] || '').toLowerCase());
}
function updateDirty() {
  const changed = colorChanged();
  const hint = $('apply-hint');
  hint.classList.toggle('warn', changed);
  hint.textContent = changed
    ? '检测到主题色或主题 ID 已改动：必须点「应用并重新编译 IPS 固件」，仅换 GIF 会让底色不匹配。'
    : '主题色未改动：可以直接「仅重新生成 S1 动画素材」，刷过固件的键盘只需重新上传 GIF，不用重刷屏幕。';
  if (!busy) $('assets-only').disabled = changed || !S.sprites.length;
}

function renderColors() {
  const box = $('#colors'); box.replaceChildren();
  for (const [key, label] of COLOR_FIELDS) {
    const row = document.createElement('div'); row.className = 'color-row';
    const input = document.createElement('input'); input.type = 'color'; input.id = 'color-' + key;
    input.value = (S.themes[S.themeId] || {})[key] || '#eaf2fd';
    const lab = document.createElement('label'); lab.htmlFor = input.id; lab.textContent = label;
    const code = document.createElement('code'); code.textContent = input.value;
    input.oninput = () => { code.textContent = input.value; schedulePreview(); updateDirty(); };
    row.append(input, lab, code); box.append(row);
  }
  appliedColors = {};
  for (const [k] of COLOR_FIELDS) appliedColors[k] = ($('#color-' + k).value || '').toLowerCase();
}
function renderPresets() {
  const box = $('#presets'); box.replaceChildren();
  for (const [name, colors] of Object.entries(S.presets || {})) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = name;
    b.onclick = () => {
      for (const [k] of COLOR_FIELDS) {
        const input = $('#color-' + k);
        input.value = colors[k] || input.value;
        input.dispatchEvent(new Event('input'));
      }
      log('已套用预设配色：' + name);
    };
    box.append(b);
  }
}
function renderSprites() {
  const box = $('#sprites'); box.replaceChildren();
  if (!S.sprites.length) {
    const p = document.createElement('p'); p.className = 'hint';
    p.textContent = '尚未上传角色素材，请先选择或拖入一张图片。'; box.append(p); return;
  }
  for (const sp of S.sprites) {
    const card = document.createElement('div'); card.className = 'sprite';
    const thumb = document.createElement('div'); thumb.className = 'thumb';
    const img = document.createElement('img'); img.src = sp.url + '?v=' + Date.now(); img.alt = sp.name;
    thumb.append(img);
    const small = document.createElement('small');
    small.textContent = ({ front: '正面', side: '侧面', back: '背面' })[sp.name] || sp.name;
    card.append(thumb, small); box.append(card);
  }
}
function fmt(n) {
  if (!n) return '—';
  return n >= 1024 * 1024 ? (n / 1024 / 1024).toFixed(1) + ' MiB' : (n / 1024).toFixed(1) + ' KiB';
}
function renderLoopInfo() {
  const frames = Number(S.character.frameCount || 8);
  const ms = Number($('#duration').value || 110);
  $('loop-info').textContent = `当前循环总时长 ≈ ${(frames * ms / 1000).toFixed(2)} 秒（${frames} 帧 × ${ms} ms）· 上传 GIF 时会按原 GIF 总时长自动换算，不再因抽帧而变快`;
}
function renderLimits() {
  const L = S.limits || {}, box = $('limits');
  const screen = (L.screen || [320, 172]).join('×');
  const budget = S.s1Budget || L.outputBytes;
  const rows = [
    ['屏幕上真正的大小', `整个屏幕 ${screen}；角色活动区约 112×112，其余是键帽卡片，角色超出会被裁掉`],
    ['上传源文件', `≤ ${fmt(L.uploadBytes)}；任意分辨率都行，程序会等比缩放（最多保留 ${L.maxFrames} 帧）`],
    ['写进屏幕的体积', `当前上限 ${fmt(budget)}${L.outputBytes && budget > L.outputBytes ? '（协议上限 ' + fmt(L.outputBytes) + '，以协议为准）' : ''}；超了会自动抽帧，抽不下去就被屏幕拒绝`],
    ['输出格式', `严格 ${screen}、每帧完整不透明、disposal=1（否则切回按键页会黑屏）`],
    ['S1 剩余空间', `屏幕外置 Flash 还要放原厂素材；被拒时选更小的上限，或在 WOB 官方驱动里删掉不用的图片`],
  ];
  box.replaceChildren();
  const title = document.createElement('strong');
  title.textContent = 'GIF 规格与体积（S1 槽位）';
  box.append(title);
  for (const [k, v] of rows) {
    const div = document.createElement('div');
    const b = document.createElement('b');
    b.textContent = k + '：';
    div.append(b, document.createTextNode(v));
    box.append(div);
  }
}
function renderFit(info, bytes, over) {
  const el = $('fit-info');
  el.classList.toggle('over', Boolean(over));
  if (info && info.source) {
    const cropped = info.cropped ? ` → 去底裁切 ${info.cropped[0]}×${info.cropped[1]}` : '';
    el.textContent = `GIF ${info.source[0]}×${info.source[1]} · ${info.frames} 帧${cropped} → 等比适配 ${info.fitted[0]}×${info.fitted[1]}（角色区 ${info.box[2] - info.box[0]}×${info.box[3] - info.box[1]}）· 输出 ${fmt(bytes)}${over ? ' · 超出 4 MiB 上限！' : ''}`;
  } else {
    el.textContent = `当前 S1 输出 ${fmt(S.gifBytes)} · ${(S.limits?.screen || [320, 172]).join('×')} · ${S.character.frameCount || 8} 帧`;
  }
}
function renderPalettes(list) {
  const box = $('palette-box');
  box.replaceChildren();
  if (!list || !list.length) {
    const empty = document.createElement('span');
    empty.className = 'empty';
    empty.textContent = '上传 GIF 后点上方按钮，这里会出现自动生成的配色方案。';
    box.append(empty);
    return;
  }
  for (const p of list) {
    const card = document.createElement('div');
    card.className = 'palette-card';
    const name = document.createElement('strong');
    name.textContent = p.name;
    const swatches = document.createElement('div');
    swatches.className = 'swatches';
    for (const c of (p.swatches || [])) {
      const chip = document.createElement('span');
      chip.className = 'swatch';
      chip.style.background = c;
      chip.title = c;
      swatches.append(chip);
    }
    card.append(name, swatches);
    card.onclick = () => {
      for (const [k] of COLOR_FIELDS) {
        const input = $('#color-' + k);
        if (p.colors && p.colors[k]) {
          input.value = p.colors[k];
          input.dispatchEvent(new Event('input'));
        }
      }
      log('已套用自动配色：' + p.name, 'ok');
    };
    box.append(card);
  }
}
function renderBuildInfo() {
  const m = S.manifest || {}, dl = $('build-info'); dl.replaceChildren();
  const rows = [
    ['当前主题', `${(S.themes[S.themeId] || {}).name || S.themeId} (${S.themeId})`],
    ['屏幕固件', m.uiVersion ? `UI ${m.uiVersion} / ${m.protocol}` : '未编译'],
    ['固件 SHA-256', (m.sha256 || '—').slice(0, 24) + '…'],
    ['S1 动画大小', S.gifBytes ? (S.gifBytes / 1024).toFixed(1) + ' KiB' : '—'],
    ['角色素材', S.sourceGif ? `${S.gifFrames} 帧 GIF 原动画 · ${S.character.name || '—'}` : `${S.sprites.length} 个视角 · ${S.character.name || '—'}`],
    ['编译工具链', S.clang ? '便携 clang 就绪' : '未找到 clang'],
    ['原厂输入', S.stockReady ? 'inputs/ips-stock.bin 就绪' : '缺失'],
  ];
  for (const [k, v] of rows) {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = k; dd.textContent = v; dl.append(dt, dd);
  }
  $('gif-link').href = S.gifUrl;
}
const SB_RIGHT_LIMIT = 3;
const SB_LABELS = { conn: '连接方式', caps: '大小写', battery: '电量',
  speed: '打字速率（每分钟按键数）', keys: '按键累计次数',
  rate: '回报率', debounce: '防抖' };
let sbRight = [];
function renderSbRight() {
  const list = $('#sb-right-list'), pool = $('#sb-right-pool');
  if (!list || !pool) return;
  // Any change to the right-hand module list must show up in the live preview
  // immediately; otherwise the preview keeps the previous widget set and the
  // new module looks "broken" (no data).
  if (S) scheduleIconPreview();
  list.innerHTML = sbRight.length ? sbRight.map((id, i) => `
    <span class="sb-chip">
      <b>${i + 1}</b>${SB_LABELS[id] || id}
      <button data-sb-up="${i}" ${i === 0 ? 'disabled' : ''}>↑</button>
      <button data-sb-down="${i}" ${i === sbRight.length - 1 ? 'disabled' : ''}>↓</button>
      <button data-sb-del="${i}">✕</button>
    </span>`).join('') : '<span class="muted">还没有选任何项目</span>';
  const left = Object.keys(SB_LABELS).filter(id => !sbRight.includes(id));
  pool.innerHTML = left.map(id => `<button data-sb-add="${id}" ${sbRight.length >= SB_RIGHT_LIMIT ? 'disabled' : ''}>+ ${SB_LABELS[id]}</button>`).join('');
  for (const b of list.querySelectorAll('[data-sb-up]')) b.onclick = () => {
    const i = Number(b.dataset.sbUp); [sbRight[i - 1], sbRight[i]] = [sbRight[i], sbRight[i - 1]]; renderSbRight();
  };
  for (const b of list.querySelectorAll('[data-sb-down]')) b.onclick = () => {
    const i = Number(b.dataset.sbDown); [sbRight[i + 1], sbRight[i]] = [sbRight[i], sbRight[i + 1]]; renderSbRight();
  };
  for (const b of list.querySelectorAll('[data-sb-del]')) b.onclick = () => {
    sbRight.splice(Number(b.dataset.sbDel), 1); renderSbRight();
  };
  for (const b of pool.querySelectorAll('[data-sb-add]')) b.onclick = () => {
    sbRight.push(b.dataset.sbAdd); renderSbRight();
  };
}
function readStatusbarForm() {
  const kind = document.querySelector('input[name="sb-left"]:checked')?.value || 'time';
  const right = sbRight.slice();
  return {
    left: { type: kind, text: $('#sb-text').value.trim() },
    right,
    values: { rate: $('#sb-rate').value.trim() || '--', debounce: $('#sb-debounce').value.trim() || '--' },
  };
}
function writeStatusbarForm(cfg) {
  cfg = cfg || {};
  const left = cfg.left || {};
  for (const el of document.querySelectorAll('input[name="sb-left"]')) el.checked = el.value === (left.type || 'time');
  $('#sb-text').value = left.text || '';
  sbRight = (cfg.right || []).filter(id => SB_LABELS[id]).slice(0, SB_RIGHT_LIMIT);
  renderSbRight();
  $('#sb-rate').value = (cfg.values || {}).rate && (cfg.values || {}).rate !== '--' ? cfg.values.rate : '';
  $('#sb-debounce').value = (cfg.values || {}).debounce && (cfg.values || {}).debounce !== '--' ? cfg.values.debounce : '';
}
// 20 wide x 14 tall - the largest icon the repaint band can show.
// Fallbacks only; /api/state supplies the authoritative presets from tools/assets.py.
const ICON_PRESETS_FALLBACK = {
  rice: [
    '00000011111111100000',
    '00001101001000111000',
    '00010100000010001100',
    '00010010001001000100',
    '00100000100000010010',
    '00111111111111111110',
    '00111111111111111110',
    '00111111111111111110',
    '00111111111101101110',
    '00011111111101001100',
    '00011111111011011100',
    '00001111111011111000',
    '00000111111111110000',
    '00000001111111100000',
  ],
  book: [
    '01111111000111111100',
    '10000000101000000010',
    '10111110010011111010',
    '10000000010000000010',
    '10000000010000000010',
    '10111110010011111010',
    '10000000010000000010',
    '10000000010000000010',
    '10111110010011111010',
    '10000000010000000010',
    '11111111010111111110',
    '10000000111000000010',
    '01111110010011111100',
    '00000001111100000000',
  ],
  blank: Array.from({ length: 14 }, () => '0'.repeat(20)),
};
let iconPresets = ICON_PRESETS_FALLBACK;
let activePreset = 'rice';
let riceRows = iconPresets.rice.slice();
let riceColor = '#a35479';
// true = keep following the theme ink; false = user picked a fixed colour.
let riceColorFollowsTheme = true;
function themeInk() {
  try { return ($('#color-ink') && $('#color-ink').value) || riceColor; } catch { return riceColor; }
}
function applyEditorColor() {
  if (riceColorFollowsTheme) riceColor = themeInk();
  const box = $('#sb-icon-editor');
  if (box) box.style.setProperty('--px-on', riceColor);
  const size = $('#sb-icon-size');
  if (size) size.textContent = `${riceRows[0].length} × ${riceRows.length}`;
}
let ricePainting = false;
function markIconPreset(key) {
  activePreset = key;
  for (const b of document.querySelectorAll('[data-icon-preset]')) b.classList.toggle('active', b.dataset.iconPreset === key);
}
function setIconPattern(key) {
  if (key === 'custom') {
    markIconPreset('custom');
    $('#sb-status').textContent = '自定义图案：在下方点格子画/擦；全部擦掉即为空白图标';
    return;
  }
  const rows = iconPresets[key];
  if (!rows || !rows.length) return;
  riceRows = rows.map(r => r.slice());
  markIconPreset(key);
  renderRiceEditor();
  applyEditorColor();
  scheduleIconPreview();
  const names = { rice: '米饭', book: '书本', blank: '空白' };
  $('#sb-status').textContent = `已选「${names[key] || key}」图案，点「保存状态栏」后再重新编译写入固件`;
}
function renderIconPresetButtons() {
  const box = $('#sb-icon-presets');
  if (!box) return;
  for (const b of box.querySelectorAll('[data-icon-preset]')) b.onclick = () => setIconPattern(b.dataset.iconPreset);
  markIconPreset(activePreset);
}
function renderRiceEditor() {
  const box = $('#sb-icon-editor');
  if (!box) return;
  applyEditorColor();
  box.style.gridTemplateColumns = `repeat(${riceRows[0].length}, 22px)`;
  box.replaceChildren();
  riceRows.forEach((row, y) => {
    [...row].forEach((cell, x) => {
      const c = document.createElement('span');
      c.className = cell === '1' ? 'px on' : 'px';
      c.dataset.x = String(x); c.dataset.y = String(y);
      box.append(c);
    });
  });
  // Event delegation: the element under the pointer is the one we recolour, so
  // no selector lookup is involved (the old getElementById call always missed).
  if (!box.dataset.wired) {
    box.dataset.wired = '1';
    box.addEventListener('mousedown', e => {
      const t = e.target && e.target.closest ? e.target.closest('.px') : null;
      if (!t) return;
      e.preventDefault();
      ricePainting = true;
      paintCell(Number(t.dataset.x), Number(t.dataset.y), t);
    });
    box.addEventListener('mouseover', e => {
      if (!ricePainting) return;
      const t = e.target && e.target.closest ? e.target.closest('.px') : null;
      if (t) paintCell(Number(t.dataset.x), Number(t.dataset.y), t);
    });
  }
}
function riceRowsHex() {
  const bits = riceRows.join('');
  let hex = '';
  for (let i = 0; i < bits.length; i += 4) hex += parseInt(bits.slice(i, i + 4).padEnd(4, '0'), 2).toString(16);
  return `${riceRows[0].length}x${riceRows.length}:${hex}`;
}
// One preview path for everything: the icon currently painted in the editor
// is sent with each preview so the POST render never overwrites it with the
// last saved icon.
let iconPreviewTimer = null;
function scheduleIconPreview() {
  // Paint feedback must feel immediate; 320 ms was tuned for colour inputs.
  clearTimeout(iconPreviewTimer);
  iconPreviewTimer = setTimeout(() => { refreshPreview(); }, 60);
}
function paintCell(x, y, node) {
  const row = riceRows[y];
  if (!row || x < 0 || x >= row.length) return;
  const next = row[x] === '1' ? '0' : '1';
  riceRows[y] = row.slice(0, x) + next + row.slice(x + 1);
  const el = node || $$(`#sb-icon-editor .px[data-x="${x}"][data-y="${y}"]`);
  if (el) el.className = next === '1' ? 'px on' : 'px';
  markIconPreset('custom');
  scheduleIconPreview();
}
document.addEventListener('mouseup', () => { ricePainting = false; });
$('#sb-icon-clear').onclick = async () => {
  // Update the editor and the live preview immediately; the server clear only
  // removes the saved override so a future reload sees the default too.
  riceRows = (iconPresets.rice || ICON_PRESETS_FALLBACK.rice).map(r => r.slice());
  markIconPreset('rice');
  renderRiceEditor();
  applyEditorColor();
  scheduleIconPreview();
  try {
    const r = await api('/api/left-icon', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                           body: JSON.stringify({ clear: true }) });
    if (r.status !== 200 || !r.data.ok) throw Error(r.data.error || ('HTTP ' + r.status));
    log('已恢复默认米饭图标', 'ok');
    $('#sb-status').textContent = '已恢复默认图标（点「保存状态栏」后写入固件）';
  } catch (e) { log('恢复失败：' + e.message, 'err'); }
};

function renderForm() {
  const c = S.character || DEFAULT_CHAR;
  $('#theme-id').value = S.themeId;
  $('#theme-name').value = (S.themes[S.themeId] || {}).name || S.themeId;
  $('#char-name').value = c.name || '自定义角色';
  $('#scale').value = c.scale ?? 1.0;
  $('#offsetY').value = c.offsetY ?? 0;
  $('#duration').value = c.duration ?? 160;
  $('#shadow').checked = c.shadow !== false;
  $('#remove-bg').checked = c.removeBg !== false;
  $('#sequence').value = seqKey(c.sequence || SEQ.turn, S.sprites.length);
  const sel = $('#motion-style');
  if (c.sourceGif) {
    let opt = sel.querySelector('option[value="gif"]');
    if (!opt) {
      opt = document.createElement('option');
      opt.value = 'gif';
      opt.textContent = '使用上传 GIF 的原动画（逐帧播放）';
      sel.append(opt);
    }
    sel.value = 'gif';
  } else {
    const stale = sel.querySelector('option[value="gif"]');
    if (stale) stale.remove();
    const lively = Boolean((c.motion || {}).enabled);
    const allFront = (c.sequence || SEQ.turn).every(v => v === 0);
    sel.value = lively ? 'lively' : (allFront ? 'idle' : 'turn');
  }
  syncMotionUI();
  $('#scale-out').textContent = Number($('#scale').value).toFixed(2) + '×';
  $('#offset-out').textContent = $('#offsetY').value + ' px';
  $('#duration-out').textContent = $('#duration').value + ' ms';
  renderColors(); renderPresets(); renderSprites(); renderBuildInfo();
  const card = $('stock-card');
  if (card) card.hidden = Boolean(S.stockReady);
  const line = $('status-line');
  const ok = S.sprites.length && S.clang && S.stockReady;
  line.classList.toggle('bad', !ok);
  const art = S.sourceGif ? `${S.gifFrames} 帧 GIF 原动画` : `${S.sprites.length} 个角色视角`;
  const missing = [];
  if (!S.sprites.length) missing.push('角色素材');
  if (!S.stockReady) missing.push('原厂屏幕固件（见上方 ⓪ 导入）');
  if (!S.clang) missing.push('便携 clang（主题编译需要）');
  line.textContent = ok
    ? `已连接 · 当前 ${(S.themes[S.themeId] || {}).name || S.themeId} · ${art} · 工具链就绪`
    : `已连接，但无法编译：缺少 ${missing.join(' / ')}。预览与导入功能仍可用`;
  renderLimits();
  renderLoopInfo();
  renderFit(null, S.gifBytes, S.gifBytes > (S.limits?.outputBytes || Infinity));
  updateDirty(); schedulePreview();
}

async function refreshPreview() {
  if (!S) return;
  try {
    const r = await api('/api/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ colors: collectColors(), character: collectCharacter(),
                             icon: riceRowsHex(),
                             color: riceColorFollowsTheme ? null : riceColor,
                             statusbar: readStatusbarForm() }),
    });
    if (r.status !== 200) {
      const e = r.data || {}; log('预览生成失败：' + (e.error || r.status), 'err'); return;
    }
    const url = URL.createObjectURL(r.blob), img = $('live-preview');
    if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
    img.src = url; img.dataset.url = url;
  } catch (e) { log('预览请求失败：' + e.message, 'err'); }
}
// One place that states exactly what ended up on the screen's animation slot.
function logAnimationSummary() {
  if (!S) return;
  const frames = S.gifFrames || 0, per = S.character?.duration || 0, bytes = S.gifBytes || 0;
  if (!frames || !bytes) return;
  const budget = S.s1Budget || 0;
  const secs = (frames * per / 1000).toFixed(2);
  const pct = budget ? Math.round(bytes / budget * 100) : 0;
  log(`本次动画：${frames} 帧 × ${per} ms = ${secs} s 循环 · ${(bytes / 1024).toFixed(0)} KB`
    + ` · 约 ${Math.ceil(bytes / 232)} 个数据包`
    + (budget ? ` · 占「${(budget / 1024).toFixed(0)} KB」上限的 ${pct}%` : ''), 'ok');
  if (budget && bytes > budget * 0.9) log('已接近体积上限：如果屏幕报 BEGIN 状态 4，请在 ① 里把「动画体积上限」降一档，或减少帧数/加长每帧时长', 'err');
}

function schedulePreview() {
  clearTimeout(timer); timer = setTimeout(refreshPreview, 320);
}

async function loadState() {
  const r = await api('/api/state');
  if (r.status !== 200) { $('status-line').classList.add('bad'); $('status-line').textContent = '无法读取本机配置：' + (r.data || {}).error; return; }
  S = r.data;
  S.character = { ...DEFAULT_CHAR, ...(S.character || {}) };
  if (S.iconPresets && S.iconPresets.rice && S.iconPresets.rice.length) {
    iconPresets = { ...ICON_PRESETS_FALLBACK, ...S.iconPresets };
  }
  renderIconPresetButtons();
  writeStatusbarForm(S.statusbar || {});
  if (S.leftIcon && S.leftIcon.rows && S.leftIcon.rows.length) {
    // Older saved icons may be wider/taller than the band allows; crop them so
    // the editor grid always matches what the screen can show.
    const rows = S.leftIcon.rows.slice(0, 14);
    const w = Math.min(20, Math.min(...rows.map(r => r.length)));
    riceRows = rows.map(r => r.slice(0, w));
    const match = Object.keys(iconPresets).find(k =>
      JSON.stringify(iconPresets[k]) === JSON.stringify(riceRows));
    markIconPreset(match || 'custom');
  }
  const savedColor = (S.leftIcon && S.leftIcon.color) || '';
  riceColorFollowsTheme = !/^#[0-9a-f]{6}$/i.test(savedColor);
  riceColor = riceColorFollowsTheme ? themeInk() : savedColor;
  if ($('#sb-icon-color')) $('#sb-icon-color').value = riceColor;
  renderRiceEditor();
  setBusy(false); renderForm();
}

async function upload(file) {
  if (!file) return;
  if (!file.type.startsWith('image/')) { log('请选择图片文件', 'err'); return; }
  log('正在处理 ' + file.name + '（拆分视角 / 去除白底）…');
  const dataUrl = await new Promise((resolve, reject) => {
    const fr = new FileReader(); fr.onload = () => resolve(fr.result); fr.onerror = () => reject(fr.error); fr.readAsDataURL(file);
  });
  try {
    const r = await api('/api/upload', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: dataUrl, split: $('#split').checked,
                             name: $('#char-name').value, removeBg: $('#remove-bg').checked,
                             budgetBytes: Number($('#s1-budget')?.value) || undefined }),
    });
    if (!r.data || !r.data.ok) throw Error((r.data || {}).error || '上传失败');
    const d = r.data;
    S = d.state; S.character = { ...DEFAULT_CHAR, ...(S.character || {}) };
    writeStatusbarForm(S.statusbar || {});
    log(d.gifFrames
      ? (d.sampled
          ? `已导入 ${d.gifFrames} 帧（源 ${d.sourceFrames} 帧，因输出超过 4 MiB 或超过安全上限而自动抽帧）`
          : `已导入 ${d.gifFrames} 帧 GIF 原动画 · 全部帧完整保留，未抽帧`)
      : `已识别 ${d.views} 个视角并写入 local/views/（未改动仓库源码）`, 'ok');
    if (d.warning) log('⚠ ' + d.warning, 'err');
    if (d.buildLog) log(d.buildLog.slice(-700));
    if (d.compiled) {
      log('IPS 固件已自动重新编译：刷屏幕固件 + 上传 S1 后即可直接显示', 'ok');
    } else if (d.gifFrames) {
      log('固件未重编，已仅生成 S1 素材；请点「应用并重新编译 IPS 固件」', 'err');
    }
    if (d.timing) {
      log(`速度换算：原 GIF ${d.timing.sourceFrames} 帧 / ${(d.timing.totalMs / 1000).toFixed(2)} 秒 → 输出 ${d.timing.outputFrames} 帧，每帧 ${S.character.duration} ms，循环 ${(d.loopMs / 1000).toFixed(2)} 秒`, 'ok');
      if (d.speedClamped) log('单帧时长被限制在 60~600 ms，总时长与原 GIF 略有差异，可用「每帧时长」滑块微调', 'err');
    }
    if (d.gifFrames) log(d.removeBg ? '已按「保守去白底」处理：仅去除与边缘相连的中性亮白，角色自带白色保留' : '已保留 GIF 全部原始像素（含白底）', 'ok');
    if (d.overLimit) log('警告：输出 GIF 超过 4 MiB 上限，请减少帧数或缩小画面', 'err');
    renderForm();
    if (d.fitted) renderFit(d.fitted, d.outputBytes, d.overLimit);
    if (d.palettes) {
      renderPalettes(d.palettes);
      log(`已根据 GIF 主色生成 ${d.palettes.length} 套配色，点色卡可一键套用`, 'ok');
    }
  } catch (e) { log('图片处理失败：' + e.message, 'err'); }
}

async function apply(compile) {
  if (busy || !S.sprites.length) return;
  const payload = {
    themeId: $('#theme-id').value.trim(), themeName: $('#theme-name').value.trim() || $('#theme-id').value.trim(),
    colors: collectColors(), character: collectCharacter(), compile,
  };
  setBusy(true);
  log(compile ? '正在写入主题与角色配置并重新编译 IPS 固件（约 10~30 秒）…' : '正在重新生成 S1 动画素材…');
  try {
    const r = await api('/api/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = r.data || {};
    if (d.log) log(d.log);
    if (!d.ok) { log('失败：' + (d.error || '未知错误'), 'err'); if (d.trace) log(d.trace, 'err'); }
    else {
      log(compile ? '完成：新 IPS 固件与配套 GIF 已生成，请到刷机向导重刷屏幕并上传 S1' : '完成：新 GIF 已生成，只需在刷机向导重新上传 S1', 'ok');
      await loadState();
      logAnimationSummary();
      renderFirmware();
    }
  } catch (e) { log('请求失败：' + e.message, 'err'); }
  finally { setBusy(false); updateDirty(); }
}

for (const [id, out, suffix] of [['scale', 'scale-out', '×'], ['offsetY', 'offset-out', ' px'], ['duration', 'duration-out', ' ms']]) {
  $(id).oninput = () => {
    $(out).textContent = (id === 'scale' ? Number($(id).value).toFixed(2) : $(id).value) + suffix;
    schedulePreview();
    if (id === 'duration') renderLoopInfo();
  };
}
for (const id of ['sequence', 'shadow', 'theme-id', 'theme-name', 'char-name']) {
  $(id).oninput = () => { if (id === 'theme-id' || id === 'theme-name' || id === 'char-name') updateDirty(); schedulePreview(); };
}
$('#motion-style').onchange = () => { syncMotionUI(); schedulePreview(); };
$('#remove-bg').onchange = () => {
  if (!S || !S.sourceGif) { log('去白底设置将在下次上传 GIF 时生效'); return; }
  log('去白底设置已改变，正在重新生成 S1 素材…');
  apply(false);
};
$('#extract-palette').onclick = async () => {
  try {
    const r = await api('/api/palette', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    if (!r.data || !r.data.ok) throw Error((r.data || {}).error || '提取失败');
    renderPalettes(r.data.palettes);
    log(`已根据 GIF 主色生成 ${r.data.palettes.length} 套配色，点色卡可一键套用`, 'ok');
  } catch (e) { log('配色提取失败：' + e.message, 'err'); }
};
// Reference materials are NOT embedded: the thumbnails only show what the two
// recommended GIFs look like. Dragging a card into the drop box asks the user
// to pick their own local copy through the same file input as a normal upload.
const MATERIAL_NAMES = { claude: 'claude.gif', deepseek: 'deepseek.gif' };
function pickMaterial(key) {
  const name = MATERIAL_NAMES[key] || '角色 GIF';
  log(`已把 ${name} 放进选择框：素材不内置，请从本机选择同名文件`);
  $('#file').click();
}
for (const card of document.querySelectorAll('[data-material]')) {
  card.addEventListener('dragstart', e => {
    e.dataTransfer.setData('text/plain', 'studio-material:' + card.dataset.material);
    e.dataTransfer.effectAllowed = 'copy';
  });
  card.addEventListener('click', () => pickMaterial(card.dataset.material));
}
$('#drop').onclick = () => $('#file').click();
$('#file').onchange = e => upload(e.target.files[0]);
$('#drop').ondragover = e => { e.preventDefault(); $('#drop').classList.add('over'); };
$('#drop').ondragleave = () => $('#drop').classList.remove('over');
$('#drop').ondrop = e => {
  e.preventDefault(); $('#drop').classList.remove('over');
  if (e.dataTransfer.files && e.dataTransfer.files.length) return upload(e.dataTransfer.files[0]);
  const hint = e.dataTransfer.getData('text/plain') || '';
  if (hint.startsWith('studio-material:')) return pickMaterial(hint.slice('studio-material:'.length));
};
// Switching the left-slot mode must refresh the preview immediately; before
// this the radios were bound to a no-op so only a save+recompile showed it.
for (const el of document.querySelectorAll('input[name="sb-left"]')) {
  el.onchange = () => {
    schedulePreview();
    $('#sb-status').textContent = '模式已切换，点「保存状态栏」后再重新编译写入固件';
  };
}
$('#sb-text').oninput = () => { schedulePreview(); $('#sb-status').textContent = '文字已改，点「保存状态栏」后再重新编译写入固件'; };
$('#sb-icon-color').oninput = () => {
  riceColor = $('#sb-icon-color').value;
  riceColorFollowsTheme = false;
  applyEditorColor();
  scheduleIconPreview();
  $('#sb-status').textContent = '图标颜色已改，点「保存状态栏」后再重新编译写入固件';
};
$('#sb-icon-color-reset').onclick = () => {
  // Follow the theme again: clear the saved custom colour and pick up the
  // current "ink" swatch so the icon matches the rest of the UI.
  riceColorFollowsTheme = true;
  riceColor = themeInk();
  $('#sb-icon-color').value = riceColor;
  applyEditorColor();
  scheduleIconPreview();
  $('#sb-status').textContent = '已改回主题色（保存后生效）';
};
$('#sb-save').onclick = async () => {
  const cfg = readStatusbarForm();
  $('#sb-save').disabled = true;
  try {
    const r = await api('/api/statusbar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ ...cfg, icon: riceRows,
                                                  color: riceColorFollowsTheme ? '' : riceColor }) });
    if (r.status !== 200 || !r.data.ok) throw Error(r.data.error || ('HTTP ' + r.status));
    S.statusbar = r.data.statusbar;
    writeStatusbarForm(S.statusbar);
    $('#sb-status').textContent = r.data.log || '已保存';
    log(r.data.log || '状态栏已保存', 'ok');
  } catch (e) {
    $('#sb-status').textContent = e.message;
    log('状态栏保存失败：' + e.message, 'err');
  } finally { $('#sb-save').disabled = false; }
};
// Firmware locations: list the built binaries and open their folders.
function fmtBytes(n) {
  return n >= 1024 * 1024 ? (n / 1048576).toFixed(2) + ' MB' : (n / 1024).toFixed(0) + ' KB';
}
async function renderFirmware() {
  const box = $('#fw-list');
  if (!box) return;
  try {
    const r = await fetch('/api/firmware-info', {cache: 'no-store'});
    const d = await r.json();
    const labels = {app: '应用目录（新固件默认位置）', screen: '屏幕固件（build/ 同步源）',
                    main: '主控固件', snapshot: '内置快照（刷机向导默认用）'};
    box.innerHTML = Object.entries(d.targets).map(([k, t]) => {
      if (!t.exists) return `<div class="fw-row"><b>${labels[k]}</b><span class="muted">尚未生成</span></div>`;
      const files = t.files.map(f => `${f.name} <span class="muted">${fmtBytes(f.bytes)}</span>`).join(' · ');
      return `<div class="fw-row"><b>${labels[k]}</b><code>${t.rel}</code><span class="fw-files">${files}</span></div>`;
    }).join('');
  } catch (e) { box.textContent = '读取失败：' + e.message; }
}
async function revealFirmware(target) {
  try {
    const r = await api('/api/reveal', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                        body: JSON.stringify({target})});
    if (r.status !== 200 || !r.data.ok) throw Error((r.data || {}).error || ('HTTP ' + r.status));
    log('已打开：' + r.data.path, 'ok');
  } catch (e) { log('打开文件夹失败：' + e.message, 'err'); }
}
$('#fw-open-app').onclick = () => revealFirmware('app');
$('#fw-open-screen').onclick = () => revealFirmware('screen');
$('#fw-open-main').onclick = () => revealFirmware('main');
$('#fw-open-snapshot').onclick = () => revealFirmware('snapshot');
$('#fw-refresh').onclick = renderFirmware;
renderFirmware();

$('#apply').onclick = () => apply(true);
$('#assets-only').onclick = () => apply(false);
$('#reset').onclick = async () => { log('已放弃未保存的改动，恢复上次应用/保存的配置'); await loadState(); };

// Import the user's own factory firmware. The public build deliberately ships
// without any WOB binaries, so this is the one-time setup step that makes
// "应用并重新编译" possible on a fresh machine.
async function importStock(target, file) {
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) { log('文件过大，原厂固件只有 300~500 KB', 'err'); return; }
  log(`正在读取 ${file.name}（${file.size} B）…`);
  const data = await new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(String(fr.result));
    fr.onerror = () => reject(fr.error || new Error('读取失败'));
    fr.readAsDataURL(file);
  });
  const r = await api('/api/stock', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target, data }),
  });
  if (r.status !== 200 || !r.data?.ok) { log('导入失败：' + (r.data?.error || r.status), 'err'); return; }
  log(r.data.log, 'ok');
  await loadState();
  log('已就绪，可以继续「应用并重新编译 IPS 固件」', 'ok');
}
$('#stock-ips').onchange = e => importStock('ips', e.target.files[0]);
$('#stock-main').onchange = e => importStock('main', e.target.files[0]);

// Remember the S1 size target; it is what keeps the animation small enough for
// the screen's free flash (a too-big file is refused with BEGIN status 4).
const budgetSel = $('#s1-budget');
if (budgetSel) {
  budgetSel.value = String(S?.s1Budget || 4 * 1024 * 1024);
  budgetSel.onchange = async () => {
    const r = await api('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ s1Budget: Number(budgetSel.value) }),
    });
    if (r.data?.ok) log(r.data.log, 'ok');
    else log('设置失败：' + (r.data?.error || r.status), 'err');
  };
}

await loadState();
renderPalettes(null);
