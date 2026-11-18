import test from 'node:test';
import assert from 'node:assert/strict';
import {customerRequest,customerPage,startSocialLogin,socialReturnMessage} from '../storefront/customer-account.js';
import {credits} from '../storefront/ai-membership.js';
import {aiRequest} from '../storefront/ai-service.js';

test('social sign-in shows only configured providers and pending verification keeps email flow',()=>{
 const guest={authenticated:false,signupCredits:8,emailEnabled:true};
 assert.doesNotMatch(customerPage(guest,{}),/data-customer-action="social-/);
 const page=customerPage({...guest,socialProviders:['google','facebook','unknown']},{});
 assert.match(page,/social-google/);assert.match(page,/social-facebook/);assert.doesNotMatch(page,/social-unknown/);
 assert.match(page,/8 <span>AI creations/);
 const pending=customerPage({...guest,socialProviders:['google'],socialPending:{provider:'google',email:'a@example.com'}},{});
 assert.doesNotMatch(pending,/data-customer-action="social-google"/);assert.match(pending,/Verify your email once/);assert.match(pending,/cancel-social/);
 const disabled=customerPage({...guest,emailEnabled:false},{});
 assert.match(disabled,/type="submit" disabled/);assert.match(disabled,/Email sign-in is temporarily unavailable/);
});

test('social start protects CSRF, limits return context and rejects non-provider redirects',async()=>{
 const fetcher=authorizationUrl=>async(url,options)=>{
  assert.equal(options.credentials,'same-origin');
  if(url.endsWith('csrf/'))return {ok:true,json:async()=>({csrfToken:'csrf'})};
  assert.equal(url,'/api/v1/store/customer/social/google/start/');
  assert.equal(options.headers['X-CSRFToken'],'csrf');
  assert.deepEqual(JSON.parse(options.body),{next:'choose',language:'en-US',device_id:'789'});
  return {ok:true,json:async()=>({authorizationUrl})};
 };
 const context={next:'https://attacker.example',search:'?device_id=789&shop_id=invalid&email=private@example.com'};
 const good='https://accounts.google.com/o/oauth2/v2/auth?state=test';
 assert.equal(await startSocialLogin('google',{...context,fetcher:fetcher(good)}),good);
 for(const url of ['https://attacker.example/','https://accounts.google.com.evil.example/o/oauth2/v2/auth','http://accounts.google.com/o/oauth2/v2/auth','https://accounts.google.com:8443/o/oauth2/v2/auth','https://user:pass@accounts.google.com/o/oauth2/v2/auth']){
  await assert.rejects(startSocialLogin('google',{...context,fetcher:fetcher(url)}),/unavailable/);
 }
 await assert.rejects(startSocialLogin('unknown'),/unavailable/);
 assert.equal(socialReturnMessage('<script>private</script>'),'');
 assert.match(socialReturnMessage('cancelled'),/cancelled/);
});

test('guest cannot claim local trial credits and registered allowance is server-owned',()=>{
 assert.equal(credits({server:true,authenticated:false,trialRemaining:20}).trial,0);
 assert.equal(credits({server:true,authenticated:true,trialRemaining:2,trialCount:0}).trial,2);
 const page=customerPage({authenticated:false,signupCredits:3},{email:'"><script>alert(1)</script>',codeSent:false});
 assert.match(page,/A welcome gift for you/);assert.match(page,/3 <span>AI creations/);assert.doesNotMatch(page,/<script>/);
});
test('email sign-in and AI mutations include CSRF and session cookies',async()=>{
 for(const send of [fetcher=>customerRequest('verify/',{method:'POST',body:{code:'123456'},fetcher}),fetcher=>aiRequest('ai-renders/',{method:'POST',body:{accepted:true},key:'a'.repeat(64),fetcher})]){
  const calls=[];await send(async(url,options)=>{calls.push(url);assert.equal(options.credentials,'same-origin');if(url.endsWith('csrf/'))return {ok:true,json:async()=>({csrfToken:'csrf-token'})};assert.equal(options.headers['X-CSRFToken'],'csrf-token');return {ok:true,json:async()=>({})};});
  assert.equal(calls.length,2);assert.equal(calls[0],'/api/v1/auth/csrf/');
 }
});
test('expired codes show server feedback and email values remain escaped',async()=>{
 await assert.rejects(customerRequest('',{fetcher:async()=>({ok:false,status:400,json:async()=>({detail:'Code expired'})})}),/Code expired/);
 const page=customerPage({authenticated:true,customer:{email:'<b>@example.com'},trialRemaining:2},{next:'choose'});
 assert.match(page,/&lt;b&gt;@example.com/);assert.match(page,/Sign out/);assert.doesNotMatch(page,/customer-email-form/);
});

test('signed-in profile shows server balances and escapes names without exposing staff fields',()=>{
 const page=customerPage({server:true,authenticated:true,customer:{email:'hello@example.com',displayName:'<script>bad()</script>',joinedAt:'2026-10-29T01:00:00Z'},trialRemaining:7,subscription:{endsAt:Date.now()+3600000,used:2,monthlyLimit:10}},{});
 assert.match(page,/customer-profile-form/);assert.match(page,/Gift credits remaining/);assert.match(page,/>7<\/strong>/);assert.match(page,/>8<\/strong>/);
 assert.match(page,/Joined/);assert.doesNotMatch(page,/<script>/);assert.doesNotMatch(page,/name="(?:email|active|notes)"/);
});

test('credit activity shows pool, signed changes and balance without rendering private reasons',()=>{
 const page=customerPage({authenticated:true,customer:{email:'test@example.com'},trialRemaining:2},{ledgerOpen:true,ledger:[{id:1,kind:'grant',pool:'gift',amount:3,balanceAfter:4,createdAt:'2026-10-29T08:00:00Z',reason:'PRIVATE STAFF NOTE',actorName:'private-admin',renderId:'<script>bad()</script>'}],ledgerNext:1});
 assert.match(page,/Credit history/);assert.match(page,/Extra credits/);assert.match(page,/>\+3</);assert.match(page,/>Balance<\/span> 4/);assert.match(page,/Load earlier activity/);assert.doesNotMatch(page,/PRIVATE STAFF NOTE|private-admin|<script>/);
});
