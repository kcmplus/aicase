import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('C:/Users/53671/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const browser=await chromium.launch({headless:true,channel:'msedge'});
const page=await browser.newPage({viewport:{width:1413,height:871}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const base='http://127.0.0.1:4173/';
const state=()=>page.evaluate(()=>JSON.parse(localStorage.getItem('ai-case-studio-v1')));
const options=()=>page.locator('#product-variant option').evaluateAll(els=>els.map(el=>el.value));
const add=page.locator('[data-shop="add-accessory"]');
let checks=0;
const check=async(name,fn)=>{await fn();checks++;console.log('PASS '+name);};
try{
 await page.goto(base+'?lang=zh-CN#product?id=glass');
 await check('brand is required before selecting a screen protector model',async()=>{
  assert.equal(await page.locator('#product-brand').count(),1);
  assert.deepEqual(await page.locator('#product-brand option').allTextContents(),['请选择品牌','苹果 / Apple','三星 / Samsung']);
  assert.equal(await page.locator('#product-variant').isDisabled(),true);
  assert.equal(await add.isDisabled(),true);
 });
 await page.goto(base+'?lang=zh-CN#studio');
 await page.locator('#model').selectOption('iPhone 16 Pro');
 await page.locator('.account-button').click();
 await page.locator('#email').fill('brand-demo@example.com');
 await page.locator('#account-form button').click();
 await page.goto(base+'?lang=zh-CN#product?id=glass');
 await check('Apple only offers Apple models with correct stock',async()=>{
  await page.locator('#product-brand').selectOption('apple');
  assert.deepEqual(await options(),['','iphone16','iphone16pro','iphone15']);
  await page.locator('#product-variant').selectOption('iphone16pro');
  assert.match(await page.locator('.variant-status').innerText(),/7/);
  assert.equal(await add.isEnabled(),true);
 });
 await check('switching to Samsung clears the previous model and blocks stale purchase',async()=>{
  await page.locator('#product-brand').selectOption('samsung');
  assert.deepEqual(await options(),['','s24']);
  assert.equal(await page.locator('#product-variant').inputValue(),'');
  assert.equal(await add.isDisabled(),true);
  await page.locator('#product-variant').selectOption('s24');
  assert.match(await page.locator('.variant-status').innerText(),/4/);
  assert.equal(await page.locator('.model-match strong').count(),1);
 });
 await check('language switch preserves brand and model, cart keeps exact variant',async()=>{
  await page.locator('#language').selectOption('en-US');
  assert.equal(await page.getByLabel('Phone brand',{exact:true}).inputValue(),'samsung');
  assert.equal(await page.getByLabel('Phone model',{exact:true}).inputValue(),'s24');
  await add.click();
  const s=await state();
  assert.equal(s.cart[0].variantId,'s24');
  assert.equal(s.model,'iPhone 16 Pro');
  assert.equal(s.account.defaultModel,'iPhone 16 Pro');
  await page.locator('.header-cart').click();
  assert.match(await page.locator('.cart-items').innerText(),/Samsung S24/);
 });
 await check('Apple and Samsung remain separate cart variants and empty brand resets selection',async()=>{
  await page.goto(base+'?lang=en-US#product?id=glass');
  await page.locator('#product-brand').selectOption('apple');
  await page.locator('#product-variant').selectOption('iphone16');
  await add.click();
  assert.deepEqual((await state()).cart.map(l=>l.variantId),['s24','iphone16']);
  await page.locator('#product-brand').selectOption('');
  assert.equal(await page.locator('#product-variant').isDisabled(),true);
  assert.equal(await add.isDisabled(),true);
 });
 await check('both selectors fit desktop and mobile in both languages',async()=>{
  for(const lang of ['zh-CN','en-US'])for(const width of [360,390,768,1080,1413]){
   await page.setViewportSize({width,height:871});
   await page.goto(base+'?lang='+lang+'#product?id=glass');
   await page.locator('#product-brand').selectOption('samsung');
   await page.locator('#product-variant').selectOption('s24');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   for(const selector of ['#product-brand','#product-variant']){
    const box=await page.locator(selector).boundingBox();
    assert.ok(box.width>100&&box.height>=44&&box.x>=0&&box.x+box.width<=width);
   }
   if(width===1413&&lang==='zh-CN')await page.screenshot({path:'test-results/product-brands-desktop.png'});
   if(width===390&&lang==='en-US'){
    await page.locator('.product-detail-copy').scrollIntoViewIfNeeded();
    await page.screenshot({path:'test-results/product-brands-mobile.png'});
   }
  }
 });
 assert.deepEqual(errors,[]);
 console.log(`${checks} brand/model checks passed`);
}finally{await browser.close();}
