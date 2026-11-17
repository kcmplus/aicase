// Synthetic server replies only; all writes and external requests are blocked.
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const origin=process.env.PREVIEW_URL,fixture=process.env.TEST_ORDER;
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
await mkdir('test-results/order-success',{recursive:true});
try{
 for(const [width,height] of [[390,844],[320,568]]){
  const context=await browser.newContext({viewport:{width,height},serviceWorkers:'block'}),writes=[],errors=[];
  const response=await context.request.get(`${origin}/api/v1/store/orders/${fixture}/`,{headers:{'X-Order-Key':'a'.repeat(64)}});
  assert(response.ok());const base=await response.json();
  const id=crypto.randomUUID(),path=`/api/v1/store/orders/${id}/`;
  let current={...base,reference:id,status:'pending',mode:'stripe_live',amount:'0.50',fulfillment_type:'courier',refund:null,progress:{...base.progress,code:'delivery',payment:'unpaid'},delivery_address:{recipient:'Synthetic recipient',phone:'1234567',region:'US / NY',street:'Test street'},shipping_quote:{version:1,print_amount:'0.50',shipping_amount:'0.00',total_amount:'0.50',currency:'USD'}};
  await context.route('**/*',route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.origin!==origin||!['GET','HEAD'].includes(request.method())){writes.push(request.method()+' '+url.pathname);return route.abort();}
   if(url.pathname===path||url.pathname===path+'progress/')return route.fulfill({json:current});
   return route.continue();
  });
  await context.addInitScript(()=>localStorage.setItem('popomo-order-access-v1','a'.repeat(64)));
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  const target=origin+`/#payment?order=${id}&result=success`;
  await page.goto(target);await page.locator(`[data-active-order="${id}"]`).waitFor();
  assert.equal(await page.locator('.v35-order-success').count(),0,'A success URL does not confirm payment');
  current={...current,status:'paid',progress:{...current.progress,payment:'paid'}};
  await page.locator('.v35-order-success[open]').waitFor({timeout:12000});
  assert.equal(await page.locator('#order-success-title').innerText(),'Payment successful');
  assert.equal(await page.locator('.order-success-amount').innerText(),'$0.50');
  assert.match(await page.locator('.order-success-reference').innerText(),new RegExp(id));
  const box=await page.locator('.v35-order-success').boundingBox();assert(box.x>=0&&box.y>=0&&box.x+box.width<=width+1&&box.y+box.height<=height+1);
  await page.screenshot({path:`test-results/order-success/${width}-paid.png`});
  await page.locator('[data-success-details]').click();await page.locator('.v35-order-success').waitFor({state:'detached'});
  assert.equal(new URL(page.url()).hash,`#payment?order=${id}&result=success`);
  await page.reload();await page.locator(`[data-active-order="${id}"]`).waitFor();
  assert.equal(await page.locator('.v35-order-success').count(),0,'Reload cannot repeat an acknowledged receipt');
  await context.close();

  const freeContext=await browser.newContext({viewport:{width,height},serviceWorkers:'block'});
  await freeContext.route('**/*',route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.origin!==origin||!['GET','HEAD'].includes(request.method())){writes.push(request.method()+' '+url.pathname);return route.abort();}
   if(url.pathname===path||url.pathname===path+'progress/')return route.fulfill({json:{...current,mode:'free_test',amount:'0.00',progress:{...current.progress,payment:'free'},shipping_quote:{...current.shipping_quote,print_amount:'0.00',total_amount:'0.00'}}});
   return route.continue();
  });
  await freeContext.addInitScript(()=>localStorage.setItem('popomo-order-access-v1','a'.repeat(64)));
  const freePage=await freeContext.newPage();freePage.on('pageerror',e=>errors.push(e.message));
  await freePage.goto(origin+`/#payment?order=${id}`);await freePage.locator(`[data-active-order="${id}"]`).waitFor();
  assert.equal(await freePage.locator('.v35-order-success').count(),0,'An old paid order does not trigger a new success notice');
  await freePage.goto(target);await freePage.locator('.v35-order-success[open]').waitFor();
  assert.equal(await freePage.locator('#order-success-title').innerText(),'Payment successful');
  assert.equal(await freePage.locator('.order-success-amount').innerText(),'$0.00');
  assert.match(await freePage.locator('#order-success-message').innerText(),/No payment was collected/);
  await freePage.screenshot({path:`test-results/order-success/${width}-free.png`});
  await freePage.locator('[data-success-orders]').click();await freePage.locator('.v35-orders').waitFor();
  assert.equal(new URL(freePage.url()).hash,'#orders');assert.equal(await freePage.locator('.v35-order-success').count(),0);
  // Exercise the real checkout handler with a synthetic POST reply, without a return URL.
  const createdId=crypto.randomUUID(),submitted=[];
  const created={...current,reference:createdId,mode:'free_test',amount:'0.00',progress:{...current.progress,payment:'free'},shipping_quote:{...current.shipping_quote,print_amount:'0.00',total_amount:'0.00'}};
  await freePage.route(origin+'/__success_fixture',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><title>Synthetic checkout fixture</title>'}));
  await freePage.route(origin+'/api/v1/store/payment-config/?fulfillment_type=courier',route=>route.fulfill({json:{available:true,provider:'free',mode:'test',zero_price_test:true,fulfillment_type:'courier',quote:created.shipping_quote}}));
  await freePage.route(origin+'/api/v1/store/orders/**',route=>{
   const request=route.request(),pathname=new URL(request.url()).pathname;
   if(pathname==='/api/v1/store/orders/'&&request.method()==='POST'){submitted.push(request.postDataJSON());return route.fulfill({status:201,json:created});}
   if(request.method()==='GET'&&[createdId+'/',createdId+'/progress/'].some(suffix=>pathname==='/api/v1/store/orders/'+suffix))return route.fulfill({json:created});
   return route.fallback();
  });
  await freePage.goto(origin+'/__success_fixture');
  await freePage.evaluate(async order=>{
   const {readDesign,writeDesign}=await import('/simple-storage.js');
   const {createDesignWorkspace}=await import('/design-workspace.js');
   const {readPass}=await import('/simple-core.js');
   const {registerSupplierTemplates}=await import('/phone-templates.js');
   registerSupplierTemplates([order.phone_template]);
   const identity=await(await fetch('/api/v1/store/ai-account/')).json();
   const workspace=createDesignWorkspace(identity,{read:readDesign,write:writeDesign});
   await workspace.write('checkout-draft',{pass:readPass(order.snapshot.code,order.snapshot),phoneTemplate:order.phone_template,quantity:1,fulfillmentType:'courier',deliveryAddress:order.delivery_address,deliveryAddressSaved:true});
  },created);
  await freePage.goto(origin+'/#checkout');
  await freePage.locator('#print-checkout-form [name="accepted"]').check();
  await freePage.locator('#print-checkout-form button:not([disabled])').click();
  await freePage.locator('.v35-order-success[open]').waitFor();
  assert.equal(new URL(freePage.url()).hash,`#payment?order=${createdId}`);
  assert.equal(await freePage.locator('#order-success-title').innerText(),'Payment successful');
  assert.equal(submitted.length,1);assert.equal(submitted[0].expected_amount,'0.00');assert.equal(submitted[0].quantity,1);assert.equal(submitted[0].fulfillment_type,'courier');
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  await freeContext.close();console.log('PASS verified paid/free receipt, new checkout, return/polling gates, session deduplication and modal layout',width,height);
 }
}finally{await browser.close();}
