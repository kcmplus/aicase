<script setup>
import {computed,ref,onBeforeUnmount} from 'vue';
import {api,allRecords,can} from './api.js';
import PhoneTemplateInfo from './PhoneTemplateInfo.vue';
const props=defineProps({model:{type:Object,default:null},disabled:Boolean});
const emit=defineEmits(['updated','busy']);
const busy=ref(false),error=ref(''),progress=ref(''),result=ref(null);
const editable=computed(()=>can('management_api.change_phonemodel'));
const sources=computed(()=>props.model?.template_sources||[]);
const specs=v=>(v||[]).map(s=>`${s.spec_name}：${s.spec_value}`).join(' · ');
let alive=true;
onBeforeUnmount(()=>{alive=false;});
async function syncOne(source){
 if(busy.value||props.disabled)return;
 busy.value=true;emit('busy',true);error.value='';
 try{await api(`admin/phone-models/${props.model.id}/import-template/`,{method:'POST',body:{source:source.id,refresh:true}});}
 catch(e){error.value=e.message;}
 finally{emit('updated');busy.value=false;emit('busy',false);}
}
async function syncAll(){
 if(busy.value||props.disabled)return;
 busy.value=true;emit('busy',true);error.value='';result.value=null;
 const summary={imported:0,masks:0,missing:0,kept:0,failed:[]};
 try{
  progress.value='正在读取机型模板来源…';
  const models=await allRecords('phone-models');
  const work=[];
  for(const model of models)for(const source of model.template_sources||[]){
   if(!source.has_source)summary.missing++;
   else if(source.status==='imported')summary.kept++;
   else work.push({model,source});
  }
  for(let i=0;i<work.length&&alive;i++){
   const {model,source}=work[i];progress.value=`正在同步 ${i+1} / ${work.length}：${model.name}`;
   try{const data=await api(`admin/phone-models/${model.id}/import-template/`,{method:'POST',body:{source:source.id}});summary.imported++;if(data.mask)summary.masks++;}
   catch(e){summary.failed.push(`${model.name} · 商品 ${source.goods_id}：${e.message}`);}
  }
  result.value=summary;
 }catch(e){error.value=e.message;}
 finally{progress.value='';busy.value=false;emit('busy',false);emit('updated');}
}
</script>
<template>
 <section class="model-templates">
  <template v-if="!model">
   <div class="template-actions"><div><strong>机型底图与遮罩</strong><p>从已映射商品导入供应商图片，统一在每个机型的「底图」中查看。不同设备、款式分别保留。</p></div><el-button v-if="editable" :loading="busy" :disabled="disabled" @click="syncAll">同步供应商底图</el-button></div>
   <p v-if="progress" role="status">{{progress}}</p>
   <el-alert v-if="result" :title="`本次导入 ${result.imported} 张底图，生成 ${result.masks} 张预览遮罩；已有 ${result.kept} 张，缺少链接 ${result.missing} 项，失败 ${result.failed.length} 项。`" :type="result.failed.length?'warning':'success'" :closable="false"/>
   <p v-for="message in result?.failed||[]" :key="message" class="error-text">{{message}}</p>
  </template>
  <template v-else>
   <p>底图保留供应商原始像素尺寸。预览遮罩从透明区域提取，实际打印尺寸和范围尚待确认。</p>
   <PhoneTemplateInfo :model="model.name"/>
   <el-empty v-if="!sources.length" description="尚未关联供应商商品，可在商品与库存中同步机型。"/>
   <article v-for="source in sources" :key="source.id" class="source-card">
    <div class="source-heading"><div><strong>{{model.name}}</strong><p>{{source.device_name}} · 商品 {{source.goods_id}}</p><small>{{specs(source.specs)}}</small></div><el-button v-if="editable&&source.has_source" :loading="busy" :disabled="disabled" @click="syncOne(source)">{{source.image?'重新获取底图':'同步底图'}}</el-button></div>
    <div v-if="source.image" class="source-images">
     <figure><a :href="source.image" target="_blank" rel="noopener"><img :src="source.image" :alt="model.name+' 供应商底图'"/></a><figcaption>供应商底图 · {{source.width}} × {{source.height}} px</figcaption></figure>
     <figure v-if="source.mask"><a :href="source.mask" target="_blank" rel="noopener" aria-label="查看预览遮罩"><span class="source-mask" :style="{aspectRatio:source.width+'/'+source.height,maskImage:`url(${source.mask})`,WebkitMaskImage:`url(${source.mask})`}"></span></a><figcaption>预览遮罩 · 自动生成</figcaption></figure>
     <p v-else>遮罩待补充</p>
    </div>
    <el-alert v-else :title="source.has_source?'底图尚未导入，可点击同步。':'供应商尚未提供模板链接。'" type="info" :closable="false"/>
    <p v-if="source.mask_note">{{source.mask_note}}</p><p v-if="source.error" class="error-text">{{source.error}}</p>
   </article>
  </template>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
 </section>
</template>
<style scoped>
.model-templates{margin:16px 0 24px}.template-actions,.source-heading{display:flex;justify-content:space-between;align-items:center;gap:16px}.model-templates p,.model-templates small{color:#65716b;font-size:12px;line-height:1.8}.template-actions{padding:16px;background:#f3f8f6;border-radius:12px}.template-actions p{margin:6px 0 0}.source-card{margin:18px 0;padding:18px;border:1px solid #dce5e2;border-radius:12px}.source-images{display:flex;align-items:center;justify-content:center;gap:32px;padding:24px 0}.source-images figure{margin:0;text-align:center}.source-images img,.source-mask{display:block;width:125px;height:auto;max-height:310px;object-fit:contain;margin:auto}.source-mask{background:#368e87;mask-size:100% 100%;-webkit-mask-size:100% 100%;mask-mode:alpha}.source-images figcaption{font-size:11px;color:#65716b;margin-top:12px}.model-templates .error-text{color:#b43e3e}@media(max-width:600px){.template-actions,.source-heading{align-items:flex-start;flex-direction:column}.source-images{gap:16px}.source-images img,.source-mask{width:95px}}
</style>
