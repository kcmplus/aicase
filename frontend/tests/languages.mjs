import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('C:/Users/53671/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const browser=await chromium.launch({headless:true,channel:'msedge'});
const page=await browser.newPage({viewport:{width:390,height:844}});
const base='http://127.0.0.1:4173/';
let count=0;const check=async(name,fn)=>{await fn();count++;console.log('PASS '+name);};
const state=()=>page.evaluate(()=>JSON.parse(localStorage.getItem('ai-case-studio-v1')));
const switchTo=locale=>page.locator('#language').selectOption(locale);
const untranslated=()=>page.evaluate(()=>{const out=[];const walker=document.createTreeWalker(document.querySelector('#app'),NodeFilter.SHOW_TEXT);let n;while(n=walker.nextNode()){if(!n.parentElement.closest('[translate="no"],.language-control')&&/[\u3400-\u9fff]/.test(n.textContent))out.push(n.textContent.trim());}return out;});
try{
await page.goto(base);
await check('language selector is available on the mobile header',async()=>assert.equal(await page.locator('#language').count(),1));
await switchTo('en-US');
await check('English page language and title persist after reload',async()=>{await page.reload();assert.equal(await page.locator('html').getAttribute('lang'),'en-US');assert.match(await page.title(),/Inspiration/);assert.deepEqual(await untranslated(),[]);});
await page.goto(base+'#studio');await page.locator('#model').selectOption('小米 14');await page.locator('#tab-text').click();await page.locator('#caption').fill('邮寄到家');
await switchTo('zh-CN');await switchTo('en-US');
await check('language changes preserve canonical model and user artwork text',async()=>{assert.equal(await page.locator('#model').inputValue(),'小米 14');assert.equal(await page.locator('#caption').inputValue(),'邮寄到家');assert.equal(await page.locator('#live-phone .case-caption').innerText(),'邮寄到家');assert.deepEqual(await untranslated(),[]);});
await page.locator('.account-button').click();await page.locator('#email').fill('language@example.com');await page.locator('#account-form button').click();
await page.locator('[data-action="to-delivery"]').click();await page.locator('[data-action="delivery"][data-mode="pickup"]').click();
await check('unsupported-device and inventory messages are localized',async()=>{assert.match(await page.locator('.alert').innerText(),/not support/);assert.deepEqual(await untranslated(),[]);});
await page.locator('[data-action="mail"]').click();await page.locator('[data-action="to-checkout"]').click();await page.locator('#pay-button').click();await page.locator('[data-action="fill-address"]').click();await page.locator('#confirm-design').check();
await check('sample shipping details clear prior required-field errors',async()=>assert.equal(await page.locator('#checkout-form').evaluate(f=>f.checkValidity()),true));
await switchTo('zh-CN');await switchTo('en-US');
await check('checkout preserves filled values and consent when switching languages',async()=>{assert.equal(await page.locator('input[name="name"]').inputValue(),'Demo Customer');assert.equal(await page.locator('#confirm-design').isChecked(),true);assert.match(await page.locator('.total-line').innerText(),/USD\s*77/);});
await page.locator('.demo-controls summary').click();await page.locator('#fail-payment').check();await page.locator('#pay-button').click();await page.locator('#checkout-error').filter({hasText:'Demo payment failed'}).waitFor();
await check('English payment failure creates no order',async()=>assert.equal((await state()).orders.length,0));
await page.locator('#fail-payment').uncheck();await page.locator('#pay-button').click();await page.waitForURL(/#orders$/);
await check('English order keeps USD price and formats an American date',async()=>{assert.equal((await state()).orders[0].total,77);assert.match(await page.locator('.page-heading p').innerText(),/\d{1,2}\/\d{1,2}\/\d{4}/);assert.deepEqual(await untranslated(),[]);});
for(let j=0;j<4;j++){await page.locator('[data-action="advance"]').click();assert.deepEqual(await untranslated(),[]);}
await check('English mail tracking completes',async()=>assert.equal((await state()).orders[0].step,4));
await page.goto(base+'?device=SH-002&lang=en-US#device');await page.locator('[data-action="device-design"]').click();await page.locator('[data-action="to-delivery"]').click();await page.locator('[data-action="to-checkout"]').click();await page.locator('#confirm-design').check();await page.locator('#pay-button').click();await page.waitForURL(/#orders$/);
for(let j=0;j<3;j++)await page.locator('[data-action="advance"]').click();await page.locator('#pickup-code').fill('000000');await page.locator('#pickup-form button').click();
await check('English pickup error and pickup flow work',async()=>{assert.match(await page.locator('#pickup-error').innerText(),/does not match/);await page.locator('#pickup-code').fill((await state()).orders[0].pickupCode);await page.locator('#pickup-form button').click();assert.equal((await state()).orders[0].step,3);assert.deepEqual(await untranslated(),[]);});
await check('both languages fit six pages at five viewport sizes',async()=>{for(const lang of ['zh-CN','en-US']){for(const [w,h] of [[360,800],[390,844],[768,1024],[1080,1920],[1440,1000]]){await page.setViewportSize({width:w,height:h});for(const r of ['home','studio','delivery','checkout','orders','device']){await page.goto(base+'?lang='+lang+'#'+r);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${lang} ${w} ${r} overflow`);if(lang==='en-US')assert.deepEqual(await untranslated(),[],`${r} untranslated`);}}}});
await page.setViewportSize({width:390,height:844});await page.goto(base+'?lang=en-US#home');await page.screenshot({path:'test-results/en-mobile-home.png',fullPage:true});await page.goto(base+'?lang=en-US#studio');await page.screenshot({path:'test-results/en-mobile-studio.png',fullPage:true});await page.setViewportSize({width:1440,height:1000});await page.goto(base+'?lang=en-US#home');await page.screenshot({path:'test-results/en-desktop-home.png',fullPage:true});
console.log(`${count} language checks passed`);
}finally{await browser.close();}
