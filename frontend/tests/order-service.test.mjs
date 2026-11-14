import test from 'node:test';
import assert from 'node:assert/strict';
import {orderAccessKey,orderRequest,savedOrder,checkoutBody,checkoutEmailField,getPaymentConfig,stripeCheckoutUrl} from '../storefront/order-service.js';
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
test('order writes carry customer session and CSRF while retaining browser ownership',async()=>{
 const calls=[];await orderRequest('example/',{key:'b'.repeat(64),method:'PATCH',body:{revision:1},fetcher:async(url,options)=>{calls.push({url,...options});return {ok:true,json:async()=>({csrfToken:'test-csrf'})}}});
 const [csrf,sent]=calls;assert.equal(csrf.url,'/api/v1/auth/csrf/');assert.equal(csrf.credentials,'same-origin');
 assert.equal(sent.credentials,'same-origin');assert.equal(sent.cache,'no-store');assert.equal(sent.headers['X-Order-Key'],'b'.repeat(64));assert.equal(sent.headers['X-CSRFToken'],'test-csrf');assert.equal(JSON.parse(sent.body).revision,1);
});
test('signed-in checkout displays email without input and sends expected identity only',()=>{
 const account={authenticated:true,customer:{id:crypto.randomUUID(),email:'member@example.com'}};
 const body=checkoutBody({requestKey:crypto.randomUUID(),pass:pass()},{account,accepted:true,email:'other@example.com',amount:'10.00'});
 assert.equal(body.customer_id,account.customer.id);assert.equal(Object.hasOwn(body,'customer_email'),false);
 const html=checkoutEmailField(account);assert.match(html,/member@example.com/);assert.doesNotMatch(html,/<input/);
 assert.doesNotMatch(checkoutEmailField({...account,customer:{...account.customer,email:'<script>test</script>'}}),/<script>/);
});
test('guest checkout retains optional manual email without claiming an account',()=>{
 for(const account of [undefined,{authenticated:false,customer:{id:'stale',email:'stale@example.com'}}]){
  const body=checkoutBody({requestKey:crypto.randomUUID(),pass:pass()},{account,accepted:true,email:'guest@example.com',amount:'10.00'});
  assert.equal(body.customer_id,null);assert.equal(body.customer_email,'guest@example.com');
  const html=checkoutEmailField(account);assert.match(html,/<input name="email"/);assert.doesNotMatch(html,/required|stale@example.com/);
 }
});
test('unavailable sign-in check stops checkout before sending the order',async()=>{
 const calls=[];
 await assert.rejects(orderRequest('',{method:'POST',body:{},key:'a'.repeat(64),fetcher:async url=>{calls.push(url);return {ok:false}}}),/sign-in could not be checked/);
 assert.deepEqual(calls,['/api/v1/auth/csrf/']);
});
test('the shared admin/order renderer escapes customer text',()=>{
 const snapshot=pass();snapshot.addedArtwork=[{id:'extra-text',type:'text',text:'<script>alert(1)</script>',font:'serif',color:'#123456',x:50,y:50,scale:100,rotation:0}];
 const html=phone(makePersonalDesign(snapshot),snapshot.model);
 assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));
});

test('Stripe state stays unpaid until the server confirms payment',()=>{
 const data={reference:crypto.randomUUID(),snapshot:pass(),status:'pending',amount:'10.00',currency:'USD',mode:'stripe_live',revision:1,created_at:new Date().toISOString(),updated_at:new Date().toISOString()};
 assert.equal(savedOrder(data).status,'pending');assert.equal(savedOrder(data).mode,'stripe_live');
 assert.equal(savedOrder({...data,status:'paid'}).status,'paid');
 const body=checkoutBody({requestKey:crypto.randomUUID(),pass:pass()},{accepted:true,amount:'10.00',provider:'stripe',mode:'test'});
 assert.equal(body.payment_provider,'stripe');assert.equal(body.payment_mode,'test');
});
test('payment config failure cannot silently select demo payment',async()=>{
 await assert.rejects(getPaymentConfig(async()=>({ok:false})),/could not be loaded/);
 await assert.rejects(getPaymentConfig(async()=>({ok:true,json:async()=>({})})),/Invalid payment settings/);
 assert.deepEqual(await getPaymentConfig(async()=>({ok:true,json:async()=>({provider:'stripe',mode:'test',available:true})})),{provider:'stripe',mode:'test',available:true});
});
test('redirect only accepts Stripe hosted checkout',()=>{
 assert.equal(stripeCheckoutUrl('https://checkout.stripe.com/c/pay/test'),'https://checkout.stripe.com/c/pay/test');
 for(const url of ['javascript:alert(1)','https://evil.test','http://checkout.stripe.com/pay','https://checkout.stripe.com.evil.test','https://user@checkout.stripe.com/pay'])assert.throws(()=>stripeCheckoutUrl(url));
});

