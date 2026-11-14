import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,access} from 'node:fs/promises';
import {shellHeader,shellFooter,homePresentation,shellInfo} from '../storefront/v35-shell.js';

test('V35 home prioritizes the real album handler and preserves gallery and AI editor destinations',()=>{
 const html=homePresentation({gallery:'<section id="designs">CATALOG</section>'});
 assert.ok(html.indexOf('data-action="home-photo"')<html.indexOf('href="#designs"'));
 assert.match(html,/id="photo-file" data-home-upload type="file" accept="image\/jpeg,image\/png,image\/webp"/);
 assert.match(html,/href="#choose\?source=photo&studio=1"/);
 assert.match(html,/<section id="designs">CATALOG<\/section>/);
 assert.doesNotMatch(html,/sessionStorage|setTimeout|pay_status|data-action="advance-print"/);
});
test('upload busy state disables the album action without claiming upload success',()=>{
 const html=homePresentation({busy:true});
 assert.match(html,/data-action="home-photo" aria-busy="true" disabled/);
 assert.match(html,/Reading your photo…/);
 assert.doesNotMatch(homePresentation(),/aria-busy="true"/);
});
test('shared shell exposes working legacy destinations and bilingual native menu semantics',()=>{
 for(const lang of ['en-US','zh-CN']){
  const header=shellHeader({lang,authenticated:true,route:'orders'});
  for(const hash of ['home','designs','how-it-works','choose?source=photo','orders','pass','account'])assert.ok(header.includes(`href="#${hash}"`),hash);
  assert.match(header,/<dialog id="v35-menu"/);
  assert.match(header,/aria-controls="v35-menu" aria-expanded="false"/);
  assert.match(header,/href="#orders" aria-current="page"/);
  assert.match(header,new RegExp(`data-shell-language="${lang}" aria-pressed="true"`));
  assert.doesNotMatch(header,/href="\.\/.*\.html|#kiosk|#membership/);
  assert.match(shellFooter(lang),/data-shell-info="station"/);
 }
 assert.match(shellHeader({lang:'zh-CN'}),/打开菜单/);
 assert.match(shellHeader(),/Open menu/);
});
test('home instructions follow phone confirmation and do not ask to save a design QR',()=>{
 const html=homePresentation({lang:'zh-CN'});
 assert.match(html,/扫描设备屏上的二维码/);
 assert.match(html,/已出货不等于已取件/);
 assert.match(html,/快递／空运暂未开放结算/);
 assert.doesNotMatch(html,/保存.{0,4}二维码|Keep your code|save the QR code|Show your code/);
 assert.match(shellInfo('station','en-US')[1],/Nearby search is not available/);
 assert.match(shellInfo('ai','zh-CN')[1],/服务端确认/);
});
test('all V35 presentation assets are local and available; editor entry retains the existing service module',async()=>{
 const html=homePresentation(),css=await readFile(new URL('../storefront/v35-shell.css',import.meta.url),'utf8');
 for(const path of new Set([...html.matchAll(/(?:src)="\.\/([^"?]+)"/g),...css.matchAll(/url\('\.\/([^']+)'\)/g)].map(match=>match[1])))await access(new URL('../storefront/'+path,import.meta.url));
 const entry=await readFile(new URL('../storefront/index.html',import.meta.url),'utf8');
 assert.match(entry,/href="\.\/v35-shell.css"/);assert.match(entry,/src="\.\/simple-app.js"/);
 assert.doesNotMatch(entry,/popomo-ui|order-store.js|profile-store.js/);
});
