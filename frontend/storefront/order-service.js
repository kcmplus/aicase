import {readPass} from './simple-core.js';
import {esc} from './art.js';
import {registerSupplierTemplates} from './phone-templates.js';
import {retryUnavailableRead} from './request-retry.js';

const KEY='popomo-order-access-v1';
export function orderAccessKey(storage=localStorage){
 let key=storage.getItem(KEY);
 if(!/^[0-9a-f]{64}$/.test(key||'')){key=crypto.randomUUID().replaceAll('-','')+crypto.randomUUID().replaceAll('-','');storage.setItem(KEY,key);}
 return key;
}
export async function orderRequest(path='',{method='GET',body,fetcher=fetch,key=orderAccessKey()}={}){
 const multipart=typeof FormData!=='undefined'&&body instanceof FormData;
 const headers={...(!multipart?{'Content-Type':'application/json'}:{}),'X-Order-Key':key};
 if(!['GET','HEAD'].includes(method)){
  const csrf=await fetcher('/api/v1/auth/csrf/',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(20000)});
  if(!csrf.ok)throw Error('Your sign-in could not be checked. Please reload and try again.');
  headers['X-CSRFToken']=(await csrf.json()).csrfToken;
 }
 const response=await fetcher('/api/v1/store/orders/'+path,{method,credentials:'same-origin',cache:'no-store',headers,...(body===undefined?{}:{body:multipart?body:JSON.stringify(body)}),signal:AbortSignal.timeout(30000)});
 let data;try{data=await response.json();}catch{throw Error('Orders are temporarily unavailable. Your design is saved; please retry.');}
 if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:Object.values(data).flat().map(v=>typeof v==='string'?v:JSON.stringify(v)).join(' ')||'Could not save your order.');error.status=response.status;throw error;}
 return data;
}
export function savedOrder(data,previous){
 if(data.phone_template)registerSupplierTemplates([data.phone_template]);
 const pass=readPass(data.snapshot.code,data.snapshot);
 return {id:data.reference,...(data.phone_template?{phoneTemplate:data.phone_template}:{}),server:true,progress:data.progress||null,fulfillmentType:data.fulfillment_type||'unspecified',fulfillment:data.fulfillment||null,refund:data.refund||null,mode:data.mode,status:data.status==='completed'?'collected':data.status,priceCents:Math.round(Number(data.amount)*100),currency:data.currency,revision:data.revision,stationId:data.station_id,customerEmail:data.customer_email,pass,oldCodes:[...new Set([...(previous?.oldCodes||[]),...(previous&&previous.pass.code!==pass.code?[previous.pass.code]:[])])],createdAt:Date.parse(data.created_at),updatedAt:Date.parse(data.updated_at)};
}
export function checkoutBody(draft,{accepted,email='',account,amount,provider='demo',mode='demo'}){
 const customer=account?.authenticated?account.customer:null;
 return {request_key:draft.requestKey,fulfillment_type:draft.fulfillmentType||'pickup',payment_provider:provider,payment_mode:mode,accepted,
  customer_id:customer?.id||null,...(customer?{}:{customer_email:email}),expected_amount:amount,snapshot:draft.pass};
}
export function checkoutEmailField(account){
 if(account?.authenticated&&account.customer)return `<div class="order-email order-email-signed"><span>Order email</span><strong translate="no">${esc(account.customer.email)}</strong><small>Using your signed-in email for support and payment receipts.</small></div>`;
 return '<label class="order-email">Email (optional)<input name="email" type="email" maxlength="254" autocomplete="email" placeholder="you@example.com"><small>Saved with your order for support and payment receipts.</small></label>';
}

export async function getPaymentConfig(fetcher=fetch,retryOptions){
 const response=await retryUnavailableRead(()=>fetcher('/api/v1/store/payment-config/',{credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(10000)}),retryOptions);
 if(response.status===503)throw Error('Checkout is temporarily unavailable after 3 retries. Your design is saved. Please try again later.');
 if(!response.ok)throw Error('Payment settings could not be loaded. Please reload and try again.');
 const data=await response.json();
 if(!['demo','stripe','airwallex','free'].includes(data.provider)||!['demo','test','live'].includes(data.mode)||typeof data.available!=='boolean')throw Error('Invalid payment settings.');
 if(data.provider==='free'&&(data.mode!=='test'||data.zero_price_test!==true))throw Error('Invalid payment settings.');
 return data;
}
export function stripeCheckoutUrl(value){
 const url=new URL(value);
 if(url.protocol!=='https:'||url.hostname!=='checkout.stripe.com'||url.username||url.password)throw Error('Invalid Stripe checkout address.');
 return url.href;
}

export function mergeOrderProgress(order,data){
 if(data.reference!==order.id)throw Error('Order identity mismatch.');
 return {...order,progress:data.progress||null,fulfillment:data.fulfillment||null,refund:data.refund||null,
  status:data.status==='completed'?'collected':data.status,updatedAt:Date.parse(data.updated_at)};
}
