import {locale} from './simple-i18n.js';

export function storageStartupPage(lang='en-US'){
 const zh=lang==='zh-CN';
 return `<main id="main" class="v35-page v35-wrap"><section class="v35-empty" role="alert" aria-labelledby="v35-storage-title"><p class="v35-kicker">POPOMO</p><h1 id="v35-storage-title">${zh?'无法访问浏览器存储':'Browser storage is unavailable'}</h1><p>${zh?'请在浏览器设置中允许此网站使用存储，然后重新加载。当前无法读取或保存设计，页面尚未进入编辑、下单或打印流程。':'Allow storage for this site in your browser settings, then reload. Designs cannot be read or saved, so editing, checkout and printing have not started.'}</p><p>${zh?'我们没有删除已有的本机设计。请勿清除网站数据，以免丢失本机保存的设计。':'Your existing local designs have not been deleted. Avoid clearing site data to preserve designs saved on this browser.'}</p><button type="button" class="v35-entry v35-primary" data-startup-reload>${zh?'重新加载并重试':'Reload and try again'}</button></section></main>`;
}

export function showStorageStartupError(app,{lang=locale(),reload=()=>location.reload()}={}){
 app.innerHTML=storageStartupPage(lang);
 const button=app.querySelector('[data-startup-reload]');
 button.addEventListener('click',reload);
 button.focus({preventScroll:true});
}
