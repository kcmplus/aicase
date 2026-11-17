import {brandLogo,esc,icon} from './art.js';
import {create as createQR} from './vendor/qr.js';
import {deviceInfoScope,loadDeviceInfo,scopedDesignUrl} from './device-info-service.js';

const root=document.querySelector('#device-app'),config=window.POPOMO_DEVICE_CONFIG||{};
const query=new URLSearchParams(location.search);
let lang=query.get('lang')==='zh-CN'?'zh-CN':'en-US',scope=null,data=null,busy=false,error='';
const say=(en,zh)=>lang==='zh-CN'?zh:en;
document.body.classList.add('device-info-page');
function time(value){const date=new Date(value);return value&&Number.isFinite(date.getTime())?date.toLocaleString(lang):say('Not yet synced','尚未同步');}
function qr(url){
 const modules=createQR(url,{errorCorrectionLevel:'M'}).modules,size=modules.size;let path='';
 for(let y=0;y<size;y++)for(let x=0;x<size;x++)if(modules.get(y,x))path+=`M${x+4} ${y+4}h1v1h-1z`;
 return `<svg viewBox="0 0 ${size+8} ${size+8}" role="img" aria-label="${say('Scan to design on your phone','扫码进入手机设计页')}"><rect width="100%" height="100%" fill="white"/><path d="${path}" fill="#243e34"/></svg>`;
}
function render(){
 document.documentElement.lang=lang;
 document.title='POPOMO · '+say('Device information','设备信息');
 const url=scope&&scopedDesignUrl(location.origin,config.storefrontUrl,scope,lang);
 const ready=data&&!error&&data.inventory.availability==='ready';
 const detailsOpen=root.querySelector('#station-details')?.open||false;
 root.innerHTML=`<header class="info-header">${brandLogo()}<span>${say('YOUR PHOTO. YOUR CASE.','你的照片，你的手机壳。')}</span><button data-action="language" aria-label="${say('Switch to Chinese','切换为英文')}">${lang==='zh-CN'?'English':'中文'}</button></header>
 <main class="info-main"><section class="info-scan" aria-label="${say('Scan to get started','扫码开始设计')}"><p class="info-eyebrow">${say('MAKE IT YOURS','做一个，属于你的。')}</p><h1>${say('Scan to create your case','手机扫码，选择照片')}</h1><p class="info-lead">${say('Choose a photo from your album. Make it your own.','用相册里的喜欢，设计你的专属手机壳。')}</p>
 ${ready&&url?`<div class="info-qr">${qr(url)}</div><p class="info-scan-hint">${icon('scan',20)}${say('Open your phone camera and scan','打开手机相机，扫描上方二维码')}</p>`:`<div class="info-qr-placeholder" role="status">${icon('scan',72)}<p>${esc(error==='invalid-device'?say('Please check the device link.','请检查设备链接。'):error==='device-unavailable'?say('This device is not available yet.','这台设备暂未开放。'):error?say('Unable to load. Please retry.','暂时无法加载，请重试。'):busy&&!data?say('Getting your QR code ready…','正在准备二维码…'):ready&&!url?say('Set a phone-accessible shop URL to preview the QR code.','配置手机可访问的地址后，即可预览二维码。'):data?.inventory.availability==='updating'?say('Updating available models. Please wait.','正在更新可选机型，请稍候。'):say('No available models yet. Please contact the operator.','暂无可选机型，请联系工作人员。'))}</p><button class="info-refresh" data-action="refresh" ${busy?'disabled':''}>${say(busy?'Refreshing…':'Try again',busy?'正在刷新…':'重新获取')}</button></div>`}
 <ol class="info-steps"><li><b>1</b>${say('Scan on your phone','手机扫码')}</li><li><b>2</b>${say('Choose your photo','选择照片')}</li><li><b>3</b>${say('Design your case','设计手机壳')}</li></ol>
 <p class="info-model-note">${ready?`${data.models.length} ${say('phone models · Choose yours after scanning','款机型可选 · 扫码后选择你的型号')}`:say('Available models are shown on your phone.','可选机型将在手机端展示。')}</p></section>
 <details id="station-details" class="info-details-panel" ${detailsOpen?'open':''}><summary><span>${esc(data?.name||say('This print station','当前打印设备'))}${scope?' · '+esc(scope.deviceId):''}</span><span>${say('Device information','设备信息')} <i aria-hidden="true">⌄</i></span></summary><div class="info-details-content"><dl class="info-details"><div><dt>${say('Location','设备位置')}</dt><dd>${esc(data?.location||say('Location not provided','位置暂未填写'))}</dd></div><div><dt>${say('Device number','设备编号')}</dt><dd>${esc(data?.number||'—')}</dd></div><div><dt>${say('Connection status','设备在线状态')}</dt><dd>${say('Unconfirmed','待确认')}</dd></div><div><dt>${say('Print setting','设备打印配置')}</dt><dd>${esc(data?.print_type||say('Not provided','未提供'))}</dd></div><div><dt>${say('Currency','设备币种')}</dt><dd>${esc(data?.currency||say('Not provided','未提供'))}</dd></div><div><dt>${say('Information updated','信息更新时间')}</dt><dd>${esc(time(data?.info_updated_at))}</dd></div></dl><button class="info-refresh" data-action="refresh" ${busy?'disabled':''}>${say(busy?'Refreshing…':'Refresh information',busy?'正在刷新…':'刷新设备信息')}</button>${ready?`<div class="info-models">${data.models.map(model=>`<span>${esc(model.name)}</span>`).join('')}</div>`:''}</div></details></main>
 <footer class="info-footer"><span>${say('Design preview · Automatic printing is not connected yet.','设计预览 · 自动打印尚未接通。')}</span></footer>`;
 root.setAttribute('aria-busy',String(busy));
}
async function refresh(){
 if(busy)return;
 busy=true;error='';render();
 try{scope=deviceInfoScope(location.search,config);data=await loadDeviceInfo(scope);}
 catch(e){error=e.message;data=null;}
 finally{busy=false;render();}
}
root.addEventListener('click',event=>{
 const action=event.target.closest('[data-action]')?.dataset.action;
 if(action==='refresh')void refresh();
 if(action==='language'){lang=lang==='zh-CN'?'en-US':'zh-CN';const url=new URL(location.href);url.searchParams.set('lang',lang);history.replaceState(null,'',url);render();}
});
setInterval(()=>{if(!document.hidden)void refresh();},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)void refresh();});
await refresh();
