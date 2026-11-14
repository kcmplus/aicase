import {registerSupplierTemplates} from './phone-templates.js';
import {validPhoneColors} from './phone-colors.js';
export const stockedPhoneModels=[];
export let stockCatalogStatus='loading';
let records=[];
export const stockSelection=model=>records.find(r=>r.name===model)||null;
export function applyStockCatalog(data){
 if(data?.version!==1||!Array.isArray(data.models)||!Array.isArray(data.templates))throw Error('Invalid stock catalog.');
 const names=new Set();
 for(const r of data.models){
  if(typeof r.name!=='string'||!r.name||names.has(r.name)||typeof r.brand!=='string'||!data.templates.some(t=>t.model===r.name&&t.id===r.templateId&&t.inventoryItemId===r.inventoryItemId))throw Error('Invalid stocked model.');
  names.add(r.name);
 }
 registerSupplierTemplates(data.templates,{select:true});
 records=data.models.map(r=>({...r,colors:validPhoneColors(r.colors,data.templates.find(t=>t.id===r.templateId))}));stockedPhoneModels.splice(0,stockedPhoneModels.length,...records.map(r=>r.name));stockCatalogStatus=data.availability==='updating'?'updating':'ready';
}
export function unavailableStockCatalog(){
 records=[];stockedPhoneModels.splice(0);registerSupplierTemplates([],{select:true});stockCatalogStatus='unavailable';
}
export function deviceScope(location=globalThis.location){
 const query=new URLSearchParams(location?.search||''),hash=new URLSearchParams((location?.hash||'').split('?')[1]||'');
 const scope=new URLSearchParams();
 for(const name of ['device_id','shop_id']){const value=query.get(name)??hash.get(name);if(value!==null)scope.set(name,value);}
 return scope.toString();
}
export async function loadStockCatalog(fetcher=globalThis.fetch,scope=deviceScope()){
 try{
  const response=await fetcher('/api/v1/store/phone-models/'+(scope?'?'+scope:''),{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw Error('Stock catalog unavailable.');
  applyStockCatalog(await response.json());return true;
 }catch{unavailableStockCatalog();return false;}
}
