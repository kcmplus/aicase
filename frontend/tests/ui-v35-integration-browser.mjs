// Run through scripts/test_v35_dev_browser.py: synthetic data and fresh browser contexts.
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE?pathToFileURL(process.env.PLAYWRIGHT_MODULE).href:'playwright');
const origin=process.env.PREVIEW_URL,model=process.env.TEST_MODEL,order=process.env.TEST_ORDER;
assert(origin&&model&&order,'Use the disposable fixture runner.');
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
await mkdir('test-results/v35-integration',{recursive:true});
try{
 for(const [width,height] of [[320,568],[390,844],[768,1024],[1440,900]]){
  if(process.env.TEST_VIEWPORT_WIDTH&&width!==Number(process.env.TEST_VIEWPORT_WIDTH))continue;
  const context=await browser.newContext({viewport:{width,height},serviceWorkers:'block'}),errors=[],writes=[];
  // Both frontend and backend have independent outbound guards. This browser may
  // read only its fixture origin; payment/dispatch/print writes are forbidden.
  await context.route('**/*',route=>{
   const req=route.request(),url=new URL(req.url());
   if(url.origin!==origin||!['GET','HEAD'].includes(req.method())){writes.push(req.method()+' '+url.pathname);return route.abort();}
   if(url.pathname==='/__ai_fixture')return route.fulfill({contentType:'text/html',body:'<!doctype html><html><body>Isolated local draft fixture</body></html>'});
   return route.continue();
  });
  await context.addInitScript(()=>localStorage.setItem('popomo-order-access-v1','a'.repeat(64)));
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto(origin+'/#home');
  await page.locator('[data-action="home-photo"]').waitFor();
  assert.match(await page.locator('#v35-hero-title').innerText(),/A little imagination/);
  const entries=await page.locator('.v35-entries').evaluate(el=>[...el.children].map(c=>c.getBoundingClientRect().toJSON()));
  if(width<=760){assert.equal(entries[0].top,entries[1].top);assert(entries[2].top>=entries[0].bottom);assert(entries[2].width>entries[0].width*1.9);}
  await page.screenshot({path:`test-results/v35-integration/${width}-home.png`});
  if(width===390){
   const phone=await page.locator('.v35-fan-case').nth(2).boundingBox();
   await page.mouse.move(phone.x+phone.width/2,phone.y+60);await page.mouse.down();
   await page.mouse.move(phone.x+phone.width/2-70,phone.y+60,{steps:6});await page.mouse.up();
   assert.equal(await page.locator('.v35-fan').getAttribute('data-step'),'1','Drag rotates inspiration without launching AI');
   assert.equal(await page.locator('.v35-home-phone').count(),0);
   await page.locator('[data-shell-fan="-1"]').click();
   const catalogPattern='**/api/v1/store/phone-models/**';
   await context.route(catalogPattern,route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
   await page.reload();await page.locator('[data-action="home-photo"]').click();
   assert(await page.locator('#home-phone-model').isDisabled(),'Failed catalog never falls back to static sale models');
   assert(await page.locator('[data-home-confirm]').isDisabled());
   await context.unroute(catalogPattern);
   await page.locator('[data-home-retry]').click();
   await page.waitForFunction(()=>document.querySelector('#home-phone-model')?.disabled===false);
   await page.keyboard.press('Escape');await page.locator('.v35-home-phone').waitFor({state:'detached'});
  }

  await page.locator('[data-action="home-photo"]').click();
  await page.locator('.v35-home-phone[open]').waitFor();
  assert(await page.locator('[data-home-confirm]').isDisabled(),'Model and style must be explicitly chosen');
  await page.keyboard.press('Escape');
  await page.locator('.v35-home-phone').waitFor({state:'detached'});
  assert.equal(await page.locator('.v35-home-phone').count(),0);
  assert.equal(await page.evaluate(()=>document.activeElement.dataset.action),'home-photo');
  await page.locator('[data-action="home-photo"]').click();
  await page.locator('#home-phone-model').selectOption(model);
  assert(await page.locator('[data-home-confirm]').isDisabled(),'Selecting a model alone does not select a case style');
  await page.locator('[data-home-material="standard"]').click();
  await page.locator('[data-home-color="synthetic-blue"][aria-pressed="true"]').waitFor();
  await page.screenshot({path:`test-results/v35-integration/${width}-home-picker.png`});
  const modal=await page.locator('.v35-home-phone').boundingBox();
  assert(modal.x>=0&&modal.y>=0&&modal.x+modal.width<=width&&modal.y+modal.height<=height,'Modal stays in viewport');
  assert(await page.locator('[data-home-confirm]').isVisible(),'Footer stays reachable in a short viewport');
  await page.locator('[data-home-material="magnetic"]').click();
  assert.equal(await page.locator('[data-home-color]').count(),0,'Unconfigured style hides body colors in onboarding too');
  await page.locator('[data-home-material="standard"]').click();
  const photoBytes=await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=64;canvas.height=128;const ctx=canvas.getContext('2d');ctx.fillStyle='#3951af';ctx.fillRect(0,0,64,128);return canvas.toDataURL().split(',')[1];});
  const chooser=page.waitForEvent('filechooser');
  await page.locator('[data-home-confirm]').click();
  await (await chooser).setFiles({name:'synthetic.png',mimeType:'image/png',buffer:Buffer.from(photoBytes,'base64')});
  await page.locator('.v35-editor').waitFor();
  await page.locator('[data-case-material="standard"][aria-pressed="true"]').waitFor();
  await page.locator('[data-phone-color="synthetic-blue"][aria-pressed="true"]').waitFor();
  await page.goto(origin+'/#home');
  await page.locator('.v35-entries [data-action="home-ai"]').click();
  assert.equal(await page.locator('#home-phone-model').inputValue(),model);
  await page.locator('[data-home-confirm]').click();
  await page.locator('.look-browser[open]').waitFor();
  await page.keyboard.press('Escape');
  await page.goto(origin+'/#choose?design=bloom');
  await page.locator('.model-first summary').waitFor();
  if(!await page.locator('[data-phone-model]').first().isVisible())await page.locator('.model-first summary').click();
  await page.locator('[data-phone-model]').first().waitFor();
  await page.locator('[data-phone-model]').filter({hasText:model}).click();
  await page.locator('[data-case-material="standard"]').click();
  await page.locator('[data-phone-color="synthetic-blue"]').waitFor();
  assert.equal(await page.locator('[data-phone-color="synthetic-blue"]').getAttribute('aria-pressed'),'true');
  await page.locator('[data-case-material="magnetic"]').click();
  assert.equal(await page.locator('[data-phone-color]').count(),0,'Unconfigured style skips colors');
  await page.locator('[data-case-material="standard"]').click();
  await page.locator('#design-form button').click();
  await page.locator('[data-action="save-local-design"]').waitFor();
  assert.equal(new URL(page.url()).hash,'#review');
  assert.equal(await page.locator('dialog.v35-design-review').count(),0,'Review is a page, not an extra dialog');
  await page.reload();
  await page.locator('.v35-review-summary').waitFor().catch(async error=>{console.error({width,url:page.url(),errors,text:await page.locator('body').innerText()});throw error;});
  assert.match(await page.locator('.v35-review-summary').innerText(),/1 case/);
  assert.match(await page.locator('.v35-review-summary').innerText(),/Standard/);
  assert.match(await page.locator('.v35-review-summary').innerText(),/Synthetic blue/);
  const reviewGeometry=await page.locator('.v35-review-case').evaluate(stage=>({stage:stage.getBoundingClientRect().toJSON(),phone:stage.querySelector('.phone-case').getBoundingClientRect().toJSON()}));
  assert(reviewGeometry.phone.height>=200&&reviewGeometry.stage.height<=500,'Review phone has a readable, bounded size');
  assert.equal(await page.locator('.v35-design-steps ol').evaluate(el=>getComputedStyle(el).display),'flex','Journey steps appear in a horizontal row');
  assert(reviewGeometry.phone.top>=reviewGeometry.stage.top&&reviewGeometry.phone.bottom<=reviewGeometry.stage.bottom,'Review phone fits vertically');
  assert(reviewGeometry.phone.left>=reviewGeometry.stage.left&&reviewGeometry.phone.right<=reviewGeometry.stage.right,'Review phone fits horizontally');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Review never scrolls horizontally');
  await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,document.body.scrollHeight);});
  await page.screenshot({path:`test-results/v35-integration/${width}-review.png`,fullPage:true});
  await page.goBack();
  await page.locator('.v35-editor').waitFor();
  await page.goForward();
  await page.locator('.v35-review-summary').waitFor().catch(async error=>{console.error({width,url:page.url(),errors,text:await page.locator('body').innerText()});throw error;});
  assert.match(await page.locator('.v35-review-summary').innerText(),/Synthetic blue/);
  if(width===390){
   await page.locator('.v35-design-steps a[href="#choose?step=model"]').click();
   await page.locator('.model-first[open]').waitFor();
   await page.locator('.model-first summary').click();
   await page.locator('#design-form button').click();
   await page.locator('.v35-review-summary').waitFor().catch(async error=>{console.error({width,url:page.url(),errors,text:await page.locator('body').innerText()});throw error;});
  }

  await page.locator('[data-action="save-local-design"]').click();
  await page.locator('[data-action="close-design-review"]').first().click();
  await page.reload();
  await page.locator('[data-case-material="standard"][aria-pressed="true"]').waitFor();
  await page.locator('[data-phone-color="synthetic-blue"][aria-pressed="true"]').waitFor();
  await page.locator('#design-form button').click();
  await page.locator('[data-action="continue-design-checkout"]').click();
  await page.locator('.v35-checkout .pickup-station-row').waitFor();
  const previewGeometry=await page.locator('.checkout-preview').evaluate(card=>{
   const stage=card.querySelector('.checkout-case'),phone=stage.querySelector('.phone-case'),title=card.querySelector('h2');
   const box=element=>element.getBoundingClientRect().toJSON();
   return {card:box(card),stage:box(stage),phone:box(phone),title:box(title),ratio:getComputedStyle(phone).aspectRatio};
  });
  assert(previewGeometry.stage.width>=previewGeometry.card.width-3,'Preview stage must span the card instead of inheriting the legacy thumbnail column');
  assert(previewGeometry.phone.height>=200&&previewGeometry.phone.width>=90,'Design must be large enough to review');
  assert(previewGeometry.phone.top>=previewGeometry.stage.top&&previewGeometry.phone.bottom<=previewGeometry.stage.bottom,'Whole phone must fit vertically');
  assert(previewGeometry.phone.left>=previewGeometry.stage.left&&previewGeometry.phone.right<=previewGeometry.stage.right,'Whole phone must fit horizontally');
  assert(Math.abs(previewGeometry.phone.x+previewGeometry.phone.width/2-previewGeometry.stage.x-previewGeometry.stage.width/2)<2,'Phone must be centered');
  assert(previewGeometry.title.top>=previewGeometry.stage.bottom,'Design title belongs below the preview');
  const [rw,rh]=previewGeometry.ratio.split('/').map(Number);
  assert(Math.abs(previewGeometry.phone.width/previewGeometry.phone.height-rw/rh)<.01,'Preserve template proportions');
  await page.screenshot({path:`test-results/v35-integration/${width}-checkout.png`,fullPage:true});
  assert.match(await page.locator('.pickup-station-row').innerText(),/Synthetic preview station/);
  await page.goto(origin+'/#orders');
  await page.locator('.v35-orders .order-row').waitFor();
  assert.match(await page.locator('.order-row').innerText(),/Standard/);
  await page.locator('[data-action="view-order"]').click();
  await page.locator('[data-active-order="'+order+'"] .order-progress').waitFor();
  await page.screenshot({path:`test-results/v35-integration/${width}-order.png`});
  await page.goto(origin+'/?device_id=101&shop_id=999#choose?design=bloom');
  await page.locator('.v35-editor').waitFor();
  await page.locator('.v35-header .v35-wordmark').click();
  await page.locator('[data-action="home-photo"]').click();
  await page.locator('#home-phone-model').selectOption(model);
  assert(await page.locator('[data-home-material="magnetic"]').isDisabled(),'Onboarding respects the scanned station inventory');
  await page.keyboard.press('Escape');
  await page.goto(origin+'/?device_id=101&shop_id=999#choose?design=bloom');
  await page.locator('.model-first summary').waitFor();
  if(!await page.locator('[data-phone-model]').first().isVisible())await page.locator('.model-first summary').click();
  await page.locator('[data-phone-model]').filter({hasText:model}).click();
  assert.equal(await page.locator('[data-case-material="magnetic"]').isDisabled(),true,'Scanned device must disable out-of-stock style');
  await page.locator('[data-case-material="standard"]').click();
  await page.locator('[data-phone-color="synthetic-blue"]').waitFor();
  await page.screenshot({path:`test-results/v35-integration/${width}-editor.png`});
  // Seed on a page without the app, so a concurrent navigation cannot overwrite the fixture.
  // A guest may prepare a local AI draft; selecting a model must never submit it.
  await page.goto(origin+'/__ai_fixture');
  const aiFixture=await page.evaluate(async model=>{
   const {createLiveRender}=await import('/ai-service.js');
   const {readDesign,writeDesign}=await import('/simple-storage.js');
   const {createDesignWorkspace}=await import('/design-workspace.js');
   const identity=await (await fetch('/api/v1/store/ai-account/')).json();
   const workspace=createDesignWorkspace(identity,{read:readDesign,write:writeDesign});
   const canvas=document.createElement('canvas');canvas.width=24;canvas.height=32;
   canvas.getContext('2d').fillRect(0,0,24,32);
   const job=createLiveRender({photo:canvas.toDataURL(),styleId:'anime',exampleId:'portrait',model});
   const membership=await workspace.read('ai-membership-v1');
   await workspace.write('ai-membership-v1',{...membership,jobs:{...membership.jobs,[job.id]:job}});
   const editor=JSON.parse(localStorage.getItem(workspace.key('editor'))||'{}');
   localStorage.setItem(workspace.key('editor'),JSON.stringify({...editor,model,aiJobId:job.id}));
   const catalog=await (await fetch('/api/v1/store/phone-models/')).json();
   return {id:job.id,photo:job.photo,model:catalog.models.find(item=>item.name!==model).name};
  },model);
  await page.goto(origin+'/#ai');
  await page.locator('#ai-phone-model').waitFor().catch(async error=>{console.error({width,url:page.url(),errors,text:await page.locator('body').innerText()});throw error;});
  await page.locator('#ai-phone-model').selectOption(aiFixture.model);
  await page.waitForFunction(model=>!document.querySelector('#ai-phone-model')?.disabled&&JSON.parse(localStorage.getItem('v35:guest:editor')||'{}').model===model,aiFixture.model);
  await page.reload();
  await page.locator('#ai-phone-model').waitFor().catch(async error=>{console.error({width,url:page.url(),errors,text:await page.locator('body').innerText()});throw error;});
  assert.equal(await page.locator('#ai-phone-model').inputValue(),aiFixture.model);
  const savedAI=await page.evaluate(async()=>{const {readDesign}=await import('/simple-storage.js');const editor=JSON.parse(localStorage.getItem('v35:guest:editor'));return (await readDesign('v35:guest:ai-membership-v1')).jobs[editor.aiJobId];});
  assert.equal(savedAI.id,aiFixture.id);assert.equal(savedAI.photo,aiFixture.photo);assert.equal(savedAI.styleId,'anime');assert.equal(savedAI.model,aiFixture.model);
  const selectBox=await page.locator('#ai-phone-model').boundingBox();assert(selectBox.width>150&&selectBox.x>=0&&selectBox.x+selectBox.width<=width,'Model picker fits the viewport');
  await page.screenshot({path:`test-results/v35-integration/${width}-ai-model.png`,fullPage:true});
  assert.deepEqual(errors,[],'No browser exceptions');assert.deepEqual(writes,[],'No external requests or financial/hardware writes');
  console.log('PASS merged editor/catalog/colors/local save/checkout stations/order detail/scanned stock/AI model change',width,height);
  await context.close();
 }
}finally{await browser.close();}
