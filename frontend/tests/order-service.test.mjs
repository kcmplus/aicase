import test from 'node:test';
import assert from 'node:assert/strict';
import {orderAccessKey,orderRequest,savedOrder,checkoutBody} from '../storefront/order-service.js';
import {createPersonalPass} from '../storefront/simple-core.js';
import {phone} from '../storefront/art.js';
import {makePersonalDesign} from '../storefront/simple-personalize.js';
const pass=()=>createPersonalPass({source:'collection',designId:'bloom',model:'iPhone 16 Pro',effect:'original',intensity:65,zoom:100,x:50,y:50});
test('a browser keeps one unguessable order key and surfaces storage failure',()=>{
 const values=new Map(),storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)};
 const key=orderAccessKey(storage);assert.match(key,/^[a-f0-9]{64}$/);assert.equal(orderAccessKey(storage),key);
 assert.throws(()=>orderAccessKey({getItem:()=>null,setItem:()=>{throw Error('storage blocked')}}),/storage blocked/);
});
test('checkout retries reuse the draft key and contain no trusted status or amount override',()=>{
 const draft={requestKey:crypto.randomUUID(),pass:pass()};
 const body=checkoutBody(draft,{accepted:true,amount:'9.90'});
 assert.deepEqual(body,checkoutBody(draft,{accepted:true,amount:'9.90'}));
 assert.equal(body.expected_amount,'9.90');assert.equal(body.status,undefined);assert.equal(body.amount,undefined);
});
test('server response keeps charged price and retires the previous design code',()=>{
 const original=pass(),next=pass(),data={reference:crypto.randomUUID(),snapshot:original,status:'paid',amount:'9.90',currency:'USD',mode:'demo',revision:1,created_at:new Date().toISOString(),updated_at:new Date().toISOString()};
 const first=savedOrder(data);const revision=savedOrder({...data,snapshot:next,status:'completed',revision:4},first);
 assert.equal(revision.priceCents,990);assert.equal(revision.status,'collected');assert.equal(revision.pass.code,next.code);assert.deepEqual(revision.oldCodes,[original.code]);
});
test('order network failures never fabricate a paid result',async()=>{
 await assert.rejects(orderRequest('',{key:'a'.repeat(64),fetcher:async()=>{throw Error('offline')}}),/offline/);
 await assert.rejects(orderRequest('',{key:'a'.repeat(64),fetcher:async()=>({ok:false,status:409,json:async()=>({detail:'Price changed'})})}),/Price changed/);
 await assert.rejects(orderRequest('',{key:'a'.repeat(64),fetcher:async()=>({json:async()=>{throw Error()}})}),/temporarily unavailable/);
});
test('order request carries browser ownership separately from admin session cookies',async()=>{
 let sent;await orderRequest('example/',{key:'b'.repeat(64),method:'PATCH',body:{revision:1},fetcher:async(url,options)=>{sent={url,...options};return {ok:true,json:async()=>({})}}});
 assert.equal(sent.credentials,'omit');assert.equal(sent.cache,'no-store');assert.equal(sent.headers['X-Order-Key'],'b'.repeat(64));assert.equal(JSON.parse(sent.body).revision,1);
});
test('the shared admin/order renderer escapes customer text',()=>{
 const snapshot=pass();snapshot.addedArtwork=[{id:'extra-text',type:'text',text:'<script>alert(1)</script>',font:'serif',color:'#123456',x:50,y:50,scale:100,rotation:0}];
 const html=phone(makePersonalDesign(snapshot),snapshot.model);
 assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));
});
