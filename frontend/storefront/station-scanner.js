import {scanScope,stationIdentity,scopeIds} from './fulfillment-service.js';

export function stationScanPrompt(lang='en-US'){
 const zh=lang==='zh-CN';
 return `<p>${zh?'请到打印机前，扫描机器屏幕上的设备二维码。':'Go to the printer and scan the station QR code on its screen.'}</p><button class="button primary full" data-action="scan-station">${zh?'扫描设备二维码':'Scan station QR code'}</button>`;
}

export function previewStationPanel(order,{station,scope='',lang='en-US'}={}){
 if(['courier','air'].includes(order?.fulfillmentType)||['cancelled','completed','collected'].includes(order?.status)||order?.refund&&order.refund.status!=='failed')return '';
 const zh=lang==='zh-CN',ids=scopeIds(scope);
 const selected=station&&ids&&station.device_id===ids.device_id&&station.shop_id===ids.shop_id;
 const notice=order?(zh?'这是演示／测试订单，没有实际收款，不能发送到真实设备打印。':'This is a demo/test order. No real payment was taken; it cannot be sent to a real printer.'):(zh?'设计已保存，请先确认订单并完成付款。':'Your design is saved. Confirm an order and complete payment first.');
 return `<section class="device-fulfillment"><h3>${zh?'打印设备':'Print station'}</h3>${selected?stationIdentity(station,{lang}):ids?`<p role="status">${zh?'正在使用链接中的设备，请刷新设备信息后继续。':'A station is specified in this link. Refresh its details to continue.'}</p><button class="text-button" data-action="refresh-device-info">${zh?'刷新设备信息':'Refresh station details'}</button>`:stationScanPrompt(lang)}<p class="field-note">${notice}</p></section>`;
}

// Keep the current order route and language; never navigate to the QR's arbitrary target.
export function stationScanDestination(value,currentUrl){
 const ids=scanScope(value,currentUrl),url=new URL(currentUrl);
 for(const [key,id] of Object.entries(ids))url.searchParams.set(key,id);
 return url.href;
}

// A late camera grant after the dialog closes must also release the camera.
export async function acquireStationCamera(mediaDevices,isClosed){
 const stream=await mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:1280}}});
 if(isClosed()){stream.getTracks().forEach(track=>track.stop());return null;}
 return stream;
}

let activeClose=null;
export function openStationScanner({lang='en-US',onScan}){
 activeClose?.();
 const zh=lang==='zh-CN',say=(en,cn)=>zh?cn:en;
 const dialog=document.createElement('dialog');dialog.className='station-scanner';
 dialog.setAttribute('aria-labelledby','station-scanner-title');
 dialog.innerHTML=`<div class="scanner-heading"><h2 id="station-scanner-title">${say('Scan station QR code','扫描设备二维码')}</h2><button type="button" class="text-button scanner-close">${say('Close','关闭')}</button></div><p>${say('Point your camera at the station QR code on the printer screen.','将镜头对准打印机屏幕上的设备二维码。')}</p><video muted autoplay playsinline></video><p class="scanner-status" role="status" aria-live="polite">${say('Opening camera…','正在打开相机…')}</p><button type="button" class="text-button scanner-retry" hidden>${say('Retry camera','重试打开相机')}</button><details><summary>${say('Cannot scan? Paste the station link','无法扫码？粘贴设备链接')}</summary><form><label>${say('Station QR link','设备二维码链接')}<input name="station_url" type="url" required autocomplete="off" placeholder="https://…/?device_id=…&shop_id=…"></label><button class="button secondary full" type="submit">${say('Use this station','使用此设备')}</button></form><p>${say('You can also scan with your phone’s Camera app and open the link in this browser.','也可以使用手机相机扫码，并在当前浏览器中打开链接。')}</p></details>`;
 const video=dialog.querySelector('video'),status=dialog.querySelector('.scanner-status'),retry=dialog.querySelector('.scanner-retry');
 let closed=false,stream=null,timer=null,processing=false,starting=false,lastCode='',lastScan=0;
 const controller=new AbortController();
 const stopCamera=()=>{clearTimeout(timer);stream?.getTracks().forEach(track=>track.stop());stream=null;video.srcObject=null;};
 const close=()=>{if(closed)return;closed=true;controller.abort();stopCamera();document.removeEventListener('visibilitychange',onVisibility);window.removeEventListener('pagehide',close);window.removeEventListener('hashchange',close);dialog.close();dialog.remove();if(activeClose===close)activeClose=null;};
 const onVisibility=()=>{if(document.hidden)close();};
 activeClose=close;
 const accept=async value=>{
  if(closed||processing)return;
  processing=true;status.textContent=say('Checking station…','正在核实设备…');
  try{const url=stationScanDestination(value,location.href);await onScan(url,{signal:controller.signal});close();}
  catch{if(!closed)status.textContent=say('This station could not be verified. Scan its POPOMO QR code or try again.','未能核实设备，请扫描机器上的 POPOMO 二维码或重试。');}
  finally{processing=false;}
 };
 const start=async()=>{
  if(closed||starting)return;starting=true;stopCamera();retry.hidden=true;video.hidden=false;
  try{
   if(!navigator.mediaDevices?.getUserMedia)throw Error('camera-unavailable');
   stream=await acquireStationCamera(navigator.mediaDevices,()=>closed);if(!stream)return;
   video.srcObject=stream;await video.play();
   const {default:decode}=await import('./vendor/jsqr.js');if(closed)return;
   const canvas=document.createElement('canvas'),context=canvas.getContext('2d',{willReadFrequently:true});
   if(!context)throw Error('canvas-unavailable');
   status.textContent=say('Keep the station QR code inside the camera view.','请将设备二维码保持在取景画面内。');
   const tick=async()=>{
    if(closed)return;
    try{if(!processing&&video.readyState>=2&&video.videoWidth){
     const scale=Math.min(1,640/video.videoWidth);canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
     context.drawImage(video,0,0,canvas.width,canvas.height);
     const frame=context.getImageData(0,0,canvas.width,canvas.height),code=decode(frame.data,frame.width,frame.height,{inversionAttempts:'attemptBoth'});
     if(code&&(code.data!==lastCode||Date.now()-lastScan>3000)){lastCode=code.data;lastScan=Date.now();await accept(code.data);}
    }}catch{stopCamera();video.hidden=true;status.textContent=say('Camera scanning stopped. Retry or paste the station link.','相机扫码已停止，请重试或粘贴设备链接。');retry.hidden=false;return;}
    if(!closed)timer=setTimeout(tick,250);
   };void tick();
  }catch{if(!closed){stopCamera();video.hidden=true;status.textContent=say('Camera unavailable. Allow camera access and retry, or use your phone camera / paste the station link.','无法打开相机，请允许相机权限后重试，也可使用手机相机扫码或粘贴设备链接。');retry.hidden=false;}}
  finally{starting=false;}
 };
 dialog.querySelector('.scanner-close').addEventListener('click',close);
 dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
 dialog.addEventListener('close',close);
 retry.addEventListener('click',()=>void start());
 dialog.querySelector('form').addEventListener('submit',event=>{event.preventDefault();void accept(new FormData(event.target).get('station_url'));});
 document.addEventListener('visibilitychange',onVisibility);window.addEventListener('pagehide',close);window.addEventListener('hashchange',close);
 document.body.append(dialog);dialog.showModal();void start();return close;
}
