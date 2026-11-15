// Layout regression using real preview CSS, artwork renderer and fitting function.
// Start the local storefront; set PLAYWRIGHT_MODULE to your installed Playwright module.
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE?pathToFileURL(process.env.PLAYWRIGHT_MODULE).href:'playwright');
const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
const fit=source.slice(source.indexOf('function fitCanvasEditor(){'),source.indexOf('\nfunction observeCanvasPreview()'));
const origin=process.env.PREVIEW_URL||'http://127.0.0.1:4191';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
await mkdir('test-results/preview-fit',{recursive:true});
try{
 for(const [width,height] of [[1440,900],[390,844],[320,568],[844,390]]){
  const page=await browser.newPage({viewport:{width,height}});
  await page.route('**/__preview_fixture',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><head>'+['simple.css','editor-workspace.css','v35-workspace.css'].map(f=>`<link rel="stylesheet" href="/${f}">`).join('')+'</head><body></body></html>'}));
  await page.goto(origin+'/__preview_fixture');
  await page.evaluate(async()=>{const {phone}=await import('/art.js');document.body.innerHTML='<section class="editor-flow v35-editor"><div class="large-preview"><div class="large-case artwork-canvas">'+phone({art:'bloom'},'iPhone 17')+'</div><div class="template-tools">Preview only · Your print template stays unchanged.</div></div><dialog class="canvas-editor"><header class="canvas-editor-header"><h2>Edit your design</h2><button class="canvas-done">Done</button></header><div class="canvas-stage"></div><footer class="canvas-toolbar">Design controls</footer></dialog></section>'});
  for(const expanded of [false,true]){
   const geometry=await page.evaluate(({fit,expanded})=>{
    if(expanded){const dialog=document.querySelector('dialog');dialog.querySelector('.canvas-stage').append(document.querySelector('.large-preview'));dialog.showModal();}
    const canvasExpanded=expanded,highlightArtwork=()=>{};
    eval('('+fit+')()');
    const preview=document.querySelector('.large-preview'),phone=preview.querySelector('.phone-case'),cs=getComputedStyle(preview);
    const box=preview.getBoundingClientRect(),p=phone.getBoundingClientRect();
    return {box:box.toJSON(),phone:p.toJSON(),top:box.top+parseFloat(cs.paddingTop),bottom:box.bottom-parseFloat(cs.paddingBottom),ratio:getComputedStyle(phone).aspectRatio};
   },{fit,expanded});
   assert(geometry.phone.top>=geometry.top-1,JSON.stringify({width,height,expanded,geometry}));
   assert(geometry.phone.bottom<=geometry.bottom+1,JSON.stringify({width,height,expanded,geometry}));
   assert(geometry.phone.left>=geometry.box.left&&geometry.phone.right<=geometry.box.right);
   const [rw,rh]=geometry.ratio.split('/').map(Number);
   assert(Math.abs(geometry.phone.width/geometry.phone.height-rw/rh)<.02,'Phone aspect ratio changed');
   await page.screenshot({path:`test-results/preview-fit/${width}-${height}-${expanded?'expanded':'overview'}.png`});
   console.log('PASS',width,height,expanded?'expanded':'overview',Math.round(geometry.phone.height)+'px');
  }
  await page.close();
 }
}finally{await browser.close();}
