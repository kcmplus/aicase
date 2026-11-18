// These namespaces separate local UI data, never grant server access or credits.
// Callers supply only an identity returned by the current server session.
export function designOwner(account){
 if(account?.authenticated===false)return 'guest';
 const id=account?.customer?.id;
 if(account?.authenticated===true&&((Number.isSafeInteger(id)&&id>0)||(typeof id==='string'&&/^[a-zA-Z0-9_-]{1,80}$/.test(id))))return 'customer-'+id;
 return null;
}
export function createDesignWorkspace(account,storage){
 const owner=designOwner(account);let active=Boolean(owner);
 const check=()=>{if(!active)throw Error('Your sign-in needs checking. Reload to view your local designs.');};
 const key=name=>{check();return 'v35:'+owner+':'+name;};
 const guarded=async(operation)=>{check();const result=await operation();check();return result;};
 return {
  owner,get active(){return active;},lock(){active=false;},check,key,
  read:name=>guarded(()=>storage.read(key(name))),
  write:(name,value)=>guarded(()=>storage.write(key(name),value)),
  update:(name,transform,initial)=>guarded(()=>storage.update(key(name),value=>{check();return transform(value);},initial)),
 };
}
export function createDesignLibrary(workspace,{validate,now=Date.now}={}){
 const validated=record=>({...record,pass:validate(record.pass)});
 return {
  async list(){const rows=await workspace.read('saved-designs')||[];if(!Array.isArray(rows))throw Error('Your saved designs could not be loaded.');return rows.map(record=>validated(record)).sort((a,b)=>b.updatedAt-a.updatedAt);},
  async save(pass,phoneTemplate){
   const snapshot=validate(pass),record={id:snapshot.code,pass:snapshot,phoneTemplate:phoneTemplate?structuredClone(phoneTemplate):null,updatedAt:now()};
   await workspace.update('saved-designs',rows=>[record,...rows.filter(row=>row.id!==record.id)],[]);return record;
  },
  async remove(id){await workspace.update('saved-designs',rows=>rows.filter(row=>row.id!==id),[]);},
 };
}
