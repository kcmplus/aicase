import test from 'node:test';
import assert from 'node:assert/strict';
import {phoneBrands,findPhoneModels} from '../storefront/phone-catalog.js';
import {phoneModels} from '../storefront/simple-core.js';

test('phone brands and searches preserve model identifiers and QR catalog order',()=>{
 const before=[...phoneModels];
 assert.deepEqual(phoneBrands(phoneModels),['Apple','Samsung']);
 assert.deepEqual(findPhoneModels(phoneModels,'Apple','iphone16'),['iPhone 16 Pro','iPhone 16']);
 assert.deepEqual(findPhoneModels(phoneModels,'Apple','APPLE 16 pro'),['iPhone 16 Pro']);
 assert.deepEqual(findPhoneModels(phoneModels,'Samsung','s24'),['Samsung S24']);
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
