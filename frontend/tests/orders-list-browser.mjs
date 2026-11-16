import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const origin=process.env.PREVIEW_URL;
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
await mkdir('test-results/orders-list',{recursive:true});
try{
 for(const [width,height] of [[390,844],[320,568],[1440,1000]]){
  const context=await browser.newContext({viewport:{width,height},serviceWorkers:'block'}),errors=[],writes=[];
  await context.addInitScript(()=>localStorage.setItem('popomo-order-access-v1','a'.repeat(64)));
  await context.route('**/*',route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.origin!==origin||!['GET','HEAD'].includes(request.method())){writes.push(request.method()+' '+url.pathname);return route.abort();}
   return route.continue();
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto(origin+'/#orders');
  await page.locator('.order-row').first().waitFor();
  assert.equal(await page.locator('.order-row').count(),2);
  await page.locator('[data-preview-ready=true]').first().waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  const cover=await page.locator('.order-cover[data-preview-ready=true]').first().boundingBox();
  const phone=await page.locator('.order-cover[data-preview-ready=true]>.phone-case').first().boundingBox();
  assert(phone.height<=cover.height&&phone.width<=cover.width,'Full case stays inside thumbnail');
  await page.screenshot({path:`test-results/orders-list/${width}-orders.png`,fullPage:true});
  await page.locator('[data-filter=pending]').click();await page.locator('[data-filter=pending][aria-pressed=true]').waitFor();
  await page.locator('.v35-orders[aria-busy=false]').waitFor();
  assert.equal(await page.locator('.order-row').count(),1);
  assert.equal(await page.locator('.order-card-actions .primary').innerText(),'Pay now →');
  await page.locator('[data-filter=paid]').click();await page.locator('[data-filter=paid][aria-pressed=true]').waitFor();await page.locator('.v35-orders[aria-busy=false]').waitFor();
  assert.equal(await page.locator('.order-row').count(),1);
  assert.equal(await page.locator('.order-card-actions .primary').count(),0);
  await page.locator('#order-search').fill('not-a-real-order');await page.locator('#order-search').press('Enter');
  await page.locator('.orders-empty').waitFor();assert.equal(await page.locator('.order-row').count(),0);
  await page.locator('#order-search').fill(process.env.TEST_ORDER);await page.locator('#order-search').press('Enter');
  await page.locator('.order-row').waitFor();
  await page.getByRole('button',{name:'Order details ↗',exact:true}).click();
  await page.locator('[data-active-order="'+process.env.TEST_ORDER+'"]').waitFor();
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  await context.close();console.log('PASS order history layout, private thumbnail, filters, search and detail',width,height);
 }
}finally{await browser.close();}
