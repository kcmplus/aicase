import {localDatabase} from './local-database.js';
const transact=localDatabase('popomo-personal-designs','designs');
export async function readDesign(key){
 return transact('readonly',tx=>new Promise((resolve,reject)=>{const r=tx.objectStore('designs').get(key);tx.oncomplete=()=>resolve(r.result);tx.onerror=()=>reject(tx.error||r.error);tx.onabort=()=>reject(tx.error||Error('Design could not be loaded.'));}));
}
export async function writeDesign(key,value){
 return transact('readwrite',tx=>new Promise((resolve,reject)=>{tx.objectStore('designs').put(value,key);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||Error('Design could not be saved.'));}));
}
// Serialize lifecycle changes across tabs, and publish only after commit.
export async function updateDesign(key,transform,initialValue){
 return transact('readwrite',tx=>new Promise((resolve,reject)=>{
  const store=tx.objectStore('designs');let value,error;
  const r=store.get(key);
  r.onsuccess=()=>{try{if(!r.result&&!initialValue)throw Error('This render is missing. Please start again.');value=transform(r.result||structuredClone(initialValue));store.put(value,key);}catch(e){error=e;tx.abort();}};
  tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(error||tx.error);tx.onabort=()=>reject(error||tx.error||Error('Render could not be saved.'));
 }));
}
