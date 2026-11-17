import test from 'node:test';
import assert from 'node:assert/strict';
import {generatedPhotoPlacement,submitLiveRender,aiRequest,createLiveRender,mergeLiveRender,hydrateLiveImage} from '../storefront/ai-service.js';
import {refreshAIOrder,canApplyAIOrder} from '../storefront/ai-core.js';
import {aiPage} from '../storefront/ai-view.js';
import {freshMembership,refreshMembership} from '../storefront/ai-membership.js';
import {createPersonalPass,readPass} from '../storefront/simple-core.js';
import {generationProgressState} from '../storefront/ai-wait.js';

const photo='data:image/jpeg;base64,AQID';
const job=()=>createLiveRender({photo,styleId:'anime',exampleId:'portrait',model:'iPhone 17'});
const response=j=>({id:'a3333333-1111-4444-8888-abcdef123456',requestKey:j.id.slice(3),mode:'live',status:'queued',payment:'credit_reserved',allocation:{type:'trial'},createdAt:1000,result:null});
test('real jobs never advance on a demo timer or substitute reference images',()=>{
 const pending=job();const queued=mergeLiveRender(pending,response(pending));
 assert.equal(pending.mode,'live');assert.equal(pending.status,'awaiting_confirmation');
 assert.deepEqual(refreshAIOrder(queued,Date.now()+9999999),queued);assert.equal(canApplyAIOrder(queued),false);
 const r={...response(pending),status:'ready',result:'/api/v1/store/ai-renders/a3333333-1111-4444-8888-abcdef123456/image/'};
 const ready=mergeLiveRender(queued,r);assert.equal(canApplyAIOrder(ready),false);
 assert.equal(canApplyAIOrder({...ready,resultPhoto:photo}),true);
 assert.equal(canApplyAIOrder({...ready,resultPhoto:photo,result:pending.sample.result}),false);
});
test('responses must match the saved request and private image route',()=>{
 const j=job();const r=response(j);
 for(const change of [{id:'bad'},{requestKey:crypto.randomUUID()},{mode:'demo'},{status:'complete'},{status:'ready',result:'https://example.com/tracker.png'}])assert.throws(()=>mergeLiveRender(j,{...r,...change}));
});
test('expired server images stop loading while an existing local copy remains usable',async()=>{
 const j=job(),r=response(j);
 const expired=mergeLiveRender(j,{...r,status:'ready',result:`/api/v1/store/ai-renders/${r.id}/image/`,imageExpired:true,imageExpiresAt:12345});
 assert.equal(await hydrateLiveImage(expired),expired);
 const html=aiPage(expired,freshMembership());
 assert.match(html,/Image retention period ended/);
 assert.doesNotMatch(html,/Loading your image|Reload my image|data-ai-action="apply"|STYLE REFERENCE/);
 const local={...expired,resultPhoto:photo};
 assert.equal(await hydrateLiveImage(local),local);
 assert.equal(canApplyAIOrder(local),true);
 assert.match(aiPage(local,freshMembership()),/data-ai-action="apply"/);
});
test('expiry between status polling and image loading becomes an expired state',async t=>{
 t.mock.method(globalThis,'fetch',async()=>({ok:false,status:410,json:async()=>({detail:'Image expired'})}));
 const j=job(),r=response(j);
 const ready=mergeLiveRender(j,{...r,status:'ready',result:`/api/v1/store/ai-renders/${r.id}/image/`});
 const expired=await hydrateLiveImage(ready);
 assert.equal(expired.imageExpired,true);
 assert.equal(expired.status,'ready');
 assert.equal(expired.payment,'credit_reserved');
});
test('result screen shows the actual input and actual generated image',()=>{
 const j=job();const r=response(j);const ready={...mergeLiveRender(j,{...r,status:'ready',result:`/api/v1/store/ai-renders/${r.id}/image/`}),resultPhoto:'data:image/jpeg;base64,BAUG'};
 const html=aiPage(ready,freshMembership());
 assert.ok(html.includes(photo));assert.ok(html.includes(ready.resultPhoto));assert.ok(!html.includes(j.sample.result));
 assert.match(html,/Your AI creation/);assert.match(html,/Use AI image/);assert.match(html,/Generate again/);assert.doesNotMatch(html,/Live photo generation is not connected|Use this sample instead|Simulate render failure/);
 const failed=aiPage({...j,status:'failed',errorCode:'credit_balance_exhausted',errorMessage:'private provider diagnostics'},freshMembership(),false,{error:'<script>bad</script>'});assert.match(failed,/&lt;script&gt;/);assert.doesNotMatch(failed,/private provider diagnostics/);
});
test('legacy demo records have a path to generate from their original upload',()=>{
 const html=aiPage({...job(),mode:'demo',status:'ready'},freshMembership());
 assert.match(html,/old demo sample/);assert.match(html,/Generate from my photo/);assert.doesNotMatch(html,/data-ai-action="apply"/);
});
test('server allowances are never refreshed from local clocks',()=>{
 const a={...freshMembership(),server:true,subscription:{anchor:1,endsAt:10,renew:true,cycle:0,used:15,monthlyLimit:15}};
 assert.deepEqual(refreshMembership(a,Date.now()),a);
});
test('AI requests carry customer session cookies',async()=>{
 const result=await aiRequest('ai-account/',{key:'a'.repeat(64),fetcher:async(url,options)=>{
  assert.equal(url,'/api/v1/store/ai-account/');assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');assert.equal(options.headers['X-Order-Key'],undefined);return {ok:true,json:async()=>({server:true})};
 }});assert.equal(result.server,true);
 await assert.rejects(()=>aiRequest('ai-account/',{key:'a'.repeat(64),retryOptions:{sleep:async()=>{}},fetcher:async()=>({ok:false,status:503,json:async()=>({detail:'Service unavailable'})})}),/after 3 retries/);
});
test('live image provenance survives a phone case order snapshot',()=>{
 const j=job();const pass=createPersonalPass({source:'photo',designId:'bloom',model:'iPhone 17',photo,effect:'original',intensity:65,zoom:100,x:50,y:50,ai:{mode:'live',styleId:j.styleId,jobId:j.id}});
 assert.equal(readPass(pass.code,structuredClone(pass)).ai.mode,'live');
});
test('active previews never substitute a sample or offer cancellation after generation starts',()=>{
 const j=job();
 const queued=aiPage({...j,status:'queued',payment:'credit_reserved'},freshMembership());
 const running=aiPage({...j,status:'generating',payment:'credit_reserved'},freshMembership());
 assert.match(queued,/Cancel &amp; return generation|Cancel & return generation/);
 assert.doesNotMatch(running,/data-ai-action="cancel"/);
 for(const html of [queued,running]){
  assert.doesNotMatch(html,/STYLE REFERENCE|data-ai-action="apply"|About \d+s|aria-valuenow="100"/);
  assert.match(html,/Estimated progress/);assert.match(html,/role="progressbar"/);
  assert.match(html,/Progress is estimated; completion is confirmed when your image arrives/);
  assert.match(html,/Creating your new look/);assert.match(html,/Usually takes around 10–20 seconds/);
 }
});
test('estimated progress is monotonic, survives reopening, and never completes a running job',()=>{
 const queued={...job(),status:'queued',paidAt:1000};
 const generating={...queued,status:'generating',startedAt:32000};
 const before=structuredClone(generating);
 assert.equal(generationProgressState(queued,1000).value,8);
 assert.equal(generationProgressState(queued,999999999).value,18);
 assert.ok(generationProgressState(generating,32000).value>18);
 let previous=0;
 for(const elapsed of [0,1000,10000,20000,30000,60000,600000]){
  const value=generationProgressState(generating,32000+elapsed).value;
  assert.ok(value>=previous&&value<=92);previous=value;
 }
 assert.deepEqual(generationProgressState(structuredClone(generating),52000),generationProgressState(generating,52000));
 assert.deepEqual(generating,before);assert.equal(canApplyAIOrder(generating),false);
});
test('100 percent requires a usable result and unsuccessful jobs do not show a meter',()=>{
 const ready={...job(),status:'ready'};
 assert.equal(generationProgressState(ready).value,96);
 assert.equal(generationProgressState({...ready,resultPhoto:photo}).value,100);
 assert.equal(generationProgressState({...ready,imageExpired:true}),null);
 for(const status of ['failed','cancelled','awaiting_confirmation']){
  const j={...job(),status};assert.equal(generationProgressState(j),null);
  assert.doesNotMatch(aiPage(j,freshMembership()),/role="progressbar"/);
 }
 assert.equal(generationProgressState({...job(),mode:'demo',status:'generating'}),null);
 assert.doesNotMatch(aiPage({...ready,resultPhoto:photo},freshMembership()),/role="progressbar"/);
});
test('missing or future timestamps never produce invalid progress or a countdown',()=>{
 for(const startedAt of [undefined,null,Infinity,NaN,999999999]){
  const j={...job(),status:'generating',startedAt,paidAt:null};
  const progress=generationProgressState(j,1000);
  assert.equal(progress.value,22);assert.equal(progress.estimated,true);
  assert.doesNotMatch(progress.message,/\d+ seconds? left/);
 }
});
test('prototype result sheet uses the actual image and keeps repeat generation separate from apply',()=>{
 const j={...job(),status:'ready',resultPhoto:photo,payment:'credit_reserved'};
 const html=aiPage(j,freshMembership());
 assert.match(html,/<dialog class="studio-render-dialog"/);
 assert.match(html,/data-ai-photo="after"/);
 assert.match(html,/data-ai-action="retry"/);assert.match(html,/data-ai-action="apply"/);
 assert.doesNotMatch(html,/data-ai-view|studio-case-pane|STYLE REFERENCE/);
 const busy=aiPage(j,freshMembership(),true,{busyAction:'apply',error:'<bad>'});
 assert.match(busy,/data-ai-action="retry" disabled/);assert.match(busy,/data-ai-action="apply" disabled/);
 assert.match(busy,/&lt;bad&gt;/);assert.match(busy,/Applying your look/);
 const loading=aiPage({...j,resultPhoto:null},freshMembership());
 assert.match(loading,/data-ai-photo="original"/);assert.match(loading,/Reload my image/);
 assert.doesNotMatch(loading,/data-ai-action="apply"|data-ai-action="retry"/);
});

