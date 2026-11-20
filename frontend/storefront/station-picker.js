import {esc} from './art.js';
import {validCoordinates,stationNavigation} from './station-navigation.js';

export function chosenStation(state,key){
 return state.rows.find(s=>s.shop_id+':'+s.device_id===key&&s.availability==='available'&&validCoordinates(s.coordinates)&&s.coordinates.coordinate_type==='WGS84');
}
export function stationChoicePanel(state,{selectedKey='',scope=null,station=null,lang='en-US',now=Date.now()}={}){
 if(state.applicable===false)return '';
 const zh=lang==='zh-CN',say=(en,cn)=>zh?cn:en;
 if(scope){
  const matches=s=>s?.device_id===scope.device_id&&s?.shop_id===scope.shop_id;
  const current=state.rows.find(matches),identity=current||(matches(station)?station:null);
  const fresh=!state.error&&!state.busy&&state.loadedAt&&now-state.loadedAt<=60000;
  const statuses={available:say('Stock is available for this phone model and case style.','此设备有该机型和款式的库存。'),out_of_stock:say('This phone model and case style are out of stock at this station.','此设备的该机型和款式暂时缺货。'),updating:say('Station stock needs updating. Refresh or contact staff.','设备库存待更新，请刷新或联系工作人员。'),unsupported:say('This station does not support this phone model and case style.','此设备不支持该机型和款式。'),unavailable:say('Printing is unavailable at this station. Contact staff.','此设备暂不可打印，请联系工作人员。')};
  const status=state.busy?say('Checking station stock…','正在核验设备库存…'):state.error?say('Stock could not be checked. Please refresh.','库存核验失败，请刷新。'):!fresh?say('Refresh station stock before confirming your order.','请刷新设备库存后确认下单。'):statuses[current?.availability]||statuses.unavailable;
  return `<div class="pickup-choice"><strong class="pickup-choice-name">${esc(identity?.name||say('Scanned print station','已扫码的打印设备'))}</strong><p>${esc(identity?.location||say('Station address not provided','网点地址未填写'))}</p><small>${say('Device ID','设备编号')}: ${esc(scope.device_id)}${identity?.number?' · '+esc(identity.number):''}</small><p role="status">${esc(status)}</p><button type="button" class="text-button" data-action="refresh-stations" ${state.busy?'disabled':''}>${say('Refresh stock','刷新库存')}</button></div>`;
 }
 const selected=state.bound&&state.rows.length===1?state.rows[0]:chosenStation(state,selectedKey);
 const fresh=!state.error&&!state.busy&&state.loadedAt&&now-state.loadedAt<=60000;
 return `<div class="pickup-choice">${selected?`<strong class="pickup-choice-name">${esc(selected.name)}</strong><p>${esc(selected.location||say('Station address not provided','网点地址未填写'))}</p>${fresh&&selected.availability==='available'?stationNavigation(selected,{lang,compact:true}):`<p role="status">${say('Refresh station stock before navigating.','请刷新网点库存后再导航。')}</p>`}`:`<p>${say('Find a print station for your phone model. Enable location to see the nearest options.','查找支持此机型的打印网点，开启定位可按距离查看。')}</p>`}<button type="button" class="button secondary" data-action="open-station-picker">${selected?say(state.bound?'View station':'Change station',state.bound?'查看网点':'更换网点'):say('Find a nearby printer','查找附近打印网点')} ↗</button>${selected?`<small>${state.bound?say('Use the station already assigned to your order.','请前往订单已绑定的网点。'):say('Scan the station QR code when you arrive to confirm where to print.','到达后请扫描设备二维码，确认打印设备。')}</small>`:''}</div>`;
}

export function openStationPicker({lang='en-US',content,onAction,onNavigate,onToggle,onClose}={}){
 const zh=lang==='zh-CN',dialog=document.createElement('dialog'),opener=document.activeElement;
 dialog.className='v35-station-picker';dialog.setAttribute('aria-labelledby','station-picker-title');
 dialog.innerHTML=`<header><div><p>FIND YOUR PRINT SPOT</p><h2 id="station-picker-title">${zh?'选择附近打印网点':'Choose a nearby printer'}</h2></div><button type="button" data-close aria-label="${zh?'关闭':'Close'}">×</button></header><div class="station-picker-content"><label class="station-picker-search">${zh?'搜索网点或地址':'Search stations or addresses'}<input type="search" autocomplete="off" maxlength="120"></label><div class="station-picker-results"></div></div>`;
 const results=dialog.querySelector('.station-picker-results'),input=dialog.querySelector('input');
 let closed=false;
 const update=()=>{if(closed)return;const active=document.activeElement,action=active?.dataset.action,key=active?.dataset.stationKey;const scroll=dialog.querySelector('.station-picker-content'),top=scroll.scrollTop;results.innerHTML=content(input.value);scroll.scrollTop=top;if(action){const next=[...results.querySelectorAll('[data-action]')].find(el=>el.dataset.action===action&&el.dataset.stationKey===key);next?.focus({preventScroll:true});}};
 const close=()=>{if(closed)return;closed=true;window.removeEventListener('hashchange',close);dialog.close();dialog.remove();document.body.classList.remove('station-picker-open');onClose?.();if(opener?.isConnected)opener.focus({preventScroll:true});};
 // Keep editor shortcuts from intercepting the native dialog's Escape key.
 dialog.addEventListener('keydown',event=>event.stopPropagation());
 dialog.querySelector('[data-close]').onclick=close;
 dialog.addEventListener('cancel',event=>{event.preventDefault();close();});dialog.addEventListener('close',close);
 dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)close();}if(event.target.closest('.station-navigation a')&&onNavigate?.()===false)event.preventDefault();const button=event.target.closest('[data-action]');if(button&&!button.disabled)void onAction?.(button.dataset.action,button.dataset.stationKey);});
 dialog.addEventListener('toggle',event=>{if(event.target.matches('.station-navigation'))onToggle?.(event.target.closest('[data-station-key]')?.dataset.stationKey,event.target.open);},true);
 input.addEventListener('input',update);window.addEventListener('hashchange',close);
 document.body.append(dialog);document.body.classList.add('station-picker-open');update();dialog.showModal();
 return {update,close};
}
