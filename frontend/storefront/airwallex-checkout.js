// Load only when an Airwallex order is paid; credentials never enter storage.
let sdkPromise;
export function loadAirwallexSDK(){
 if(!sdkPromise)sdkPromise=new Promise((resolve,reject)=>{
  const script=document.createElement('script');
  const fail=()=>{clearTimeout(timer);script.onload=null;script.onerror=null;script.remove();sdkPromise=null;reject(Error('The payment page could not be loaded. Please try again.'));};
  const timer=setTimeout(fail,15000);
  script.src='https://static.airwallex.com/components/sdk/v1/index.js';script.async=true;
  script.onerror=fail;
  script.onload=()=>{clearTimeout(timer);if(window.AirwallexComponentsSDK?.init)resolve(window.AirwallexComponentsSDK);else fail();};
  document.head.append(script);
 });
 return sdkPromise;
}
export function airwallexOptions(data){
 const c=data?.checkout,order=data?.order;
 if(data?.provider!=='airwallex'||!c||!order||!['airwallex_test','airwallex_live'].includes(order.mode)
  ||c.env!==(order.mode==='airwallex_live'?'prod':'demo')||c.mode!=='payment'||c.currency!==order.currency||c.currency!=='USD'
  ||!/^int_[A-Za-z0-9_-]{1,240}$/.test(c.intent_id)||typeof c.client_secret!=='string'||!c.client_secret
  ||order.status!=='pending')throw Error('Invalid Airwallex checkout. Refresh your order and try again.');
 const url=new URL(c.successUrl);
 if(url.protocol!=='https:'||url.username||url.password||url.search||url.pathname!=='/'
  ||url.hash!==`#payment?order=${order.reference}&result=success`)throw Error('Invalid payment return address.');
 return {env:c.env,mode:'payment',currency:c.currency,intent_id:c.intent_id,client_secret:c.client_secret,successUrl:url.href};
}
export async function openAirwallexCheckout(data,loadSDK=loadAirwallexSDK){
 const options=airwallexOptions(data);
 try{
  const sdk=await loadSDK();
  const {payments}=await sdk.init({env:options.env,enabledElements:['payments']});
  await payments.redirectToCheckout(options);
 }catch{throw Error('The payment page could not be opened. Your order is saved; please try again.');}
}
