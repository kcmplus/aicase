import {orderRequest} from './order-service.js';
import {scopeIds} from './fulfillment-service.js';

// Entry routing only reads orders. A QR never authorizes payment, sending or printing.
export async function stationEntry({scope,hash='',station,request=orderRequest}){
 const ids=scopeIds(scope);
 if(!ids||!['','#home'].includes(hash))return null;
 if(!station||station.device_id!==ids.device_id||station.shop_id!==ids.shop_id)return {route:'orders'};
 try{
  const data=await request('?page=1');
  if(!Array.isArray(data.results)||typeof data.has_more!=='boolean'||data.page!==1||
     !data.results.every(o=>/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/i.test(o.reference)))throw Error('Your orders could not be loaded. Please refresh orders.');
  if(data.results.length===1&&!data.has_more)return {reference:data.results[0].reference,data};
  return {route:data.results.length===0&&!data.has_more?'choose?source=photo':'orders',data};
 }catch(error){return {route:'orders',error:error.message||'Your orders could not be loaded. Please refresh orders.'};}
}
