import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {createDesignWorkspace,createDesignLibrary} from '../storefront/design-workspace.js';
import {storageStartupPage,showStorageStartupError} from '../storefront/v35-startup.js';

// Exercise the actual startup block with IndexedDB unavailable before first render.
test('an unavailable design database shows a recoverable startup error', async () => {
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const start=source.indexOf('let membership={...freshMembership()');
 const end=source.indexOf("let orderBook=await updateDesign('print-orders-v1'",start);
 assert.ok(start>=0&&end>start,'startup block must be present');
 const app={textContent:'Loading POPOMO…'};
 const context=vm.createContext({app,initialData:[null,null,null,null,{authenticated:false}],workspace:{active:true},
  freshMembership:()=>({jobs:{}}),privateUpdate:async()=>{throw new Error('Synthetic IndexedDB SecurityError');}});
 await assert.doesNotReject(vm.runInContext(`(async()=>{${source.slice(start,end)}})()`,context));
 assert.match(app.textContent,/storage|database|save|reload|存储|保存|重试/i);
});

function errorView(){
 const clicks={};let focused=0;
 const button={addEventListener:(type,fn)=>{clicks[type]=fn;},focus:()=>{focused++;}};
 return {app:{textContent:'',innerHTML:'',querySelector:()=>button},clicks,get focused(){return focused;}};
}

test('storage recovery is bilingual, keyboard reachable, and only reloads when requested',()=>{
 for(const lang of ['en-US','zh-CN']){
  const view=errorView();let reloads=0;
  showStorageStartupError(view.app,{lang,reload:()=>{reloads++;}});
  assert.equal(view.app.innerHTML,storageStartupPage(lang));
  assert.match(view.app.innerHTML,/role="alert".*aria-labelledby="v35-storage-title"/);
  assert.match(view.app.innerHTML,/<button type="button"[^>]+data-startup-reload/);
  assert.match(view.app.innerHTML,lang==='zh-CN'?/没有删除.*请勿清除网站数据/:/have not been deleted.*Avoid clearing site data/);
  assert.equal(view.focused,1);assert.equal(reloads,0);
  view.clicks.click();assert.equal(reloads,1);
  assert.doesNotMatch(view.app.innerHTML,/data-action=|href=|Synthetic|SecurityError/);
 }
});

// Run the complete application bootstrap, with all network reads stubbed and no
// browser data. Storage failures must return before business events or polling.
for(const failure of ['membership','orders','draft','migration','unknown-session-orders']){
 test(`actual app startup stops safely on ${failure} storage failure`,async()=>{
  const source=(await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8')).replace(/^import .*;\n/gm,'');
  const view=errorView(),writes=[],effects=[];let reloads=0;
  const fail=()=>{throw Object.assign(new Error('Synthetic private storage error'),{name:'SecurityError'});};
  const context=vm.createContext({
   document:{querySelector:selector=>{assert.equal(selector,'#app');return view.app;}},
   location:{hash:'#choose?source=photo',href:'http://127.0.0.1:4173/?device_id=123#choose?source=photo'},
   localStorage:{getItem:()=>null,setItem:()=>{effects.push('local write');}},
   setInterval:()=>{effects.push('polling');throw Error('Polling must not start');},
   window:{addEventListener:()=>{effects.push('window event');}},
   t:value=>value,deviceScope:()=>'',scopeIds:()=>null,
   loadCatalog:async()=>null,loadStockCatalog:async()=>null,fulfillmentConfig:async()=>({}),
   getAIAccount:async()=>failure==='unknown-session-orders'?null:{authenticated:false},
   createDesignWorkspace,createDesignLibrary,readPass:()=>{},
   readDesign:async key=>{if(failure==='draft'&&key.endsWith(':checkout-draft'))fail();},
   writeDesign:async()=>{effects.push('design write');},
   updateDesign:async(key,transform,initial)=>{
    writes.push(key);
    if((failure==='membership'&&key.endsWith(':ai-membership-v1'))||
      (failure.endsWith('orders')&&key==='print-orders-v1')||
      (failure==='migration'&&writes.filter(key=>key.endsWith(':ai-membership-v1')).length===2))fail();
    return transform(initial);
   },
   freshMembership:()=>({jobs:{}}),freshOrders:()=>({orders:{}}),
   stockSelection:()=>null,exampleFor:()=>({id:'portrait',results:{anime:'synthetic'}}),
   migrateRender:value=>value,
   showStorageStartupError:app=>showStorageStartupError(app,{lang:'zh-CN',reload:()=>{reloads++;}}),
  });
  await assert.doesNotReject(vm.runInContext(`(async()=>{${source}})()`,context));
  assert.match(view.app.innerHTML,/无法访问浏览器存储/);
  assert.equal(view.focused,1);assert.deepEqual(effects,[]);
  assert.equal(writes.length,{membership:1,orders:2,draft:2,migration:3,'unknown-session-orders':1}[failure]);
  assert.equal(reloads,0);view.clicks.click();assert.equal(reloads,1);
 });
}