import {airwallexOptions,openAirwallexCheckout} from '../storefront/airwallex-checkout.js';
test('checkout freezes delivery choice while historical responses stay unclassified',()=>{
 const draft={requestKey:crypto.randomUUID(),pass:pass(),fulfillmentType:'air'};
 const body=checkoutBody(draft,{accepted:true,amount:'10.00'});
 assert.equal(body.fulfillment_type,'air');
 const data={reference:crypto.randomUUID(),snapshot:draft.pass,status:'paid',amount:'10.00',currency:'USD',mode:'airwallex_live',revision:1,created_at:new Date().toISOString(),updated_at:new Date().toISOString()};
 assert.equal(savedOrder(data).fulfillmentType,'unspecified');
 assert.equal(savedOrder({...data,fulfillment_type:'courier'}).fulfillmentType,'courier');
});
test('delivery payment status never gives station collection instructions',()=>{
 for(const fulfillmentType of ['courier','air']){
  const view=paymentState({status:'ready',fulfillmentType});
  assert.equal(view.title,'Your delivery order.');
  assert.doesNotMatch(view.message,/station|collect/i);
 }
});
const airwallexData=()=>({provider:'airwallex',order:{reference:'b01737e5-c5ab-4765-8834-cbd92dfeaf81',mode:'airwallex_test',status:'pending',currency:'USD'},checkout:{env:'demo',mode:'payment',currency:'USD',intent_id:'int_test123',client_secret:'temporary-client-secret',successUrl:'https://shop.example.com/#payment?order=b01737e5-c5ab-4765-8834-cbd92dfeaf81&result=success'}});
test('Airwallex config and order remain pending until backend confirmation',async()=>{
 assert.deepEqual(await getPaymentConfig(async()=>({ok:true,json:async()=>({provider:'airwallex',mode:'test',available:true})})),{provider:'airwallex',mode:'test',available:true});
 const data={reference:crypto.randomUUID(),snapshot:pass(),status:'pending',amount:'10.00',currency:'USD',mode:'airwallex_live',revision:1,created_at:new Date().toISOString(),updated_at:new Date().toISOString()};
 assert.equal(savedOrder(data).status,'pending');assert.equal(savedOrder(data).mode,'airwallex_live');
 const body=checkoutBody({requestKey:crypto.randomUUID(),pass:pass()},{accepted:true,amount:'10.00',provider:'airwallex',mode:'test'});
 assert.equal(body.payment_provider,'airwallex');assert.equal(body.payment_mode,'test');
});
test('Airwallex SDK uses only verified checkout fields and matching environment',async()=>{
 const calls=[];const data=airwallexData();data.checkout.untrusted='ignore';
 await openAirwallexCheckout(data,async()=>({init:async options=>{calls.push(options);return {payments:{redirectToCheckout:async options=>calls.push(options)}}}}));
 assert.deepEqual(calls[0],{env:'demo',enabledElements:['payments']});
 assert.equal(calls[1].intent_id,'int_test123');assert.equal(calls[1].untrusted,undefined);
 assert.equal(calls[1].client_secret,'temporary-client-secret');
 data.order.mode='airwallex_live';data.checkout.env='prod';assert.equal(airwallexOptions(data).env,'prod');
});
test('Airwallex rejects invalid SDK options and masks SDK error details',async()=>{
 for(const fields of [{env:'prod'},{currency:'EUR'},{mode:'subscription'},{intent_id:'../../bad'},{client_secret:''},
   {successUrl:'http://shop.example.com/'},{successUrl:'javascript:alert(1)'},{successUrl:'https://user@shop.example.com/'},
   {successUrl:'https://shop.example.com/#payment?order=another&result=success'}]){
  const data=airwallexData();Object.assign(data.checkout,fields);assert.throws(()=>airwallexOptions(data));
 }
 const paid=airwallexData();paid.order.status='paid';assert.throws(()=>airwallexOptions(paid));
 await assert.rejects(openAirwallexCheckout(airwallexData(),async()=>{throw Error('temporary-client-secret')}),error=>!error.message.includes('temporary-client-secret')&&error.message.includes('order is saved'));
});

