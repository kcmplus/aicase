// Keep cached connections usable after a browser closes IndexedDB in the background.
export function localDatabase(name,storeName){
 let connection;
 function open(){
  if(connection)return connection;
  const pending=Promise.resolve().then(()=>new Promise((resolve,reject)=>{
   const request=indexedDB.open(name,1);
   request.onupgradeneeded=()=>request.result.createObjectStore(storeName);
   request.onerror=()=>reject(request.error);
   request.onsuccess=()=>{
    const db=request.result;
    const invalidate=()=>{if(connection===pending)connection=undefined;};
    db.onclose=invalidate;
    db.onversionchange=()=>{invalidate();db.close();};
    resolve(db);
   };
  }));
  connection=pending;
  pending.catch(()=>{if(connection===pending)connection=undefined;});
  return pending;
 }
 return async function transact(mode,operation){
  for(let attempt=0;attempt<2;attempt++){
   const pending=open(),db=await pending;
   let tx;
   try{tx=db.transaction(storeName,mode);}
   catch(error){
    if(error?.name!=='InvalidStateError')throw error;
    if(connection===pending)connection=undefined;
    db.close();
    if(attempt===1)throw error;
    continue;
   }
   // Only retry transaction creation. Never replay an operation after it started.
   return operation(tx);
  }
 };
}
