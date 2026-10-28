import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {phoneTemplate,phoneTemplates} from '../storefront/phone-templates.js';
import {phone} from '../storefront/art.js';
import {coverRect,pngWithDpi,crc32,textLines} from '../storefront/print-export.js';
import {createPass,createPersonalPass,readPass} from '../storefront/simple-core.js';
import {makePersonalDesign} from '../storefront/simple-personalize.js';

test('both vendor models preserve template revision through design passes',()=>{
 for(const t of phoneTemplates){
  const pass=createPersonalPass({source:'collection',designId:'bloom',model:t.model,effect:'original',intensity:65,zoom:100,x:50,y:50});
  assert.equal(readPass(pass.code,pass).phoneTemplateId,t.id);
  assert.equal(makePersonalDesign(pass).phoneTemplateId,t.id);
  assert.throws(()=>readPass(pass.code,{...pass,phoneTemplateId:'unknown'}));
  assert.throws(()=>createPass('bloom',t.model)); // legacy QR indexes remain unchanged
 }
 assert.equal(readPass('POP-1117').model,'iPhone 16 Pro');
 assert.equal(phoneTemplate('iPhone 17 Pro'),null); // never substitute a similar model
});
test('real template previews use the correct mask and overlay, without generic lenses',()=>{
 for(const t of phoneTemplates){
  const html=phone(makePersonalDesign({source:'collection',designId:'bloom'}),t.model);
  assert.ok(html.includes(`data-phone-template="${t.id}"`));
  assert.ok(html.includes(t.mask));assert.ok(html.includes(t.previewOverlay));
  assert.ok(html.includes('print-surface'));assert.ok(html.includes('data-layer-id'));
  assert.ok(!html.includes('class="camera"'));assert.ok(!html.includes('class="case-edge"'));
 }
 assert.ok(phone({},'iPhone 16 Pro').includes('class="camera"'));
});
function chunks(bytes){
 const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.length),out=[];
 for(let offset=8;offset<bytes.length;){
  const length=view.getUint32(offset),type=String.fromCharCode(...bytes.subarray(offset+4,offset+8));
  out.push({type,data:bytes.subarray(offset+8,offset+8+length),crc:view.getUint32(offset+8+length),body:bytes.subarray(offset+4,offset+8+length)});offset+=length+12;
 }
 return out;
}
test('PNG export writes a single valid 300 DPI pHYs chunk without altering pixels',async()=>{
 const t=phoneTemplates[0],input=new Uint8Array(await readFile(new URL('../storefront'+t.mask,import.meta.url)));
 const output=pngWithDpi(pngWithDpi(input,96),300),before=chunks(input),after=chunks(output),physical=after.filter(c=>c.type==='pHYs');
 assert.equal(physical.length,1);const data=new DataView(physical[0].data.buffer,physical[0].data.byteOffset,9);
 assert.equal(data.getUint32(0),11811);assert.equal(data.getUint32(4),11811);assert.equal(data.getUint8(8),1);
 assert.ok(after.every(c=>crc32(c.body)===c.crc));
 assert.deepEqual(after.filter(c=>c.type==='IDAT'),before.filter(c=>c.type==='IDAT'));
 assert.throws(()=>pngWithDpi(new Uint8Array([1,2,3])));
 assert.throws(()=>pngWithDpi(input.subarray(0,35)));
 for(const t of phoneTemplates){
  const bytes=new Uint8Array(await readFile(new URL('../storefront'+t.mask,import.meta.url)));
  const header=chunks(bytes)[0].data,view=new DataView(header.buffer,header.byteOffset,header.length);
  assert.equal(view.getUint32(0),t.printWidth);assert.equal(view.getUint32(4),t.printHeight);assert.equal(header[9],6); // RGBA, not an opaque grayscale mask
 }
});
test('crop placement uses object-position semantics and text wraps without losing characters',()=>{
 assert.deepEqual(coverRect(1200,600,300,600,0,50),{x:-0,y:0,width:1200,height:600,scale:1});
 assert.equal(coverRect(1200,600,300,600,100,50).x,-900);
 assert.equal(coverRect(600,1200,300,600).scale,.5);
 assert.deepEqual(textLines('hello\nworld',10,s=>s.length),['hello','world']);
 const text='A longword\n你好世界';assert.equal(textLines(text,4,s=>[...s].length).join(''),text.replaceAll('\n',''));
});
