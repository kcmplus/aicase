import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const {chromium}=createRequire(import.meta.url)('C:/Users/53671/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const browser=await chromium.launch({headless:true,channel:'msedge'});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const base='http://127.0.0.1:4173/',errors=[];
page.on('pageerror',e=>errors.push(e.message));
let checks=0;
const check=async(name,fn)=>{await fn();checks++;console.log('PASS '+name);};
const modal=()=>page.locator('#content-dialog');
const card=id=>page.locator('.content-card').filter({has:page.locator('.content-title[data-id="'+id+'"]')});
const toggle=(scope,action)=>scope.locator('[data-social="'+action+'"]').first();
const pressed=async(scope,action,value)=>assert.equal(await toggle(scope,action).getAttribute('aria-pressed'),String(value));
const hasText=text=>page.locator('.social-comment').filter({hasText:text});
async function goto(hash,lang='zh-CN'){
 await page.goto(base+'?lang='+lang+'#'+hash);
 await page.locator('#main').waitFor();
}
async function openPost(id){
 await page.locator('.content-title[data-social=open][data-id="'+id+'"]').click();
 await page.waitForFunction(()=>document.querySelector('#content-dialog')?.open);
}
async function closePost(){
 if(await modal().evaluate(el=>el.open).catch(()=>false)){
  await modal().locator('[data-social=close]').click();
  await page.waitForFunction(()=>!document.querySelector('#content-dialog')?.open);
 }
}
async function login(email){
 if(!await page.locator('#account-dialog').evaluate(el=>el.open))await page.locator('.account-button').click();
 await page.locator('#email').fill(email);
 if(!await page.locator('#default-model').isDisabled())await page.locator('#default-model').selectOption('iPhone 16 Pro');
 await page.locator('#account-form button[type=submit]').click();
 await page.waitForFunction(()=>!document.querySelector('#account-dialog').open);
}
async function logout(){
 await closePost();
 await page.locator('.account-button').click();
 await page.locator('#account-dialog [data-logout]').click();
 await page.waitForFunction(()=>!document.querySelector('#account-dialog').open);
}
async function submitComment(text){
 await modal().locator('#social-comment-form textarea[name=comment]').fill(text);
 await modal().locator('#social-comment-form [type=submit]').click();
 await hasText(text).last().waitFor();
}
const noOverflow=async(label)=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,label+' horizontal overflow');

