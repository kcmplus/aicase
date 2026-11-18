// Loaded only by the local direct-debug server. LAN HTTP lacks randomUUID(),
// while getRandomValues remains available. Keep cryptographic randomness.
(()=>{
 if(!crypto.randomUUID)Object.defineProperty(crypto,'randomUUID',{value:()=>{
  const bytes=crypto.getRandomValues(new Uint8Array(16));
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=Array.from(bytes,n=>n.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
 }});
 addEventListener('DOMContentLoaded',()=>{
  const note=document.createElement('aside');
  note.textContent='直连调试 · 独立本地数据 · 0 元联调 · 打印和出货均为模拟';
  note.style.cssText='padding:8px 16px;background:#e6f1eb;color:#183e30;font:13px/1.5 system-ui;text-align:center';
  document.body.prepend(note);
 });
})();