test('account GET recovers from HTML 503 and stops after three retries',async()=>{
 for(const failures of [1,3,4]){
  let calls=0;const delays=[];const signals=[];
  const request=aiRequest('ai-account/',{retryOptions:{sleep:async ms=>delays.push(ms)},fetcher:async(url,options)=>{
   calls++;signals.push(options.signal);
   return calls<=failures?{ok:false,status:503,json:async()=>{throw Error('HTML maintenance page');}}:{ok:true,status:200,json:async()=>({authenticated:true})};
  }});
  if(failures===4)await assert.rejects(request,error=>error.status===503&&/after 3 retries/.test(error.message));
  else assert.equal((await request).authenticated,true);
  assert.equal(calls,Math.min(failures+1,4));
  assert.deepEqual(delays,[1000,2000,4000].slice(0,failures));
  assert.equal(new Set(signals).size,calls);
 }
});
test('account mutations and permission failures are never automatically retried',async()=>{
 for(const method of ['GET','POST']){
  let calls=0;
  await assert.rejects(aiRequest('ai-account/',{method,retryOptions:{sleep:async()=>assert.fail('must not retry')},fetcher:async url=>{
   if(url.endsWith('/csrf/'))return {ok:true,json:async()=>({csrfToken:'test'})};
   calls++;return {ok:false,status:method==='GET'?403:503,json:async()=>({detail:'Not available'})};
  }}),/Not available/);
  assert.equal(calls,1);
 }
});

