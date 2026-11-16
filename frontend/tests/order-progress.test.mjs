import test from 'node:test';
import assert from 'node:assert/strict';
import {progressPanel,progressText,progressPaymentText} from '../storefront/order-progress.js';
import {mergeOrderProgress} from '../storefront/order-service.js';
import {startVisiblePolling} from '../storefront/visible-polling.js';

test('printing, printed, dispensing and dispensed remain distinct in both languages',()=>{
 const codes=['printing','printed','delivering','dispensed'];
 for(const lang of ['zh-CN','en-US'])assert.equal(new Set(codes.map(code=>progressText({code},lang).label)).size,4);
 const panel=progressPanel({code:'dispensed',payment:'paid'},{lang:'zh-CN'});
 assert.ok(panel.includes('已出货，请取件'));
 assert.ok(!panel.includes('已领取'));
 assert.equal(progressPaymentText({code:'printing',payment:'free'},'zh-CN'),'0 元免付已确认');
 assert.equal(progressText({code:'new-unknown-code'},'zh-CN').label,'设备进度待核实');
});
test('stale, test and shipping progress never invent verified printing, and text is escaped',()=>{
 for(const code of ['test','delivery','unverified'])assert.ok(!progressPanel({code}).includes('aria-current="step"'));
 const html=progressPanel({code:'unverified',stale:true,message:'<script>bad</script>',device:{name:'<img src=x>',location:'A & B'}},{lang:'zh-CN'});
 assert.ok(html.includes('最后已知进度'));
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img'));
 assert.ok(html.includes('A &amp; B'));
});
test('a lightweight update cannot replace the design or another order',()=>{
 const original={id:'one',pass:{design:'private'},revision:5};
 const updated=mergeOrderProgress(original,{reference:'one',status:'printing',progress:{code:'printed'},snapshot:{design:'wrong'},revision:1});
 assert.equal(updated.pass,original.pass);assert.equal(updated.revision,5);assert.equal(updated.progress.code,'printed');
 assert.throws(()=>mergeOrderProgress(original,{reference:'someone-else'}),/identity/);
});
function harness(refresh){
 const timers=new Map(),events=new Map();let id=0;
 const doc={hidden:false,addEventListener:(name,fn)=>events.set(name,fn),removeEventListener:name=>events.delete(name)};
 const stop=startVisiblePolling({refresh,interval:5000,document:doc,setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:key=>timers.delete(key)});
 return {doc,events,timers,stop,tick:()=>{const [key,fn]=timers.entries().next().value;timers.delete(key);return fn();}};
}
test('polling pauses when hidden, refreshes on return and never overlaps',async()=>{
 let calls=0,release;
 const h=harness(()=>{calls++;return new Promise(resolve=>{release=resolve;});});
 const running=h.tick();assert.equal(calls,1);
 h.doc.hidden=true;h.events.get('visibilitychange')();assert.equal(h.timers.size,0);
 h.doc.hidden=false;h.events.get('visibilitychange')();assert.equal(calls,1);
 release();await running;assert.equal(h.timers.size,1);
 h.doc.hidden=true;h.events.get('visibilitychange')();
 h.doc.hidden=false;h.events.get('visibilitychange')();assert.equal(calls,2);
 h.stop();release();await Promise.resolve();assert.equal(h.timers.size,0);assert.equal(h.events.size,0);
});
test('stopped polling rejects late results through its alive guard',async()=>{
 let finish,applied=false;
 const h=harness(async alive=>{await new Promise(r=>{finish=r;});if(alive())applied=true;});
 const running=h.tick();h.stop();finish();await running;
 assert.equal(applied,false);assert.equal(h.timers.size,0);
});
