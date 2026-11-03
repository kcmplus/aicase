import test from 'node:test';
import assert from 'node:assert/strict';
import {localDatabase} from '../storefront/local-database.js';

// Model browser connection lifecycle independently of application storage operations.
function installBrowser(t){
 const connections=[],failures=[];
 let opens=0;
 const previous=Object.getOwnPropertyDescriptor(globalThis,'indexedDB');
 Object.defineProperty(globalThis,'indexedDB',{configurable:true,value:{open(){
  opens++;
  const request={},failure=failures.shift();
  queueMicrotask(()=>{
   if(failure){request.error=failure;request.onerror();return;}
   const db={closed:false,close(){this.closed=true;},transaction(store,mode){
    if(this.closed)throw new DOMException('The database connection is closing.','InvalidStateError');
    return {store,mode,db:this};
   }};
   connections.push(db);request.result=db;request.onsuccess();
  });
  return request;
 }}});
 t.after(()=>{if(previous)Object.defineProperty(globalThis,'indexedDB',previous);else delete globalThis.indexedDB;});
 return {connections,failures,get opens(){return opens;}};
}
test('a closed cached connection is reopened once and concurrent callers share the new connection',async t=>{
 const browser=installBrowser(t),run=localDatabase('designs','photos');
 const first=await run('readonly',tx=>tx.db);
 first.close(); // Explicit close does not emit a close event, as in IndexedDB.
 let writes=0;
 const results=await Promise.all([run('readwrite',tx=>{writes++;return tx;}),run('readonly',tx=>tx)]);
 assert.equal(browser.opens,2);assert.equal(writes,1);
 assert.equal(results[0].db,results[1].db);assert.notEqual(results[0].db,first);
 assert.equal(results[0].mode,'readwrite');assert.equal(results[0].store,'photos');
 first.onclose(); // A delayed event from the old connection must not evict the new one.
 await run('readonly',()=>{});assert.equal(browser.opens,2);
});
test('unexpected close and versionchange invalidate the cached connection',async t=>{
 const browser=installBrowser(t),run=localDatabase('designs','photos');
 const first=await run('readonly',tx=>tx.db);
 first.close();first.onclose();
 const second=await run('readonly',tx=>tx.db);
 second.onversionchange();assert.equal(second.closed,true);
 await run('readonly',()=>{});assert.equal(browser.opens,3);
});
test('a failed database open does not poison later attempts',async t=>{
 const browser=installBrowser(t),run=localDatabase('designs','photos');
 browser.failures.push(new DOMException('Unavailable','UnknownError'));
 await assert.rejects(run('readonly',()=>{}),{name:'UnknownError'});
 await run('readonly',()=>{});assert.equal(browser.opens,2);
});
test('repeated closing errors stop after one reconnection',async t=>{
 const browser=installBrowser(t),run=localDatabase('designs','photos');
 const first=await run('readonly',tx=>tx.db);first.close();
 // Close every subsequent connection before transaction creation.
 const open=indexedDB.open;
 indexedDB.open=()=>{
  const request=open();
  queueMicrotask(()=>request.result.close());
  return request;
 };
 let operations=0;
 await assert.rejects(run('readwrite',()=>{operations++;}),{name:'InvalidStateError'});
 assert.equal(browser.opens,2);assert.equal(operations,0);
});
test('non-connection errors are not retried and started operations are never replayed',async t=>{
 const browser=installBrowser(t),run=localDatabase('designs','photos');
 const db=await run('readonly',tx=>tx.db);
 let writes=0;
 for(const name of ['AbortError','QuotaExceededError','InvalidStateError']){
  await assert.rejects(run('readwrite',()=>{writes++;return Promise.reject(new DOMException('Failed',name));}),{name});
 }
 assert.equal(writes,3);assert.equal(browser.opens,1);
 db.transaction=()=>{throw new DOMException('Missing store','NotFoundError');};
 await assert.rejects(run('readwrite',()=>{writes++;}),{name:'NotFoundError'});
 assert.equal(writes,3);assert.equal(browser.opens,1);
});