test('AI confirmation opens the shared model picker only before submission',()=>{
 const pending=job(),account=freshMembership(),ui={phoneModels:['iPhone 17','iPhone 13 Pro'],stockCatalogStatus:'ready'};
 const html=aiPage(pending,account,false,ui);
 assert.match(html,/<label for="ai-phone-model">Change phone model<\/label>/);
 assert.match(html,/data-action="ai-choose-phone" aria-haspopup="dialog"/);
 assert.match(html,/iPhone 17/);
 assert.match(aiPage(pending,account,true,ui),/<button[^>]+id="ai-phone-model"[^>]+disabled/);
 assert.match(aiPage(pending,account,false,{phoneModels:[],stockCatalogStatus:'unavailable'}),/data-action="refresh-models"/);
 for(const frozen of [{...pending,submissionAttempted:true},{...pending,remoteId:'known'},{...pending,status:'queued'},{...pending,status:'ready'}]){
  assert.doesNotMatch(aiPage(frozen,account,false,ui),/id="ai-phone-model"/);
 }
});

test('camera-aware renders freeze template and material and preserve the full generated photo',async t=>{
 const draft=createLiveRender({photo,styleId:'anime',exampleId:'portrait',model:'iPhone 17',phoneTemplateId:'iphone-17-a-v1',caseMaterial:'magnetic'});
 let submitted;
 t.mock.method(globalThis,'fetch',async(url,options)=>{
  if(url.endsWith('csrf/'))return {ok:true,json:async()=>({csrfToken:'fixture'})};
  submitted=JSON.parse(options.body);
  return {ok:true,json:async()=>({...response(draft),composition:{version:1,fit:'blur',model:'iPhone 17',template_id:'iphone-17-a-v1',case_material:'magnetic'}})};
 });
 assert.throws(()=>mergeLiveRender(draft,{...response(draft),composition:{version:1,fit:'blur',model:'iPhone 17',template_id:'other-template',case_material:'magnetic'}}),/different case/);
 const job=await submitLiveRender(draft,true);
 assert.equal(submitted.phone_template_id,'iphone-17-a-v1');
 assert.equal(submitted.case_material,'magnetic');
 assert.deepEqual(generatedPhotoPlacement(job),{x:50,y:50,scale:100,rotation:0,fit:'blur'});
 assert.equal(generatedPhotoPlacement({...job,composition:null}),null);
});
