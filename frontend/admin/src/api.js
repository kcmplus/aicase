import {reactive} from 'vue';
import {registerImageVariants} from '../../storefront/image-view.js';
export const session = reactive({user:null,ready:false});
let csrfToken = '';
export function can(permission){return Boolean(session.user?.is_superuser || session.user?.permissions.includes(permission));}
export async function api(path,options={}){
  const method=options.method||'GET';
  if(!['GET','HEAD'].includes(method)&&!csrfToken){const result=await api('auth/csrf/');csrfToken=result.csrfToken;}
  const headers={Accept:'application/json',...options.headers};
  let body=options.body;
  if(body!==undefined && !(body instanceof FormData)){headers['Content-Type']='application/json';body=JSON.stringify(body);}
  if(!['GET','HEAD'].includes(method))headers['X-CSRFToken']=csrfToken;
  const response=await fetch('/api/v1/'+path,{...options,method,body,headers,credentials:'same-origin'});
  let data=null;
  if(response.status!==204){const text=await response.text();try{data=JSON.parse(text);}catch{data={detail:'服务暂时不可用，请稍后重试。'};}}
  if(!response.ok){
    if(response.status===401 || (response.status===403 && data?.code==='not_authenticated')){session.user=null;if(window.location.pathname!=='/admin/login')window.location.assign('/admin/login');}
    const error=new Error(data?.detail||Object.entries(data||{}).map(([key,value])=>`${key}: ${Array.isArray(value)?value.join('；'):JSON.stringify(value)}`).join('；')||'操作失败');
    error.status=response.status;throw error;
  }
  if(data?.csrfToken)csrfToken=data.csrfToken;
  registerImageVariants(data?.image_variants);
  if(Array.isArray(data?.results))for(const record of data.results)registerImageVariants(record.image_variants);
  return data;
}
export async function restoreSession(){
  try{session.user=await api('auth/session/');}catch(error){if(error.status!==403&&error.status!==401)throw error;session.user=null;if(window.location.pathname!=='/admin/login')window.location.assign('/admin/login');}
  finally{session.ready=true;}
}
export async function allRecords(resource){
  const rows=[];let page=1;
  while(true){const result=await api(`admin/${resource}/?page=${page}`);rows.push(...result.results);if(!result.next)break;page++;if(page>100)throw new Error('选项过多，请先精简筛选。');}
  return rows;
}
