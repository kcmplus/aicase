import {AI_PROVIDER} from './runtime-catalog.js';
import {createAIOrder} from './ai-core.js';
import {importPhoto} from './simple-upload.js';
import {retryUnavailableRead} from './request-retry.js';

const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export async function aiRequest(path,{method='GET',body,fetcher=fetch,image=false,retryOptions}={}){
 const headers={'Content-Type':'application/json'};
 if(!['GET','HEAD'].includes(method)){
  const csrf=await fetcher('/api/v1/auth/csrf/',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(25000)});
  if(!csrf.ok)throw Error('Sign-in could not be reached. Please try again.');
  headers['X-CSRFToken']=(await csrf.json()).csrfToken;
 }
 const request=()=>fetcher('/api/v1/store/'+path,{method,credentials:'same-origin',cache:'no-store',
  headers,signal:AbortSignal.timeout(25000),
  ...(body===undefined?{}:{body:JSON.stringify(body)})});
 const retryAccount=method==='GET'&&path==='ai-account/';
 const response=await (retryAccount?retryUnavailableRead(request,retryOptions):request());
 if(retryAccount&&response.status===503){const error=Error('Account information is temporarily unavailable after 3 retries. Please try again later.');error.status=503;throw error;}
 if(response.ok&&image)return response.blob();
 let data;try{data=await response.json();}catch{throw Error('The AI service could not be reached. Please try again.');}
 if(!response.ok){const error=Error(typeof data.detail==='string'?data.detail:Object.values(data).flat().join(' '));error.status=response.status;throw error;}
 return data;
}
export function createLiveRender(input){
 if(!input.model)throw Error('Choose your phone model first.');
 return {...createAIOrder(input),mode:'live',version:3,model:input.model,phoneTemplateId:input.phoneTemplateId||'',caseMaterial:input.caseMaterial||'standard',priceCents:0,
  status:'awaiting_confirmation',payment:'unpaid',allocation:null,remoteId:null,resultPhoto:null};
}
export function mergeLiveRender(job,data){
 if(!uuid.test(data.id)||data.requestKey!==job.id.replace(/^AI-/,''))throw Error('The AI service returned an invalid render.');
 if(!['queued','generating','ready','failed','cancelled'].includes(data.status)||data.mode!=='live')throw Error('The AI service returned an invalid render.');
 if(data.composition?.version===1&&(data.composition.model!==job.model||data.composition.case_material!==(job.caseMaterial||'standard')||(job.phoneTemplateId&&data.composition.template_id!==job.phoneTemplateId)))throw Error('The AI service returned a different case configuration.');
 const result=data.status==='ready'?`/api/v1/store/ai-renders/${data.id}/image/`:null;
 if(data.result!==result)throw Error('The AI service returned an invalid image.');
 return {...job,remoteId:data.id,mode:'live',status:data.status,payment:data.payment,
  allocation:data.allocation,composition:data.composition?.version===1&&data.composition.fit==='blur'?{...data.composition}:null,paidAt:data.createdAt,startedAt:data.startedAt,completedAt:data.completedAt,
  errorCode:data.errorCode,errorMessage:data.errorMessage,result,imageExpired:Boolean(data.imageExpired),imageExpiresAt:data.imageExpiresAt||null};
}
export const getAIAccount=()=>aiRequest('ai-account/');
export const changeAIAccount=(action,accepted)=>aiRequest('ai-account/',{method:'POST',body:{action,accepted}});
export async function hydrateLiveImage(job){
 if(job.status==='ready'&&!job.resultPhoto&&!job.imageExpired){
  let blob;
  try{blob=await aiRequest(`ai-renders/${job.remoteId}/image/`,{image:true});}
  catch(e){if(e.status===410)return {...job,imageExpired:true};throw e;}
  const photo=await importPhoto(new File([blob],'ai-result.png',{type:blob.type}),{maxEdge:2000,quality:.92});
  if(photo.length>=3_000_000)throw Error('The generated image is too large to apply. Please try again.');
  return {...job,resultPhoto:photo};
 }
 return job;
}
export async function submitLiveRender(job,accepted){
 const data=await aiRequest('ai-renders/',{method:'POST',body:{request_key:job.id.replace(/^AI-/,''),
  accepted,photo:job.photo,style_id:job.styleId,model:job.model,phone_template_id:job.phoneTemplateId||'',case_material:job.caseMaterial||'standard',provider:AI_PROVIDER}});
 return hydrateLiveImage(mergeLiveRender(job,data));
}
export async function refreshLiveRender(job){
 if(!job.remoteId)return job;
 return hydrateLiveImage(mergeLiveRender(job,await aiRequest(`ai-renders/${job.remoteId}/`)));
}
export async function cancelLiveRender(job){
 if(!job.remoteId)return {...job,status:'cancelled',payment:'unpaid'};
 return mergeLiveRender(job,await aiRequest(`ai-renders/${job.remoteId}/`,{method:'POST',body:{action:'cancel'}}));
}

export function generatedPhotoPlacement(job){
 // Preserve the entire generated image; use the same fit as server composition geometry.
 return job?.composition?.version===1&&job.composition.fit==='blur'
  ?{x:50,y:50,scale:100,rotation:0,fit:'blur'}:null;
}
