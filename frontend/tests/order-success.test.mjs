import test from 'node:test';
import assert from 'node:assert/strict';
import {orderSuccessContent,createOrderSuccessTracker} from '../storefront/order-success.js';
const paid={id:'synthetic-order',server:true,status:'paid',mode:'stripe_live',currency:'USD',priceCents:50,progress:{payment:'paid'}};
function memory(){const data=new Map();return {getItem:key=>data.get(key),setItem:(key,value)=>data.set(key,value)};}
test('success notices require confirmed server status and distinguish paid, free and simulated receipts',()=>{
 assert.equal(orderSuccessContent(paid).title,'Payment successful');assert.equal(orderSuccessContent(paid).amount,'$0.50');
 for(const patch of [{server:false},{status:'pending'},{status:'cancelled'},{progress:{payment:'unpaid'}},{progress:null},{refund:{status:'pending'}},{refund:{status:'succeeded'}},{refund:{status:'failed'}},{priceCents:NaN},{currency:'<bad>'},{mode:'legacy'}])assert.equal(orderSuccessContent({...paid,...patch}),null);
 const free=orderSuccessContent({...paid,mode:'free_test',priceCents:0,progress:{payment:'free'}});
 assert.equal(free.title,'Payment successful');assert.match(free.message,/No payment was collected/);
 assert.equal(orderSuccessContent({...paid,mode:'free_test',progress:{payment:'free'}}),null);
 for(const mode of ['stripe_test','airwallex_test','demo']){const view=orderSuccessContent({...paid,mode,progress:{payment:'test'}});assert.equal(view.title,'Test order confirmed');assert.match(view.message,/No real payment/);}
 assert.equal(orderSuccessContent(paid,'zh-CN').title,'支付成功');
});
test('return URLs never confirm a pending payment; polling completion shows a receipt once across reloads',()=>{
 const storage=memory(),tracker=createOrderSuccessTracker({key:'guest',storage:()=>storage});
 assert.equal(tracker.observe({...paid,status:'pending',progress:{payment:'unpaid'}},{returned:true}),false);
 const afterReload=createOrderSuccessTracker({key:'guest',storage:()=>storage});
 assert.equal(afterReload.observe(paid),true);assert.equal(afterReload.observe(paid,{returned:true}),false);
 assert.equal(createOrderSuccessTracker({key:'guest',storage:()=>storage}).observe(paid,{returned:true}),false);
 assert.equal(createOrderSuccessTracker({key:'another-owner',storage:()=>storage}).observe(paid,{returned:true}),true);
});
test('old paid orders do not trigger notices without a checkout or verified return flow',()=>{
 const tracker=createOrderSuccessTracker({storage:()=>memory()});
 assert.equal(tracker.observe(paid),false);tracker.arm(paid.id);assert.equal(tracker.observe(paid),true);
 assert.equal(tracker.observe(paid),false);
});
test('refund and cancellation clear pending intent, including when storage is unavailable',()=>{
 const tracker=createOrderSuccessTracker({storage:()=>{throw Error('storage disabled');}});
 for(const patch of [{status:'cancelled'},{refund:{status:'pending'}}]){
  tracker.arm(paid.id);assert.equal(tracker.observe({...paid,...patch}),false);assert.equal(tracker.observe(paid),false);
 }
 tracker.arm(paid.id);assert.equal(tracker.observe(paid),true);assert.equal(tracker.observe(paid),false);
});
