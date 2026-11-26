// SPDX-License-Identifier: MIT
import {VID,APP_PID,MAIN_CAP,IPS_CAP,ACK_READ,parseAck,command,frame,crc16,localSeconds,timeDifference,decodeTime,validateGif,TARGETS} from './protocol.mjs';
export const wait=ms=>new Promise(r=>setTimeout(r,ms));
export function reportLength(reports,length){return reports?.some(r=>r.reportId===0&&r.items.reduce((n,i)=>n+i.reportSize*i.reportCount,0)/8===length);}
export function validDevice(device,pid,length){return device?.vendorId===VID&&device.productId===pid&&device.collections?.some(c=>c.usagePage===0xff60&&c.usage===0x61&&reportLength(c.outputReports,length)&&reportLength(c.inputReports,length));}
export class HidIO{
 constructor(device,length){this.device=device;this.length=length;this.pending=false;}
 static async choose(pid,length){
  if(!globalThis.navigator?.hid)throw Error('请用支持 WebHID 的桌面 Chrome / Edge，并通过 localhost 或 HTTPS 打开');
  const filters=[{vendorId:VID,productId:pid,usagePage:0xff60,usage:0x61}];
  let d;
  // requestDevice() needs a fresh user gesture. Inside a multi-step action (or a
  // retry right after another step) that gesture is gone, so fall back to the
  // device the user already granted in this page session instead of throwing
  // "Must be handling a user gesture" and leaving the flow half done.
  try{
   const list=await navigator.hid.requestDevice({filters});
   d=list.find(x=>validDevice(x,pid,length));
  }catch(e){
   const granted=await navigator.hid.getDevices().catch(()=>[]);
   d=granted.find(x=>validDevice(x,pid,length));
   if(!d)throw e;
  }
  if(!d){
   const granted=await navigator.hid.getDevices().catch(()=>[]);
   d=granted.find(x=>validDevice(x,pid,length));
  }
  if(!d)throw Error('设备型号或 HID 描述符不匹配');
  if(!d.opened)await d.open();return new HidIO(d,length);
 }
 async send(bytes){if(bytes.length>this.length)throw Error('Report too large');const p=new Uint8Array(this.length);p.set(bytes);await this.device.sendReport(0,p);}
 async exchange(bytes,match,timeout=2500,minLength=this.length){
  if(this.pending)throw Error('Another exchange is pending');this.pending=true;let handler,timer;
  try{
   const reply=new Promise((resolve,reject)=>{
    handler=e=>{if(e.reportId!==0||e.data.byteLength<minLength||e.data.byteLength>this.length)return;const p=new Uint8Array(e.data.buffer,e.data.byteOffset,e.data.byteLength);if(match(p))resolve(new Uint8Array(p));};
    this.device.addEventListener('inputreport',handler);timer=setTimeout(()=>reject(Error('设备应答超时')),timeout);
   });
   const [,result]=await Promise.all([this.send(bytes),reply]);return result;
  }finally{clearTimeout(timer);if(handler)this.device.removeEventListener('inputreport',handler);this.pending=false;}
 }
 async close(){if(this.device.opened)await this.device.close();}
}
export class AppClient{
 constructor(io,{pause=wait,now=Date.now}={}){this.io=io;this.pause=pause;this.now=now;this.seq=Date.now()&65535;}
 static async connect(){return new AppClient(await HidIO.choose(APP_PID,256));}
 async close(){await this.io.close();}
 async ack(){return parseAck(await this.io.exchange(ACK_READ,p=>p[0]===0xbe&&p[1]===0xe4&&p[3]===0x84));}
 async sendAwait(packet,accept,timeout=8000,pollMs=15){
  await this.io.send(packet);const start=this.now();let last,err;
  while(this.now()-start<timeout){
   // A missed/short ACK is normal on a long upload; keep polling instead of
   // aborting the whole transfer. accept() errors still fail fast below.
   try{last=await this.ack();}catch(e){err=e;await this.pause(pollMs);continue;}
   if(accept(last))return last;
   await this.pause(pollMs);
  }
  throw Error('指令应答超时：'+JSON.stringify(last)+(err?' · 最后应答错误：'+err.message:''));
 }
 async request(op,id=0,payload=[],test=a=>a.status===1&&a.value===id,{pollMs=15}={}){
  if(!Number.isInteger(pollMs)||pollMs<2||pollMs>100)throw Error('无效查询间隔');
  return this.sendAwait(command(op,id,payload),a=>{
   if(a.sub!==13)return false;if(test(a))return true;
   if(a.value===id&&a.status>=2&&a.status<=7)throw Object.assign(Error('设备拒绝指令，状态 '+a.status),{status:a.status});return false;
  },8000,pollMs).catch(e=>{throw Object.assign(new Error('OP'+op+' / ID'+id+'：'+e.message),{status:e.status,cause:e});});
 }
 async queryMain(f){return (await this.request(15,f,[],a=>a.status===0xd0+f)).value;}
 async queryIps(f){return (await this.request(11,f,[],a=>a.status===0xb0+f)).value;}
 // Screen images that cross 0x08080000 only work on a 1024 KiB part; read the
 // chip size in APP mode and refuse before anything is erased.
 async probeIpsTarget(){
  if(await this.queryIps(0)!==IPS_CAP)throw Error('请先安装匹配的 L6 屏幕固件，再读取芯片容量');
  const flashKiB=await this.queryIps(14),series=await this.queryIps(15);
  if(flashKiB!==1024)throw Error(`屏幕片内 Flash 只有 ${flashKiB} KiB，本版固件需要 1024 KiB，未做任何擦除`);
  return {flashKiB,series};
 }
 async status(){
  const mainCap=await this.queryMain(9);if(mainCap!==MAIN_CAP)throw Error('主控不是支持的 V7.1，未进行写入');
  const ipsCap=await this.queryIps(0);if(ipsCap!==IPS_CAP)throw Error('屏幕不是支持的 L6，未进行写入');
  const valid=await this.queryMain(8),hi=await this.queryMain(7),lo=await this.queryMain(6),state=await this.queryIps(4),a=await this.queryIps(5),b=await this.queryIps(6),battery=await this.queryIps(2),mode=await this.queryIps(3),key=await this.queryIps(1),keyTotal=await this.queryIps(18);
  return {mainCap,ipsCap,valid:Boolean(valid),mainSeconds:(hi*65536+lo)>>>0,screenState:state,screenTime:decodeTime((b*65536+a)>>>0),battery:battery===65535?null:battery&255,mode,key,keyTotal};
 }
 async calibrate({timeZone=Intl.DateTimeFormat().resolvedOptions().timeZone,rate=32000}={}){
  if(!Number.isInteger(rate)||rate<30000||rate>40000)throw Error('无效的计时频率');
  await this.status();await this.pause(1005-this.now()%1000);const seconds=localSeconds(this.now(),timeZone),id=++this.seq&65535,p=new Uint8Array(8),v=new DataView(p.buffer);v.setUint32(0,seconds,true);v.setUint32(4,rate,true);
  try{await this.request(18,id,p);}catch(e){if(e.status===7)throw Error('主控校时写入校验未通过，请保留 USB 连接');throw e;}
  for(let i=0;i<35;i++){
   const s=await this.status(),now=localSeconds(this.now(),timeZone);
   if(s.valid&&s.screenState===0x402&&s.screenTime&&Math.abs(timeDifference(s.mainSeconds,now))<=2&&Math.abs(timeDifference(s.screenTime.seconds,now))<=2)return s;
   await this.pause(1000);
  }
  throw Error('校时指令已应答，但读回未通过核对（主控 '+s.mainSeconds+' / 屏幕 '+JSON.stringify(s.screenTime)+' / 屏幕状态 0x'+s.screenState.toString(16)+'）；请确认屏幕已刷入本版固件并保持 USB 连接');
 }
 async control(op){const id=++this.seq&65535;for(let i=0;;i++)try{return await this.request(op,id);}catch(e){if(e.status!==2||i>=30)throw e;await this.pause(50);}}
 async stock(sub,a=0,b=0,c=0,payload=[],timeout=8000){
  let rejects=0;
  return this.sendAwait(frame(sub,a,b,c,payload),ack=>{
   if(ack.sub!==sub)return false;
   if(ack.status===255){
    // 0xFF = 屏幕拒绝这次请求（不认槽位/文件表异常/仍在上一次写入的收尾阶段）。
    // A one-off 0xFF can be a transient poll answer, but a run of them means the
    // request was refused outright - fail fast instead of waiting out the timeout.
    if(sub===1&&++rejects>=6)throw Object.assign(Error(
     'BEGIN 被拒绝（状态 255）：屏幕不接受这次上传。常见原因是它的外置 Flash 里 S1 文件表还没整理好'+
     '（上一次写入被中断过），或同名文件残留。点「清理并重试」会先写 454 B 占位素材释放旧文件再重传'),{status:255});
    return false;
   }
   if(ack.status===2)return false; // device busy: keep polling, not a fatal error
   if(sub===1&&ack.status===4)throw Error('屏幕空间不足（BEGIN 状态 4）：这个动画比屏幕外置 Flash 的剩余空间大。到定制台把「动画体积上限」调到 256 KB 重新生成，或先用「上传精简版 S1」应急；也可以在 WOB 官方驱动删掉不用的图片/动画腾地方');
   if(sub===2&&ack.value!==(a|b<<8))return false;
   if(ack.status!==0&&!(sub===1&&ack.status===6))throw Object.assign(Error('素材指令返回状态 '+ack.status),{status:ack.status});return true;
  },timeout);
 }
 async upload(bytes,{replaceConfirmed=false,progress=()=>{},chunkTimeout=30000}={}){
  if(!replaceConfirmed)throw Error('请先确认覆盖素材槽位 S1');validateGif(bytes);
  if(await this.queryIps(0)!==IPS_CAP)throw Error('屏幕协议不匹配（设备可能仍是原厂固件，请先完成 ①~④ 烧录）');
  const crc=crc16(bytes),begin=new Uint8Array(17);begin.set(new TextEncoder().encode('S1      GIF'));new DataView(begin.buffer).setUint32(11,bytes.length,true);new DataView(begin.buffer).setUint16(15,crc,true);
  const total=Math.ceil(bytes.length/232);
  await this.control(2);let ok=false;
  try{
   await this.stock(1,0,0,0,begin,chunkTimeout);
   for(let offset=0,seq=0;offset<bytes.length;offset+=232,seq++){
    try{await this.stock(2,seq&255,seq>>>8,0,bytes.subarray(offset,offset+232),chunkTimeout);}
    catch(e){throw Error(`S1 数据第 ${seq+1}/${total} 包（偏移 ${offset} B）失败：${e.message}`);}
    progress(Math.min(1,(offset+232)/bytes.length));
   }
   await this.stock(3,0,0,0,[crc&255,crc>>>8],chunkTimeout);ok=true;
  }finally{if(!ok)try{await this.stock(4);}catch{}await this.control(5);}
 }
 async enterIap(target){const t=TARGETS[target];if(!t)throw Error('Unknown target');await this.io.send(new Uint8Array(t.boot));await this.close();}
}
export class FlashClient{
 constructor(io,plan,{pause=wait}={}){this.io=io;this.plan=plan;this.pause=pause;}
 static async connect(plan){return new FlashClient(await HidIO.choose(plan.pid,64),plan);}
 async ok(p,timeout=5000){const r=await this.io.exchange(p,()=>true,timeout,2);if(r.length<2||r[0]||r[1])throw Error('烧录应答失败：'+r[0]+','+r[1]);}
 async flash(progress=()=>{}){
  const {bytes,base,pid}=this.plan;if(!validDevice(this.io.device,pid,64))throw Error('目标错误，未擦除');
  if(this.plan.flashKiB&&!this.plan.hardwareChecked)throw Error('请先在 APP 模式读取并核对屏幕芯片容量（需要 1024 KiB），未擦除');
  const erase=new Uint8Array(6);erase[0]=0x81;new DataView(erase.buffer).setUint32(2,base,true);
  progress('擦除',0);
  try{await this.ok(erase,20000);}catch(e){throw Error('擦除阶段：'+e.message+'；设备可能仍在升级模式，未确认擦除结果。');}await this.pause(1200);
  for(let off=0;off<bytes.length;off+=62){const n=Math.min(62,bytes.length-off),p=new Uint8Array(n+2);p.set([0x80,n]);p.set(bytes.subarray(off,off+n),2);await this.ok(p);progress('写入',(off+n)/bytes.length);}
  await this.ok(new Uint8Array([0x80,0]));
  const verify=async off=>{const p=new Uint8Array(62);p.set([0x82,56]);new DataView(p.buffer).setUint32(2,base+off,true);p.set(bytes.subarray(off,off+56),6);await this.ok(p);};
  let off=0;for(;off+56<=bytes.length;off+=56){await verify(off);progress('校验',(off+56)/bytes.length);}if(off<bytes.length)await verify(bytes.length-56);
  await this.io.send(new Uint8Array([0x83,0]));await this.io.close().catch(()=>{});progress('完成',1);
 }
}
