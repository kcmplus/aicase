import test from 'node:test';
import assert from 'node:assert/strict';
import {historyGroup,loadOrderHistory} from '../storefront/order-history.js';
import {orderListPage} from '../storefront/v35-order-list.js';
const free={reference:'free-order',model_name:'iPhone 16',status:'paid',progress:{payment:'free',code:'unbound'}};
test('old history reads all pages before filtering, counting and searching',async()=>{
 const rows=Array.from({length:20},(_,i)=>({reference:'pending-'+i,model_name:'Phone',status:'pending'}));
 const calls=[];const request=async path=>{calls.push(path);return new URLSearchParams(path).get('page')==='2'?{results:[free],has_more:false}:{results:rows,has_more:true};};
 const result=await loadOrderHistory({request,filter:'paid',search:'iPhone'});
 assert.deepEqual(result.results,[free]);assert.equal(result.has_more,false);
 assert.deepEqual(result.counts,{all:21,pending:20,paid:1,printed:0});assert.equal(calls.length,2);
 assert.deepEqual((await loadOrderHistory({request,filter:'paid',search:'FREEORDER'})).results,[free]);
});
test('modern history forwards filters and pagination without collecting extra pages',async()=>{
 const response={results:[free],has_more:true,counts:{all:42,paid:42,pending:0,printed:0}};const calls=[];
 assert.equal(await loadOrderHistory({request:async path=>{calls.push(path);return response;},page:2,filter:'paid',search:'a & b'}),response);
 assert.deepEqual(calls,['?page=2&status=paid&q=a%20%26%20b']);
});
test('history fallback never returns partial results after an unavailable page or stale navigation',async()=>{
 let reads=0;
 await assert.rejects(loadOrderHistory({request:async()=>{if(++reads===2)throw Error('Unavailable');return {results:[free],has_more:true};}}),/Unavailable/);
 reads=0;await loadOrderHistory({request:async()=>{reads++;return {results:[free],has_more:true};},alive:()=>false});assert.equal(reads,1);
});
test('fallback separates zero payment, refunds, cancellation and verified printing',()=>{
 assert.equal(historyGroup(free),'paid');
 assert.equal(historyGroup({...free,status:'cancelled'}),null);
 assert.equal(historyGroup({...free,refund:{status:'succeeded'}}),null);
 assert.equal(historyGroup({...free,refund:{status:'failed'}}),'paid');
 assert.equal(historyGroup({...free,progress:{payment:'paid',code:'printing'}}),'paid');
 assert.equal(historyGroup({...free,progress:{payment:'paid',code:'printed'}}),'printed');
 assert.equal(historyGroup({...free,progress:{payment:'unverified',code:'unverified'}}),null);
});
test('missing counts no longer disables history tabs or search',()=>{
 const html=orderListPage({counts:null,statusLabel:()=>''});
 assert.doesNotMatch(html,/disabled/);assert.match(html,/data-filter="paid"/);
 assert.match(orderListPage({loading:true,statusLabel:()=>''}),/disabled/);
});
