import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('C:/Users/53671/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const browser=await chromium.launch({headless:true,channel:'msedge'});
const page=await browser.newPage({viewport:{width:1440,height:1100}});
try{
 await page.goto('http://127.0.0.1:4173/?lang=zh-CN#studio');
 await page.locator('#model').selectOption('iPhone 16');
 await page.locator('[data-editor="preset"][data-id="garden"]').click();
 await page.locator('#tab-text').click();
 await page.locator('#new-text').fill('ALWAYS\nWITH YOU');
 await page.locator('[data-editor="text"]').click();
 await page.locator('#layer-size').fill('66');
 await page.locator('#layer-y').fill('55');
 await page.locator('#layer-font').selectOption('serif');
 await page.waitForFunction(()=>[...document.images].filter(i=>i.getBoundingClientRect().width).every(i=>i.complete&&i.naturalWidth));
 await page.waitForTimeout(4000);
 await page.evaluate(()=>window.scrollTo(0,0));
 await page.screenshot({path:'test-results/studio-clean-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.locator('#tab-stickers').click();
 await page.evaluate(()=>document.querySelector('.editor-tabs').scrollIntoView({block:'center'}));
 await page.screenshot({path:'test-results/studio-clean-mobile.png'});
}finally{await browser.close();}
