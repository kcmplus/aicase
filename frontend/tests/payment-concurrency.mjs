import {createRequire} from 'node:module';
import fs from 'node:fs';
const {chromium}=createRequire(import.meta.url)('C:/Users/53671/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const browser=await chromium.launch({headless:true,channel:'msedge'});let fails=0;
for(let j=0;j<12;j++){
 const context=await browser.newContext();
 const a=await context.newPage();await a.goto('http://127.0.0.1:4173/');await a.locator('#main').waitFor();await a.evaluate(async()=>{const {initialState,login}=await import('./core.js'),{claimCoupon,selectCoupon}=await import('./marketing-core.js');const s=initialState();login(s,'test@example.com','iPhone 16');s.address={name:'Demo',phone:'13800138000',detail:'Shanghai demo address'};claimCoupon(s,'welcome');selectCoupon(s,'welcome');localStorage.setItem('ai-case-studio-v1',JSON.stringify(s));});await a.goto('http://127.0.0.1:4173/?lang=en-US#checkout');await a.locator('#confirm-design').check();const b=await context.newPage();await b.goto('http://127.0.0.1:4173/?lang=en-US#checkout');await b.locator('#confirm-design').check();await Promise.all([a.locator('#pay-button').click(),b.locator('#pay-button').click()]);for(const p of [a,b])await p.waitForFunction(()=>location.hash==='#orders'||Boolean(document.querySelector('#checkout-error')?.textContent));
 const counts=await Promise.all([a,b].map(p=>p.evaluate(()=>({href:location.href,count:JSON.parse(localStorage.getItem('ai-case-studio-v1')).orders.length}))));if(counts.filter(x=>x.href.endsWith('#checkout')).length!==1||counts.some(x=>x.count!==1)){fails++;fs.writeFileSync('test-results/payment-concurrency-failure.json',JSON.stringify(counts,null,2));console.log('FAIL '+j+' '+counts.map(x=>x.href));}else console.log('PASS '+j);await context.close();
}
await browser.close();console.log({fails});if(fails)process.exitCode=1;
