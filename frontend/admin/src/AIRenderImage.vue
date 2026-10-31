<script setup>
import {computed,onBeforeUnmount,ref,watch} from 'vue';
import {ElMessage} from 'element-plus';

const props=defineProps({record:{type:Object,required:true},kind:{type:String,default:'result'}});
const original=computed(()=>props.kind==='original'),meta=computed(()=>original.value?props.record.original:props.record.image);
const title=computed(()=>original.value?'上传原图':'生成结果');
const preview=ref(''),loading=ref(false),downloading=ref(false),error=ref(''),gone=ref(false);
const labels={pending:'图片生成中',none:'此任务没有生成图片',expired:'图片已到期，无法预览或下载',deleted:'图片已按保留期限清理',missing:'此记录没有可用的图片资源'};
const date=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'未记录';
const available=computed(()=>meta.value?.state==='available'&&!gone.value);
const size=computed(()=>`${((meta.value?.size_bytes||0)/1024/1024).toFixed(2)} MB`);
let previewRequest,downloadRequest,generation=0;
function release(){if(preview.value)URL.revokeObjectURL(preview.value);preview.value='';}
async function getImage(url,signal){
 const response=await fetch(url,{credentials:'same-origin',cache:'no-store',signal});
 if(!response.ok){
  const err=Error(response.status===410?'图片已到期，无法预览或下载。':response.status===403?'登录已失效或没有访问权限，请重新登录。':'图片暂时无法读取，请稍后重试。');
  err.status=response.status;throw err;
 }
 if(!['image/png','image/jpeg','image/webp'].includes(response.headers.get('content-type')?.split(';')[0]))throw Error('未能读取图片，请刷新页面后重试。');
 return response.blob();
}
function failed(e){
 error.value=e.message;
 if([404,410].includes(e.status)){gone.value=true;release();}
}
async function load(){
 const run=++generation;
 previewRequest?.abort();release();error.value='';gone.value=false;loading.value=false;
 if(meta.value?.state!=='available')return;
 previewRequest=new AbortController();loading.value=true;
 try{const blob=await getImage(meta.value.preview_url,previewRequest.signal);if(run===generation)preview.value=URL.createObjectURL(blob);}
 catch(e){if(run===generation&&e.name!=='AbortError')failed(e);}
 finally{if(run===generation)loading.value=false;}
}
async function download(){
 if(downloading.value||!available.value)return;
 const run=generation,filename=meta.value.filename,url=meta.value.download_url;
 downloading.value=true;downloadRequest=new AbortController();
 try{
  const blob=await getImage(url,downloadRequest.signal);
  if(run!==generation)return;
  const objectUrl=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=objectUrl;link.download=filename;document.body.appendChild(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(objectUrl),1000);
 }catch(e){if(run===generation&&e.name!=='AbortError'){failed(e);ElMessage.error(e.message);}}
 finally{if(run===generation)downloading.value=false;}
}
watch(()=>[props.record.id,props.kind,meta.value?.state],()=>{downloadRequest?.abort();downloading.value=false;load();},{immediate:true});
onBeforeUnmount(()=>{generation++;previewRequest?.abort();downloadRequest?.abort();release();});
</script>

<template>
 <section class="render-image" :aria-label="title">
  <div class="image-heading"><h3>{{title}}</h3><el-button v-if="available" type="primary" :loading="downloading" @click="download">{{original?'下载原图':'下载结果'}}</el-button></div>
  <div v-loading="loading" class="preview-frame" :class="{empty:!preview}">
   <el-image v-if="preview" :src="preview" :preview-src-list="[preview]" preview-teleported fit="contain" :alt="title"/>
   <span v-else role="status">{{loading?'正在加载图片…':error||(original&&meta?.state==='missing'?'原图未保留，无法查看':labels[meta?.state])||'暂无图片'}}</span>
  </div>
  <p v-if="preview" class="image-help">点击图片放大 · {{meta.mime_type?.split('/')[1]?.toUpperCase()}} · {{size}}</p>
  <el-button v-if="error&&!gone" link type="primary" @click="load">重新加载图片</el-button>
  <p v-if="meta?.expires_at&&meta.state!=='missing'" class="image-help">保留至 {{date(meta.expires_at)}}，到期后无法预览或下载。</p>
  <p v-if="meta?.deleted_at" class="image-help">已于 {{date(meta.deleted_at)}} 清理图片，调用记录和费用仍保留。</p>
 </section>
</template>

<style scoped>
.render-image{margin-bottom:0}.image-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.image-heading{flex-wrap:wrap}.image-heading h3{margin:0;font-size:16px;color:#285843}.preview-frame{border:1px solid #e1e9e3;border-radius:12px;overflow:hidden;background:#f3f6f2;display:flex;align-items:center;justify-content:center;min-height:150px}.preview-frame .el-image{width:100%;height:300px;cursor:zoom-in}.preview-frame.empty{min-height:300px;box-sizing:border-box;padding:28px 20px;color:#7b8a81;font-size:13px;text-align:center}.image-help{font-size:12px;color:#73847b;line-height:1.8;margin:9px 0 0}@media(max-width:650px){.preview-frame .el-image{height:280px}.preview-frame.empty{min-height:280px}.image-heading{flex-wrap:wrap}}
</style>
