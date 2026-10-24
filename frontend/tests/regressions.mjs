import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('C:/Users/53671/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const browser=await chromium.launch({headless:true,channel:'msedge'});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const failures=[];
async function check(name,fn){try{await fn();console.log('PASS '+name);}catch(e){failures.push(name);console.log('FAIL '+name+' '+e.message);}}
const state=()=>page.evaluate(()=>JSON.parse(localStorage.getItem('ai-case-studio-v1')));
await page.goto('http://127.0.0.1:4173');
await page.locator('[data-action="account"]').click();await page.locator('#email').fill('repeat@example.com');await page.locator('#default-model').selectOption('Samsung S24');await page.locator('#account-form button').click();
await page.locator('[data-action="account"]').click();await page.locator('[data-logout]').click();
await page.locator('[data-action="account"]').click();await page.locator('#default-model').selectOption('iPhone 15');await page.locator('#email').fill('repeat@example.com');await page.locator('#account-form button').click();
await check('returning account restores saved model without forced reselection',async()=>assert.equal((await state()).model,'Samsung S24'));
await page.goto('http://127.0.0.1:4173/#studio');await page.locator('#model').selectOption('iPhone 16 Pro');await page.locator('[data-action="to-delivery"]').click();await page.locator('[data-action="to-checkout"]').click();await page.locator('[data-action="fill-address"]').click();await page.locator('#confirm-design').check();await page.locator('#pay-button').click();await page.locator('input[name="name"]').fill('支付中修改');await page.waitForURL(/#orders$/);
await check('payment uses confirmed snapshot even when form changes during processing',async()=>assert.equal((await state()).orders[0].address.name,'演示用户'));
await browser.close();assert.deepEqual(failures,[]);
