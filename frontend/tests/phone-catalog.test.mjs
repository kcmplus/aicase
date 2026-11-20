import {phoneModelChoices} from '../storefront/phone-model-dialog.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import {phoneBrands,findPhoneModels} from '../storefront/phone-catalog.js';
import {selectablePhoneModels as phoneModels} from '../storefront/simple-core.js';

test('the bundled fallback retains its two historical templates independently of stock choices',()=>{
 const before=[...phoneModels];
 assert.deepEqual(phoneModels,['iPhone 17','iPhone 16e']);
 assert.deepEqual(phoneBrands(phoneModels),['Apple']);
 assert.deepEqual(findPhoneModels(phoneModels,'Apple','iphone16'),['iPhone 16e']);
 assert.deepEqual(findPhoneModels(phoneModels,'Apple','APPLE 17'),['iPhone 17']);
 assert.deepEqual(findPhoneModels(phoneModels,'Apple','APPLE 16 pro'),[]);
 assert.deepEqual(findPhoneModels(phoneModels,'Samsung','s24'),[]);
 assert.deepEqual(findPhoneModels(phoneModels,'Apple','S24'),[]);
 assert.deepEqual(phoneModels,before);
});

test('large model catalogs stay separated by brand and handle empty and unmatched searches',()=>{
 const models=[...Array.from({length:100},(_,i)=>'iPhone '+(i+1)),...Array.from({length:100},(_,i)=>'Samsung S'+(i+1)),'Google Pixel 9'];
 assert.deepEqual(phoneBrands(models),['Apple','Samsung','Google']);
 assert.equal(findPhoneModels(models,'Apple','   ').length,100);
 assert.deepEqual(findPhoneModels(models,'Google','pixel 9'),['Google Pixel 9']);
 assert.deepEqual(findPhoneModels(models,'Samsung','no such phone'),[]);
 assert.deepEqual(findPhoneModels(models,'Unknown',''),[]);
});


test('model sheet groups the supplied catalog without inventing models or changing its order',()=>{
 const models=['iPhone 17 Pro Max','iPhone 17','Samsung S26','Xiaomi 16'];
 const html=phoneModelChoices({models,brand:'Apple',selected:'iPhone 17'});
 assert.ok(html.indexOf('data-picker-model="iPhone 17 Pro Max"')<html.indexOf('data-picker-model="iPhone 17"'));
 assert.match(html,/data-picker-brand="Samsung"/);assert.match(html,/data-picker-model="iPhone 17" aria-pressed="true"/);
 assert.doesNotMatch(html,/data-picker-model="Samsung S26"/);
 const scoped=phoneModelChoices({models:['Samsung S26'],brand:'Apple'});
 assert.doesNotMatch(scoped,/iPhone|Xiaomi/);assert.match(scoped,/data-picker-model="Samsung S26"/);
 for(const status of ['loading','unavailable','updating'])assert.doesNotMatch(phoneModelChoices({models,status}),/data-picker-model=/);
 assert.match(phoneModelChoices({models:[],lang:'zh-CN'}),/重新加载/);
 assert.match(phoneModelChoices({models:['Brand <script>'],brand:'Brand'}),/Brand &lt;script&gt;/);
});


test('model sheet uses the server brand for model names without a brand prefix',()=>{
 const html=phoneModelChoices({models:['Galaxy test'],brand:'Samsung',selection:()=>({brand:'Samsung'})});
 assert.match(html,/data-picker-brand="Samsung"/);assert.match(html,/data-picker-model="Galaxy test"/);assert.doesNotMatch(html,/data-picker-brand="Galaxy"/);
});


test('stale station inventory is distinguished from a failed catalog request',()=>{
 const updating=phoneModelChoices({status:'updating',models:['Old phone']});
 assert.match(updating,/Station stock needs updating/);
 assert.doesNotMatch(updating,/data-picker-model=/);
 assert.match(phoneModelChoices({status:'updating',lang:'zh-CN'}),/设备库存需要更新/);
 assert.match(phoneModelChoices({status:'unavailable'}),/Phone models are unavailable/);
 assert.match(phoneModelChoices({status:'loading'}),/Loading phone models/);
 assert.match(phoneModelChoices({status:'empty'}),/No phone models are currently available/);
});