try{
 await goto('discover');
 const firstId=await page.locator('.content-title[data-social=open]').first().getAttribute('data-id');
 assert.ok(firstId,'Feed titles expose a stable content ID');
 await check('discovery retains case catalog and exposes social navigation',async()=>{
  assert.equal(await page.locator('.content-card').count(),24);
  for(const feed of ['all','following','saved'])assert.ok(await page.locator('a[href="#discover?feed='+feed+'"]').count());
  assert.equal(await card(firstId).locator('.social-like').count(),1);
  assert.equal(await card(firstId).locator('.social-save').count(),1);
 });
 await check('canceling guest sign-in discards the pending like',async()=>{
  await toggle(card(firstId),'like').click();
  await page.locator('#account-dialog[open]').waitFor();
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>!document.querySelector('#account-dialog').open);
  await login('social-a@example.com');
  await pressed(card(firstId),'like',false);
 });
 await check('browser Back cancels sign-in and its abandoned social action',async()=>{
  await logout();await openPost(firstId);await toggle(modal(),'like').click();
  await page.locator('#account-dialog[open]').waitFor();await page.goBack();
  await page.waitForFunction(()=>!document.querySelector('#content-dialog')?.open&&!document.querySelector('#account-dialog').open);
  await login('social-a@example.com');await pressed(card(firstId),'like',false);
 });
 await check('guest sign-in resumes the requested like once',async()=>{
  await logout();
  await toggle(card(firstId),'like').click();
  await login('social-a@example.com');
  await pressed(card(firstId),'like',true);
  await page.reload();await page.locator('#main').waitFor();
  await pressed(card(firstId),'like',true);
  await toggle(card(firstId),'like').click();await pressed(card(firstId),'like',false);
  await toggle(card(firstId),'like').click();await pressed(card(firstId),'like',true);
 });
 await check('detail overlay synchronizes like save and creator follow',async()=>{
  await openPost(firstId);
  assert.match(await page.evaluate(()=>location.hash),/post=/);
  await pressed(modal(),'like',true);
  await toggle(modal(),'save').click();await pressed(modal(),'save',true);
  await toggle(modal(),'follow').click();await pressed(modal(),'follow',true);
  await closePost();await pressed(card(firstId),'save',true);
 });
 const authorId=await card(firstId).locator('.content-author').getAttribute('href').then(h=>new URLSearchParams(h.split('?')[1]).get('id'));
 await check('saved and following feeds filter content and profile follows stay synchronized',async()=>{
  await page.locator('a[href="#discover?feed=saved"]').first().click();
  await page.waitForFunction(()=>location.hash==='#discover?feed=saved');
  assert.equal(await page.locator('.content-card').count(),1);
  assert.equal(await page.locator('.content-title').first().getAttribute('data-id'),firstId);
  await page.locator('a[href="#discover?feed=following"]').first().click();
  await page.waitForFunction(()=>location.hash==='#discover?feed=following');
  assert.ok(await page.locator('.content-card').count());
  assert.ok((await page.locator('.content-card .content-author').evaluateAll(els=>els.map(el=>el.getAttribute('href')))).every(h=>h==='#creator?id='+authorId));
  await goto('creator?id='+authorId);
  await pressed(page.locator('.creator-profile'),'follow',true);
  await toggle(page.locator('.creator-profile'),'follow').click();
  await goto('discover?feed=following');
  assert.equal(await page.locator('.content-card').count(),0);
  await goto('creator?id='+authorId);await toggle(page.locator('.creator-profile'),'follow').click();
 });
 await goto('discover');await openPost(firstId);
 const unsafe='<img src=x onerror=window.__socialXss=1> 我喜欢这个设计';
 let ownCommentId;
 await check('comments validate empty input and render markup literally',async()=>{
  const input=modal().locator('#social-comment-form textarea[name=comment]');
  assert.equal(await input.getAttribute('maxlength'),'300');
  await input.fill('   ');await modal().locator('#social-comment-form [type=submit]').click();
  assert.equal(await modal().locator('.social-comment').count(),0);
  await submitComment(unsafe);
  ownCommentId=await hasText(unsafe).last().getAttribute('data-comment-id');
  assert.ok(ownCommentId);
  assert.equal(await modal().locator('img[src=x]').count(),0);
  assert.equal(await page.evaluate(()=>window.__socialXss),undefined);
  assert.equal(await input.inputValue(),'');
 });
 await check('comments support replies and deleting your own reply',async()=>{
  await modal().locator('[data-social=reply][data-comment-id="'+ownCommentId+'"]').click();
  await submitComment('回复：我准备加入自己的名字。');
  const reply=hasText('回复：我准备加入自己的名字。').last();
  const replyId=await reply.getAttribute('data-comment-id');
  assert.notEqual(replyId,ownCommentId);
  await modal().locator('[data-social=delete][data-comment-id="'+replyId+'"]').click();
  assert.equal(await hasText('回复：我准备加入自己的名字。').count(),0);
  assert.equal(await modal().locator('.social-comment[data-comment-id="'+ownCommentId+'"]').count(),1);
 });
 await check('a deleted comment preserves existing replies without offering an unusable reply action',async()=>{
  await submitComment('临时主评论');const rootId=await hasText('临时主评论').last().getAttribute('data-comment-id');
  await modal().locator('[data-social=reply][data-comment-id="'+rootId+'"]').click();await submitComment('保留的临时回复');
  const childId=await hasText('保留的临时回复').last().getAttribute('data-comment-id');
  await modal().locator('[data-social=delete][data-comment-id="'+rootId+'"]').click();
  assert.ok(await hasText('保留的临时回复').count());
  assert.equal(await modal().locator('[data-social=reply][data-comment-id="'+childId+'"]:enabled').count(),0);
  await modal().locator('[data-social=delete][data-comment-id="'+childId+'"]').click();
  assert.equal(await modal().locator('.social-comment[data-comment-id="'+rootId+'"]').count(),0);
 });
 await check('switching accounts isolates social toggles and comment deletion permission',async()=>{
  await logout();await login('social-b@example.com');
  await pressed(card(firstId),'like',false);await pressed(card(firstId),'save',false);
  await openPost(firstId);await pressed(modal(),'follow',false);
  assert.equal(await modal().locator('.social-comment[data-comment-id="'+ownCommentId+'"]').count(),1);
  assert.equal(await modal().locator('[data-social=delete][data-comment-id="'+ownCommentId+'"]').count(),0);
  await submitComment('Another local demo account can join the conversation.');
  await logout();await login('social-a@example.com');
  await pressed(card(firstId),'like',true);await pressed(card(firstId),'save',true);
  await openPost(firstId);await pressed(modal(),'follow',true);
  assert.equal(await modal().locator('[data-social=delete][data-comment-id="'+ownCommentId+'"]').count(),1);
  assert.ok(await hasText('Another local demo account can join the conversation.').count());
 });
 await closePost();await goto('discover');
 await check('Escape and browser history restore the feed position and focus',async()=>{
  const title=page.locator('.content-title[data-social=open]').nth(15);
  const id=await title.getAttribute('data-id');
  await title.scrollIntoViewIfNeeded();const beforeY=await page.evaluate(()=>scrollY);
  await title.click();await page.waitForFunction(()=>document.querySelector('#content-dialog')?.open);
  await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#content-dialog')?.open);
  assert.ok(Math.abs(await page.evaluate(()=>scrollY)-beforeY)<4,'Escape restores scroll position');
  assert.equal(await page.evaluate(()=>document.activeElement?.dataset.id),id);
  await openPost(id);await page.goBack();
  await page.waitForFunction(()=>!document.querySelector('#content-dialog')?.open);
  assert.ok(Math.abs(await page.evaluate(()=>scrollY)-beforeY)<4,'Back restores scroll position');
  await page.goForward();await page.waitForFunction(()=>document.querySelector('#content-dialog')?.open);
  assert.match(await page.evaluate(()=>location.hash),new RegExp('post='+id));
  await closePost();
 });
 await check('direct details retain social controls and content enters the DIY studio',async()=>{
  await goto('content?id='+firstId);await pressed(page.locator('#main'),'like',true);
  assert.equal(await page.locator('#main [data-social=save]').count(),1);
  await page.locator('#main [data-creator=use]').click();await page.waitForURL(/#studio$/);
  assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('ai-case-studio-v1')).design.source.contentId),firstId);
  await goto('discover');await page.locator('[data-creator=filter][data-type=photo]').click();
  const photoId=await page.locator('.content-title').first().getAttribute('data-id');
  await openPost(photoId);await modal().locator('[data-creator=use]').click();await page.waitForURL(/#studio$/);
  assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('ai-case-studio-v1')).design.layers.at(-1).source.contentId),photoId);
 });
 await check('discovery and modal fit both languages on phone tablet and desktop',async()=>{
  for(const lang of ['zh-CN','en-US'])for(const width of [360,390,768,1440]){
   await page.setViewportSize({width,height:950});await goto('discover',lang);await page.locator('[data-creator=filter][data-type=case]').click();await noOverflow(lang+' '+width+' feed');
   await openPost(firstId);await noOverflow(lang+' '+width+' detail');
   const box=await modal().boundingBox();assert.ok(box.x>=-1&&box.x+box.width<=width+1,'Dialog fits width');
   assert.ok(box.y>=-1&&box.y+box.height<=951,'Dialog fits height');
   if(lang==='en-US'){
    const chromeText=await modal().locator('[data-social=follow],#social-comment-form,[data-social=close]').allTextContents();
    assert.equal(chromeText.some(t=>/[\u3400-\u9fff]/.test(t)),false,'Social UI is localized; user comments stay original');
   }
   await closePost();
  }
 });
 await check('mobile social actions preserve the scrolled detail position',async()=>{
  await page.setViewportSize({width:390,height:844});await goto('discover');await page.locator('[data-creator=filter][data-type=case]').click();await openPost(firstId);
  await modal().locator('.social-detail-layout').evaluate(el=>{el.scrollTop=150;});
  const before=await modal().locator('.social-detail-layout').evaluate(el=>el.scrollTop);
  assert.ok(before>0,'The mobile detail can be scrolled');
  await toggle(modal(),'like').click();
  assert.ok(Math.abs(await modal().locator('.social-detail-layout').evaluate(el=>el.scrollTop)-before)<3,'Like retains mobile detail scroll');
  await toggle(modal(),'like').click();await closePost();
 });
 // Keep exported review screenshots human-readable after the security fixtures.
 await goto('discover');await openPost(firstId);
 await modal().locator('[data-social=delete][data-comment-id="'+ownCommentId+'"]').click();
 await logout();await login('social-b@example.com');await openPost(firstId);
 const secondCommentId=await hasText('Another local demo account can join the conversation.').last().getAttribute('data-comment-id');
 await modal().locator('[data-social=delete][data-comment-id="'+secondCommentId+'"]').click();
 await logout();await login('social-a@example.com');await openPost(firstId);
 await submitComment('喜欢花朵和青色的搭配，准备加上自己的名字。');
 const friendlyId=await hasText('喜欢花朵和青色的搭配，准备加上自己的名字。').last().getAttribute('data-comment-id');
 await modal().locator('[data-social=reply][data-comment-id="'+friendlyId+'"]').click();
 await submitComment('把今天的小灵感，变成每天带在身边的手机壳。');
 await closePost();
 await page.setViewportSize({width:1440,height:1000});await goto('discover');await page.locator('[data-creator=filter][data-type=case]').click();
 await page.screenshot({path:'test-results/social-desktop.png',fullPage:true});await openPost(firstId);
 await page.screenshot({path:'test-results/social-detail-desktop.png'});await closePost();
 await page.setViewportSize({width:390,height:844});await goto('discover');
 await page.screenshot({path:'test-results/social-mobile.png',fullPage:true});await openPost(firstId);
 await page.screenshot({path:'test-results/social-detail-mobile.png'});
 await check('social flows produce no JavaScript errors',async()=>assert.deepEqual(errors,[]));
 fs.writeFileSync('test-results/social-results.json',JSON.stringify({checks,errors,at:new Date().toISOString()},null,2));
 console.log(checks+' social browser checks passed');
}finally{await browser.close();}
