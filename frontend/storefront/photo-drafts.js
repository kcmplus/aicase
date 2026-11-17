import {isPhoto} from './simple-personalize.js';

// Unfinished photos need no purchasable phone model or print-ready pass.
// Store only editing data; never restore order, payment or AI request authority.
const fields=['designId','model','caseMaterial','phoneTemplateId','phoneColor','photo','effect','intensity','zoom','x','y','aiStyle','aiExample','artworkLayouts','photoArtwork','keepCollection','photoPlacement','photoOrigin','ai'];
export function createPhotoDraftLibrary(workspace,{now=Date.now,id=()=>crypto.randomUUID()}={}){
 const snapshot=value=>{
  if(value?.source!=='photo'||!isPhoto(value.photo))return null;
  return structuredClone({source:'photo',...Object.fromEntries(fields.filter(key=>Object.hasOwn(value,key)).map(key=>[key,value[key]]))});
 };
 const records=value=>{
  if(!Array.isArray(value))throw Error('Your photo drafts could not be loaded.');
  return value;
 };
 return {
  async list(){return records(await workspace.read('photo-drafts')||[]).map(row=>({id:row.id,updatedAt:row.updatedAt,snapshot:snapshot(row.snapshot)})).filter(row=>row.snapshot).sort((a,b)=>b.updatedAt-a.updatedAt);},
  async save(value){
   const copy=snapshot(value);if(!copy)return;
   const serialized=JSON.stringify(copy);
   await workspace.update('photo-drafts',value=>{
    const rows=records(value);
    // Re-entering Studio without editing should not produce duplicate cards.
    if(rows.some(row=>JSON.stringify(row.snapshot)===serialized))return rows;
    return [{id:id(),snapshot:copy,updatedAt:now()},...rows];
   },[]);
  },
  async remove(id){await workspace.update('photo-drafts',value=>records(value).filter(row=>row.id!==id),[]);},
 };
}
