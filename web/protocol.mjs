// SPDX-License-Identifier: MIT
export const VID=0x36b0,APP_PID=0x3075,MAIN_CAP=0x4350,IPS_CAP=0x5536;
export const sum16=b=>b.reduce((s,v)=>(s+v)&65535,0);
export function frame(sub,a=0,b=0,c=0,payload=[]){
 const p=new Uint8Array(11+payload.length);if(p.length>255)throw Error('Packet too large');
 p.set([0xbe,0x1a,p.length,sub,a,b,c,0]);p.set(payload,8);const sum=sum16(p.subarray(3,p.length-3));p[p.length-3]=sum&255;p[p.length-2]=sum>>>8;p[p.length-1]=0xed;return p;
}
export const command=(op,id=0,payload=[])=>frame(13,op,id&255,id>>>8,payload);
export const ACK_READ=new Uint8Array([0xbe,0xe4,10,0x84,4,0,0,0x34,2,0xed]);
export function parseAck(p,{allowLegacy=true}={}){
 if(p.length<14||p[0]!==0xbe||p[1]!==0xe4||p[2]!==14||p[3]!==0x84||p[4]!==4||p[5]||p[6]||p[13]!==0xed)throw Error('ACK format mismatch');
 const got=p[11]|p[12]<<8,valid=got===sum16(p.subarray(0,11));
 if(!valid&&!(allowLegacy&&got===0x0357))throw Error('ACK checksum mismatch');
 return {sub:p[7],status:p[8],value:p[9]|p[10]<<8,legacyChecksum:!valid};
}
export function crc16(bytes){let crc=65535;for(const v of bytes){crc^=v<<8;for(let i=0;i<8;i++)crc=(crc&32768?crc<<1^0x1021:crc<<1)&65535;}return crc;}
export function localSeconds(ms=Date.now(),timeZone=Intl.DateTimeFormat().resolvedOptions().timeZone){const a=new Intl.DateTimeFormat('en-GB',{timeZone,hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(ms)).split(':').map(Number);return a[0]*3600+a[1]*60+a[2];}
export const timeDifference=(a,b)=>((a-b+129600)%86400)-43200;
export function decodeTime(raw){if(raw===0xffffffff)return null;const s=raw.toString(16).padStart(6,'0');if(!/^\d{6}$/.test(s))return null;const h=+s.slice(0,2),m=+s.slice(2,4),v=+s.slice(4,6);return h<24&&m<60&&v<60?{seconds:h*3600+m*60+v,text:`${s.slice(0,2)}:${s.slice(2,4)}:${s.slice(4,6)}`}:null;}
export function validateGif(bytes){
 const signature=new TextDecoder().decode(bytes.subarray(0,6));
 const isGif=['GIF87a','GIF89a'].includes(signature)&&bytes.length>=13;
 const w=isGif?bytes[6]|bytes[7]<<8:0,h=isGif?bytes[8]|bytes[9]<<8:0,mb=(bytes.length/1048576).toFixed(1);
 if(!isGif)throw Error('这不是 GIF 文件（'+mb+' MB）：请选 .gif，不要选视频或图片');
 if(w!==320||h!==172)throw Error(`GIF 尺寸是 ${w}×${h}，必须严格 320×172（${mb} MB）。原图请用「主题定制台」上传，它会自动裁切/缩放并按「动画体积上限」抽帧`);
 if(bytes.length>4*1024*1024)throw Error(`GIF 有 ${mb} MB，超过 4 MB 上限：到「主题定制台」把「动画体积上限」调到 256/512 KB 重新生成`);
}
// The screen's GIF decoder polls the UART for ACKs between frames. A source
// exported at 20-60 ms/frame starves that polling so the upload stalls; the
// diagnostic page's "降低动画负载" (150 ms) always works. Raise short frame
// delays to a safe minimum before ANY upload, preserving already slow frames.
export const S1_FRAME_MIN_MS=150;
export function screenSafeGif(bytes,minMs=S1_FRAME_MIN_MS){
 const b=new Uint8Array(bytes),delay=Math.round(minMs/10);let frames=0,raised=0;
 for(let i=0;i<b.length-7;i++){
  if(b[i]===0x21&&b[i+1]===0xF9&&b[i+2]===0x04&&b[i+7]===0x00){
   const cur=b[i+4]|(b[i+5]<<8);frames++;
   if(cur&&cur<delay){b[i+4]=delay&255;b[i+5]=(delay>>8)&255;raised++;}
   i+=7;
  }
 }
 return frames?{bytes:b,frames,raised}:null;
}
export async function sha256(bytes){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');}
export const TARGETS={main:{pid:0x3079,base:0x2000,bytes:294912,boot:[0xbe,0xfc,4,0xed]},ips:{pid:0x3078,base:0x4000,bytes:507904,boot:[0xbe,0xfc,5,0,0xed]}};
export async function validateBuild(bytes,m){
 const t=TARGETS[m?.target];
 if(m?.variant)throw Error('歌词版固件已从本项目移除，请使用基础版构建（不带 variant）');
 if(!t||m.format!=='rainy75v2-tft/build-v1'||m.applicationBase!==t.base||m.iapPid!==t.pid||bytes.length!==m.bytes||bytes.length!==t.bytes)throw Error('构建清单或目标不匹配');
 if(!/^[a-f0-9]{64}$/.test(m.sha256)||await sha256(bytes)!==m.sha256)throw Error('固件 SHA-256 不匹配，未擦除');
 // Screen images now extend past the factory tail into the second 32 KiB bank.
 if(t.flashKiB&&m.requiredFlashKiB&&m.requiredFlashKiB!==t.flashKiB)throw Error('构建清单声明的屏幕容量与本版不一致，未擦除');
 return {...t,target:m.target,bytes:new Uint8Array(bytes),sha256:m.sha256,
  hardwareChecked:!t.flashKiB};
}
