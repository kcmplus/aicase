import templates from './assets/phone-templates/templates.json' with {type:'json'};

// Versioned files are immutable. Retain old entries when adding a new revision.
export const phoneTemplates=Object.freeze(templates.map(t=>Object.freeze({...t})));
const supplierTemplates=new Map(),selectedTemplates=new Map();
export function registerSupplierTemplates(items,{select=false}={}){
 if(!Array.isArray(items))throw Error('Invalid phone templates.');
 const validated=items.map(t=>{
  const asset=v=>typeof v==='string'&&/^\/media\/supplier-templates\/[a-f0-9]{64}-(?:overlay|mask)(?:_[a-zA-Z0-9]+)?\.png$/.test(v);
  if(!t||!/^supplier-[1-9]\d*-[a-f0-9]{20}$/.test(t.id)||typeof t.model!=='string'||!t.model||t.model.length>120||
    !['overlay','previewOverlay','mask'].every(k=>asset(t[k]))||
    !['printWidth','printHeight','sourceWidth','sourceHeight'].every(k=>Number.isInteger(t[k])&&t[k]>0&&t[k]<=4096)||
    t.previewOnly!==true||t.dpi!==null||!Number.isSafeInteger(t.inventoryItemId)||t.inventoryItemId<=0)throw Error('Invalid supplier template.');
  return Object.freeze({...t});
 });
 if(select)selectedTemplates.clear();
 for(const t of validated){supplierTemplates.set(t.id,t);if(select)selectedTemplates.set(t.model,t.id);}
}
export function phoneTemplate(model,id){
 const supplier=supplierTemplates.get(id??selectedTemplates.get(model));
 const template=supplier?.model===model?supplier:phoneTemplates.findLast(t=>t.model===model&&(id===undefined||t.id===id));
 if(id!==undefined&&!template)throw Error('This phone template is unavailable.');
 return template||null;
}