import {paymentState} from '../storefront/payment-state.js';
test('payment return never claims success or invites duplicate payment',()=>{
 const pending=paymentState({status:'pending'},{returned:true});
 assert.equal(pending.fulfilled,false);assert.equal(pending.showCode,false);assert.equal(pending.canPay,false);assert.equal(pending.showNewOrder,false);
 assert.match(pending.message,/do not pay again/);
 const delayed=paymentState({status:'pending'},{returned:true,exhausted:true});assert.match(delayed.message,/longer than usual/);
 assert.equal(paymentState({status:'pending'}).canPay,true);
});
test('paid and fulfillment statuses retain receipt; cancelled and unknown do not',()=>{
 for(const status of ['paid','printing','ready','completed','collected']){
  const state=paymentState({status});assert.equal(state.showCode,true);assert.equal(state.canPay,false);assert.doesNotMatch(state.title,/closed/i);
 }
 for(const status of ['cancelled','unknown']){
  const state=paymentState({status});assert.equal(state.showCode,false);assert.equal(state.canPay,false);
 }
});

test('payment config retries only 503 up to three times, including HTML maintenance responses',async()=>{
 for(const failures of [0,1,3,4]){
  let calls=0;const delays=[],signals=[];
  const request=getPaymentConfig(async(url,options)=>{
   calls++;signals.push(options.signal);
   assert.equal(options.credentials,'omit');assert.equal(options.cache,'no-store');
   return calls<=failures?{ok:false,status:503,json:async()=>{throw Error('HTML maintenance page');}}:{ok:true,status:200,json:async()=>({provider:'airwallex',mode:'live',available:true})};
  },{sleep:async ms=>delays.push(ms)});
  if(failures===4)await assert.rejects(request,/after 3 retries/);
  else assert.equal((await request).provider,'airwallex');
  assert.equal(calls,Math.min(failures+1,4));
  assert.deepEqual(delays,[1000,2000,4000].slice(0,failures));
  assert.equal(new Set(signals).size,calls);
 }
});
test('payment config does not retry authorization errors or malformed successful responses',async()=>{
 for(const status of [401,403,200]){
  let calls=0;
  await assert.rejects(getPaymentConfig(async()=>{calls++;return {ok:status===200,status,json:async()=>({})};},{sleep:async()=>assert.fail('must not retry')}));
  assert.equal(calls,1);
 }
});

test('refund states suppress payment and fulfillment code without rewriting order history',()=>{
 for(const status of ['requested','pending','succeeded','failed']){
  const view=paymentState({status:'paid',refund:{status}},{returned:true});
  assert.equal(view.canPay,false);assert.equal(view.showCode,false);assert.equal(view.fulfilled,false);
  assert.match(view.title,/refund/i);
 }
 assert.equal(paymentState({status:'paid',refund:{status:'succeeded'}}).showNewOrder,true);
});

test('no-charge checkout is explicit and never claims money was collected',async()=>{
 const config={provider:'free',mode:'test',available:true,zero_price_test:true};
 assert.deepEqual(await getPaymentConfig(async()=>({ok:true,json:async()=>config})),config);
 for(const value of [{...config,mode:'live'},{...config,zero_price_test:false}])await assert.rejects(getPaymentConfig(async()=>({ok:true,json:async()=>value})),/Invalid/);
 const view=paymentState({mode:'free_test',status:'paid',fulfillmentType:'pickup'});
 assert.equal(view.title,'No-charge order confirmed.');assert.equal(view.canPay,false);
 assert.doesNotMatch(view.message,/payment is confirmed/i);
 const body=checkoutBody({requestKey:crypto.randomUUID(),pass:pass()},{accepted:true,amount:'0.00',provider:'free',mode:'test'});
 assert.equal(body.expected_amount,'0.00');assert.equal(body.payment_provider,'free');
});
