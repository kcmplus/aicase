const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));

// Only use for reads: one initial request, then at most three retries on 503.
export async function retryUnavailableRead(request,{sleep=wait}={}){
 for(let retry=0;;retry++){
  const response=await request();
  if(response.status!==503||retry===3)return response;
  await response.body?.cancel();
  await sleep(1000*2**retry);
 }
}
