import {registerSupplierTemplates,registerDesignModels,selectSupplierTemplate} from './phone-templates.js';
export const stockedPhoneModels=[];
export let stockCatalogStatus='loading';
let records=[];
export function stockSelection(model,material){
 const record=records.find(r=>r.name===model);if(!record)return null;
 if(material===undefined)return record;
 const style=record.styles?.find(s=>s.caseMaterial===material);
 return style?.available?{...record,...style,templateId:style.templateId,inventoryItemId:style.inventoryItemId}:null;
}
export function applyStockCatalog(data){
 if(data?.version!==1||!Array.isArray(data.models)||!Array.isArray(data.templates))throw Error('Invalid stock catalog.');
 const names=new Set();
 for(const r of data.models){
  if(typeof r.name!=='string'||!r.name||names.has(r.name)||typeof r.brand!=='string'||!((data.scope==='catalog'&&r.templateId===undefined&&r.inventoryItemId===undefined)||data.templates.some(t=>t.model===r.name&&t.id===r.templateId&&t.inventoryItemId===r.inventoryItemId)))throw Error('Invalid stocked model.');
  if(r.styles!==undefined){
   if(!Array.isArray(r.styles)||r.styles.length!==2||new Set(r.styles.map(s=>s.caseMaterial)).size!==2)throw Error('Invalid case styles.');
   for(const s of r.styles){
    if(!['standard','magnetic'].includes(s.caseMaterial)||typeof s.available!=='boolean'||(s.templateId!==undefined&&!data.templates.some(t=>t.model===r.name&&t.id===s.templateId&&t.inventoryItemId===s.inventoryItemId))||(data.scope==='device'&&s.available&&!s.templateId))throw Error('Invalid case style.');
   }
  }
  names.add(r.name);
 }
 registerSupplierTemplates(data.templates,{select:true});
 for(const r of data.models)selectSupplierTemplate(r.name,r.templateId);
 registerDesignModels(data.models.map(r=>r.name));
 records=data.models.map(r=>({...r}));stockedPhoneModels.splice(0,stockedPhoneModels.length,...records.map(r=>r.name));stockCatalogStatus=data.availability==='updating'?'updating':'ready';
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
