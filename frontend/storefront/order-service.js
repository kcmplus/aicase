import {readPass} from './simple-core.js';

const KEY='popomo-order-access-v1';
export function orderAccessKey(storage=localStorage){
 let key=storage.getItem(KEY);
 if(!/^[0-9a-f]{64}$/.test(key||'')){key=crypto.randomUUID().replaceAll('-','')+crypto.randomUUID().replaceAll('-','');storage.setItem(KEY,key);}
 return key;
}
export async function orderRequest(path='',{method='GET',body,fetcher=fetch,key=orderAccessKey()}={}){
 const response=await fetcher('/api/v1/store/orders/'+path,{method,credentials:'omit',cache:'no-store',headers:{'Content-Type':'application/json','X-Order-Key':key},...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(20000)});
 let data;try{data=await response.json();}catch{throw Error('Orders are temporarily unavailable. Your design is saved; please retry.');}
 if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:Object.values(data).flat().map(v=>typeof v==='string'?v:JSON.stringify(v)).join(' ')||'Could not save your order.');error.status=response.status;throw error;}
 return data;
}
export function savedOrder(data,previous){
 const pass=readPass(data.snapshot.code,data.snapshot);
 return {id:data.reference,server:true,mode:'demo',status:data.status==='completed'?'collected':data.status,priceCents:Math.round(Number(data.amount)*100),currency:data.currency,revision:data.revision,stationId:data.station_id,customerEmail:data.customer_email,pass,oldCodes:[...new Set([...(previous?.oldCodes||[]),...(previous&&previous.pass.code!==pass.code?[previous.pass.code]:[])])],createdAt:Date.parse(data.created_at),updatedAt:Date.parse(data.updated_at)};
}
export function checkoutBody(draft,{accepted,email='',amount}){
 return {request_key:draft.requestKey,accepted,customer_email:email,expected_amount:amount,snapshot:draft.pass};
}
