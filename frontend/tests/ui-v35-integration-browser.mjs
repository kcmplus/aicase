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
  const context=await browser.newContext({viewport:{width,height},serviceWorkers:'block'}),errors=[],writes=[];
  // Both frontend and backend have independent outbound guards. This browser may
  // read only its fixture origin; payment/dispatch/print writes are forbidden.
  await context.route('**/*',route=>{
   const req=route.request(),url=new URL(req.url());
   if(url.origin!==origin||!['GET','HEAD'].includes(req.method())){writes.push(req.method()+' '+url.pathname);return route.abort();}
   return route.continue();
  });
  await context.addInitScript(()=>localStorage.setItem('popomo-order-access-v1','a'.repeat(64)));
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto(origin+'/#choose?design=bloom');
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
  await page.locator('.model-first summary').waitFor();
  if(!await page.locator('[data-phone-model]').first().isVisible())await page.locator('.model-first summary').click();
  await page.locator('[data-phone-model]').filter({hasText:model}).click();
  assert.equal(await page.locator('[data-case-material="magnetic"]').isDisabled(),true,'Scanned device must disable out-of-stock style');
  await page.locator('[data-case-material="standard"]').click();
  await page.locator('[data-phone-color="synthetic-blue"]').waitFor();
  await page.screenshot({path:`test-results/v35-integration/${width}-editor.png`});
  assert.deepEqual(errors,[],'No browser exceptions');assert.deepEqual(writes,[],'No external requests or financial/hardware writes');
  console.log('PASS merged editor/catalog/colors/local save/checkout stations/order detail/scanned stock',width,height);
  await context.close();
 }
}finally{await browser.close();}
