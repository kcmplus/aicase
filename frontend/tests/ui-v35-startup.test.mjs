import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

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
