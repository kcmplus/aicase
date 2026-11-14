import {mergeMarketingLedger} from './marketing-core.js';
import {localDatabase} from './local-database.js';
// A shared IndexedDB record avoids per-tab localStorage cache races.
// Called under the existing Web Lock; still a browser-local simulation.
const transact=localDatabase('popomo-demo-payments','ledgers');
async function read(id){return transact('readonly',tx=>new Promise((resolve,reject)=>{const request=tx.objectStore('ledgers').get(id);tx.oncomplete=()=>resolve(request.result);tx.onerror=()=>reject(tx.error||request.error);tx.onabort=()=>reject(tx.error||Error('Payment ledger aborted'));}));}
async function write(id,data){return transact('readwrite',tx=>new Promise((resolve,reject)=>{tx.objectStore('ledgers').put(data,id);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||Error('Payment ledger aborted'));}));}
export async function hydratePaymentLedger(state){if(state.ledgerId)mergeMarketingLedger(state,await read(state.ledgerId));}
export async function commitWithPaymentLedger(state,commit){await hydratePaymentLedger(state);const before=structuredClone(state);try{commit();await write(state.ledgerId,{orders:structuredClone(state.orders),marketing:structuredClone(state.marketing)});}catch(error){Object.assign(state,before);throw error;}}
