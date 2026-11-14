import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,access} from 'node:fs/promises';
import {shellHeader,shellFooter,homePresentation,shellInfo,mountShell} from '../storefront/v35-shell.js';
import {worksPage,workDetailPage,matchingWorks,tutorialPage,aboutPage,locationsPage,membershipInfoPage,publicPageDestination} from '../storefront/v35-pages.js';
import {designs} from '../storefront/simple-core.js';
import {normalizeLocale} from '../storefront/simple-i18n.js';

test('V35 home prioritizes the real album handler and preserves gallery and AI editor destinations',()=>{
 const html=homePresentation({gallery:'<section id="designs">CATALOG</section>'});
 assert.ok(html.indexOf('data-action="home-photo"')<html.indexOf('href="#designs"'));
 assert.match(html,/id="photo-file" data-home-upload type="file" accept="image\/jpeg,image\/png,image\/webp"/);
 assert.match(html,/href="#choose\?source=photo&studio=1"/);
 assert.match(html,/<section id="designs">CATALOG<\/section>/);
 assert.doesNotMatch(html,/sessionStorage|setTimeout|pay_status|data-action="advance-print"/);
});
test('upload busy state disables the album action without claiming upload success',()=>{
 const html=homePresentation({busy:true});
 assert.match(html,/data-action="home-photo" aria-busy="true" disabled/);
 assert.match(html,/Reading your photo…/);
 assert.doesNotMatch(homePresentation(),/aria-busy="true"/);
});
test('shared shell exposes working legacy destinations and bilingual native menu semantics',()=>{
 for(const lang of ['en-US','zh-CN']){
  const header=shellHeader({lang,authenticated:true,route:'orders'});
  for(const hash of ['home','designs','how-it-works','choose?source=photo','orders','pass','account'])assert.ok(header.includes(`href="#${hash}"`),hash);
  assert.match(header,/<dialog id="v35-menu"/);
  assert.match(header,/aria-controls="v35-menu" aria-expanded="false"/);
  assert.match(header,/href="#orders" aria-current="page"/);
  assert.match(header,new RegExp(`data-shell-language="${lang}" aria-pressed="true"`));
  assert.doesNotMatch(header,/href="\.\/.*\.html|#kiosk|#membership/);
  assert.match(shellFooter(lang),/data-shell-info="station"/);
 }
 assert.match(shellHeader({lang:'zh-CN'}),/打开菜单/);
 assert.match(shellHeader(),/Open menu/);
});
test('home instructions follow phone confirmation and do not ask to save a design QR',()=>{
 const html=homePresentation({lang:'zh-CN'});
 assert.match(html,/扫描设备屏上的二维码/);
 assert.match(html,/已出货不等于已取件/);
 assert.match(html,/快递／空运暂未开放结算/);
 assert.doesNotMatch(html,/保存.{0,4}二维码|Keep your code|save the QR code|Show your code/);
 assert.match(shellInfo('station','en-US')[1],/Nearby search is not available/);
 assert.match(shellInfo('ai','zh-CN')[1],/服务端确认/);
});
test('all V35 presentation assets are local and available; editor entry retains the existing service module',async()=>{
 const html=homePresentation(),css=await readFile(new URL('../storefront/v35-shell.css',import.meta.url),'utf8');
 for(const path of new Set([...html.matchAll(/(?:src)="\.\/([^"?]+)"/g),...css.matchAll(/url\('\.\/([^']+)'\)/g)].map(match=>match[1])))await access(new URL('../storefront/'+path,import.meta.url));
 const entry=await readFile(new URL('../storefront/index.html',import.meta.url),'utf8');
 assert.match(entry,/href="\.\/v35-shell.css"/);assert.match(entry,/src="\.\/simple-app.js"/);
 assert.doesNotMatch(entry,/popomo-ui|order-store.js|profile-store.js/);
});

test('shell menu updates its expanded state and restores focus when closed',()=>{
 const listeners={}; let focused=0;
 const opener={isConnected:true,attrs:{},setAttribute(key,value){this.attrs[key]=value;},focus(){focused++;}};
 const closeButton={focus(){focused++;}};
 const menu={open:false,addEventListener(type,fn){listeners[type]=fn;},showModal(){this.open=true;},close(){this.open=false;listeners.close();},querySelector(){return closeButton;}};
 const classes=new Set();
 const originalDocument=globalThis.document;
 globalThis.document={body:{classList:{add:value=>classes.add(value),remove:value=>classes.delete(value)}}};
 const root={querySelector(selector){return selector==='#v35-menu'?menu:opener;},addEventListener(type,fn){listeners[type]=fn;},removeEventListener(type){delete listeners[type];}};
 const click=selector=>listeners.click({target:{closest(){return {matches(value){return value.split(',').includes(selector);},dataset:{}};}}});
 try{
  const cleanup=mountShell(root);
  click('[data-shell-menu]');
  assert.equal(menu.open,true);assert.equal(opener.attrs['aria-expanded'],'true');assert.ok(classes.has('v35-menu-open'));
  click('[data-shell-close]');
  assert.equal(menu.open,false);assert.equal(opener.attrs['aria-expanded'],'false');assert.equal(classes.has('v35-menu-open'),false);assert.equal(focused,2);
  cleanup();assert.equal(listeners.click,undefined);
 }finally{globalThis.document=originalDocument;}
});

const preview=id=>`<div class="phone-case" data-template="${id}"></div>`;
test('Works center filters the existing editable catalog, preserves bilingual search and has an empty state',()=>{
 assert.deepEqual(matchingWorks(designs,{query:'花开'}).map(work=>work.id),['bloom']);
 assert.deepEqual(matchingWorks(designs,{category:'graphic',query:'statement'}).map(work=>work.id),['type']);
 assert.deepEqual(matchingWorks(designs,{category:'travel'}).map(work=>work.id),['sunset']);
 const html=worksPage({works:designs,preview,params:new URLSearchParams({category:'all',q:'<unmatched>"'})});
 assert.match(html,/No matching designs/);assert.match(html,/value="&lt;unmatched&gt;&quot;"/);assert.doesNotMatch(html,/value="<unmatched>/);
 for(const lang of ['en-US','zh-CN']){
  const all=worksPage({works:designs,preview,lang});
  for(const work of designs)assert.match(all,new RegExp(`href="#work\\?id=${work.id}"`));
  assert.match(all,/id="v35-work-search"/);assert.match(all,/role="status"/);
 }
});
test('Work details resolve only available template ids and lead to the real editor without simulated orders',()=>{
 const html=workDetailPage({works:designs,preview,params:new URLSearchParams({id:'popomo-bloom'})});
 assert.match(html,/data-template="bloom"/);assert.match(html,/href="#choose\?design=bloom"/);assert.match(html,/href="#designs"/);
 assert.doesNotMatch(html,/sessionStorage|data-like|data-use="print"|quantity/);
 const missing=workDetailPage({works:designs,preview,params:new URLSearchParams({id:'unpublished-customer-photo'})});
 assert.match(missing,/Design not found/);assert.doesNotMatch(missing,/data-template|href="#choose/);
});
test('Tutorial and about retain real destinations and explain the current printing boundaries in both languages',()=>{
 for(const lang of ['en-US','zh-CN']){
  const html=tutorialPage({lang});
  for(const section of ['steps','save','print'])assert.match(html,new RegExp(`id="${section}"`));
  for(const target of ['#choose?source=photo','#designs','#orders','#locations'])assert.ok(html.includes(`href="${target}"`));
  assert.match(html,/data-shell-info="tutorial"/);
  assert.doesNotMatch(html,/3–4|US\$4|保存.{0,4}二维码|save the QR|data-action="advance-print"/);
  assert.match(aboutPage({lang}),/id="our-story"/);
 }
 assert.match(tutorialPage(),/Dispensed does not mean collected/);
 assert.match(tutorialPage({lang:'zh-CN'}),/快递／空运结算与附近搜索暂未开放/);
 assert.match(shellInfo('tutorial','zh-CN')[1],/确认已付订单/);
 assert.equal(shellInfo('station')[2],'#locations');
});
const station={device_id:'123',shop_id:'351',name:'Verified <device>',location:'Actual address',number:'A-1',models:[{name:'iPhone 17',brand:'Apple'}],inventory:{availability:'ready'},coordinates:{coordinate_type:'WGS84',latitude:10,longitude:20}};
test('Station pages show verified data and navigate only with confirmed WGS84 coordinates',()=>{
 const html=locationsPage({station,hasScope:true});
 assert.match(html,/Verified &lt;device&gt;/);assert.match(html,/Actual address/);assert.match(html,/iPhone 17/);
 assert.match(html,/maps\.google|www\.google\.com\/maps/);assert.match(html,/destination=10%2C20/);
 assert.match(html,/data-action="scan-station"/);assert.doesNotMatch(html,/DEMO-0|New York|km away|online now/);
 for(const coordinates of [null,{...station.coordinates,coordinate_type:'GCJ02'},{...station.coordinates,latitude:999}]){
  const withoutMap=locationsPage({station:{...station,coordinates},hasScope:true});
  assert.doesNotMatch(withoutMap,/href="https:\/\/(?:www\.google|maps\.apple|uri\.amap|api\.map\.baidu)/);
 }
});
test('Station unknown, error, empty, updating and busy states never create fake print authority',()=>{
 const unknown=locationsPage();assert.match(unknown,/No printer selected/);assert.match(unknown,/Nearby search is not available/);assert.doesNotMatch(unknown,/data-action="refresh-device-info"/);
 const error=locationsPage({hasScope:true,error:'device-unavailable',legacy:true});
 assert.match(error,/identity is ambiguous/);assert.match(error,/read-only/);assert.doesNotMatch(error,/Verified|Actual address|data-action="(?:start-print|advance-print)"/);
 const busy=locationsPage({hasScope:true,busy:true});assert.match(busy,/aria-busy="true" disabled/);
 for(const [status,message] of [['empty','No available models'],['updating','Inventory is being refreshed']])assert.ok(locationsPage({station:{...station,models:[],inventory:{availability:status}}}).includes(message));
});
test('Membership deep link keeps actual allowances and exposes no simulated purchase or renewal',()=>{
 const html=membershipInfoPage({account:{authenticated:true,trialRemaining:7,subscription:{endsAt:Date.now()+60000,monthlyLimit:20,used:4}}});
 assert.match(html,/<strong>7<\/strong>/);assert.match(html,/<strong>16<\/strong>/);assert.match(html,/href="#account"/);
 assert.match(html,/Membership purchases are not available/);assert.doesNotMatch(html,/<form|data-ai-action|subscribe|renewal/);
 const signedOut=membershipInfoPage({account:{authenticated:false,trialRemaining:7}});assert.doesNotMatch(signedOut,/<strong>7<\/strong>/);assert.match(signedOut,/Sign in to view/);
});
test('Public HTML aliases preserve device, language, design and section parameters',async()=>{
 assert.equal(normalizeLocale('zh'),'zh-CN');assert.equal(normalizeLocale('en'),'en-US');assert.equal(normalizeLocale('zh-CN'),'zh-CN');assert.equal(normalizeLocale('invalid'),null);
 for(const [name,route] of [['works-center','designs'],['work-detail','work'],['how-to','how-it-works'],['about','about'],['printers','printers'],['print-locations','locations']]){
  const destination=new URL(publicPageDestination(`http://127.0.0.1:4173/${name}.html?device_id=123&shop_id=351&lang=zh&id=bloom#steps`));
  assert.equal(destination.pathname,'/');assert.equal(destination.searchParams.get('device_id'),'123');
  assert.equal(destination.hash.split('?')[0],'#'+route);
  const params=new URLSearchParams(destination.hash.split('?')[1]);
  assert.equal(params.get('shop_id'),'351');assert.equal(params.get('lang'),'zh');assert.equal(params.get('id'),'bloom');assert.equal(params.get('section'),'steps');
  const entry=await readFile(new URL(`../storefront/${name}.html`,import.meta.url),'utf8');assert.match(entry,/src="\.\/v35-page-entry.js"/);
 }
 assert.equal(publicPageDestination('http://127.0.0.1:4173/unregistered.html'),null);
});
test('Public page integration registers real routes and removes obsolete manual hardware simulation',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 for(const route of ['designs:()=>worksPage','work:()=>workDetailPage',"'how-it-works':()=>tutorialPage",'about:()=>aboutPage','locations:publicStationPage','printers:publicStationPage','kiosk:()=>publicStationPage(true)','membership:()=>membershipInfoPage'])assert.ok(source.includes(route));
 assert.match(source,/event.target.id==='v35-work-search'/);
 assert.doesNotMatch(source,/data-action="(?:start-print|advance-print|scan-saved)"|if\(el.dataset.action==='(?:start-print|advance-print)'\)/);
 const deviceEntry=await readFile(new URL('../storefront/device-entry.js',import.meta.url),'utf8');
 assert.match(deviceEntry,/import\('\.\/device-info-app.js'\)/);assert.match(deviceEntry,/destination.hash='kiosk'/);assert.doesNotMatch(deviceEntry,/import\('\.\/device-app.js'\)/);
 const htmls=[worksPage({works:designs,preview}),workDetailPage({works:designs,preview,params:new URLSearchParams({id:'bloom'})}),tutorialPage(),aboutPage(),locationsPage()];
 for(const html of htmls)for(const [,path] of html.matchAll(/src="\.\/([^"?]+)"/g))await access(new URL('../storefront/'+path,import.meta.url));
});
