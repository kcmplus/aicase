// Session-only composition history. Photos and phone/stock selection are never restored.
const fields=['artworkLayouts','photoArtwork','photoPlacement','zoom','x','y','effect','intensity'];
export function createEditorHistory(limit=40){
 let context=null,entries=[],index=-1;
 const snapshot=state=>{
  const value=Object.fromEntries(fields.map(key=>[key,state[key]]));
  // Rendering lazily materializes these defaults; that is not a user edit.
  if(state.designId)value.artworkLayouts={...state.artworkLayouts,[state.designId]:{zoom:100,x:50,y:50,artworkEdits:{},addedArtwork:[],...state.artworkLayouts?.[state.designId]}};
  if(state.source==='photo')value.photoPlacement=state.photoPlacement||{x:50,y:50,scale:state.zoom||100,rotation:0};
  return JSON.stringify(value);
 };
 function record(state,owner){
  const next=[owner,state.source,state.designId,state.model,state.caseMaterial,state.photo,state.keepCollection,state.ai?.jobId];
  const value=snapshot(state);
  if(!context||next.some((part,i)=>part!==context[i])){context=next;entries=[value];index=0;return;}
  if(entries[index]===value)return;
  entries.splice(index+1);entries.push(value);
  if(entries.length>limit)entries.shift();
  index=entries.length-1;
 }
 function move(state,owner,delta){
  record(state,owner);
  if(index+delta<0||index+delta>=entries.length)return false;
  index+=delta;
  const value=JSON.parse(entries[index]);
  for(const key of fields){if(Object.hasOwn(value,key))state[key]=value[key];else delete state[key];}
  return true;
 }
 return {record,undo:(state,owner)=>move(state,owner,-1),redo:(state,owner)=>move(state,owner,1),get canUndo(){return index>0;},get canRedo(){return index>=0&&index<entries.length-1;}};
}
