<script setup>
import {computed,onMounted,onBeforeUnmount,ref} from 'vue';
import {onBeforeRouteLeave} from 'vue-router';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api,allRecords,can} from './api.js';
import {imageAttributes} from '../../storefront/image-view.js';
import AIResultsField from './AIResultsField.vue';

const rows=ref([]),styles=ref([]),models=ref([]),query=ref(''),loading=ref(false),error=ref('');
const open=ref(false),form=ref(null),saved=ref(''),reading=ref(false),saving=ref(false),uploading=ref(false),formError=ref('');
const busy=computed(()=>reading.value||saving.value||uploading.value);
const editable=computed(()=>can(`management_api.${form.value?.id?'change':'add'}_aiexample`));
const dirty=computed(()=>form.value&&JSON.stringify(form.value)!==saved.value);
const filtered=computed(()=>rows.value.filter(row=>`${row.name} ${row.subject} ${row.results.map(item=>`${item.style_name} ${item.phone_model_name} ${item.prompt}`).join(' ')}`.toLowerCase().includes(query.value.trim().toLowerCase())));
const filled=row=>row.results.filter(item=>item.prompt?.trim()).length;
async function load(){
 loading.value=true;error.value='';
 try{rows.value=await allRecords('ai-examples');}catch(e){error.value=e.message;}finally{loading.value=false;}
}
function accept(data){form.value={id:data.id,revision:data.revision||0,code:data.code||'',name:data.name||'',subject:data.subject||'',sort_order:data.sort_order||0,active:data.active??true,original_path:data.original_path||'',results:structuredClone(data.results||[])};saved.value=JSON.stringify(form.value);}
async function edit(row){
 open.value=true;form.value=null;formError.value='';reading.value=true;
 try{
  accept(row?await api(`admin/ai-examples/${row.id}/`):{});
  const options=await Promise.allSettled([can('management_api.view_aistyle')?allRecords('ai-styles'):[],can('management_api.view_phonemodel')?allRecords('phone-models'):[]]);
  styles.value=options[0].status==='fulfilled'?options[0].value:[];
  models.value=options[1].status==='fulfilled'?options[1].value:[];
  if(options.some(result=>result.status==='rejected'))formError.value='部分风格或机型选项加载失败，已有关联会保留。请关闭后重新打开重试。';
 }catch(e){formError.value=e.message;}finally{reading.value=false;}
}
async function save(){
 if(!form.value||!editable.value||busy.value)return;
 formError.value='';
 if(!form.value.code.trim()||!form.value.name.trim()||!form.value.subject.trim()||!form.value.original_path){formError.value='请填写案例标识、名称、说明和原图。';return;}
 if(!form.value.results.length||form.value.results.some(row=>!row.style||!row.image_path)){formError.value='每个案例至少添加一个风格，并为每个效果选择风格和效果图。';return;}
 saving.value=true;
 try{
  const {id,...body}=form.value;
  body.results=body.results.map(row=>({style:row.style,image_path:row.image_path,prompt:row.prompt||'',phone_model:row.phone_model||null}));
  accept(await api(`admin/ai-examples/${id?id+'/':''}`,{method:id?'PATCH':'POST',body}));
  ElMessage.success('案例图片与提示词已一起保存');await load();
 }catch(e){formError.value=e.message;}finally{saving.value=false;}
}
async function confirmDiscard(){
 if(busy.value)return false;
 if(!dirty.value)return true;
 try{await ElMessageBox.confirm('案例有未保存的图片或提示词修改。','离开案例编辑',{confirmButtonText:'丢弃修改',cancelButtonText:'继续编辑',type:'warning'});return true;}catch{return false;}
}
async function close(done){if(await confirmDiscard()){form.value=null;typeof done==='function'?done():open.value=false;}}
async function canLeave(){if(!await confirmDiscard())return false;form.value=null;open.value=false;return true;}
defineExpose({canLeave,load});
async function upload(event){
 const file=event.target.files?.[0];if(!file)return;
 uploading.value=true;formError.value='';
 try{const body=new FormData();body.append('file',file);form.value.original_path=(await api('admin/uploads/',{method:'POST',body})).path;}
 catch(e){formError.value=e.message;}finally{uploading.value=false;event.target.value='';}
}
async function remove(row){
 try{await ElMessageBox.confirm(`删除“${row.name}”及其案例提示词？共用风格与机型配置会保留。`,'删除案例',{confirmButtonText:'删除案例',cancelButtonText:'取消',type:'warning'});await api(`admin/ai-examples/${row.id}/`,{method:'DELETE'});await load();}
 catch(e){if(e!=='cancel'&&e!=='close')ElMessage.error(e.message||'删除失败');}
}
function beforeUnload(event){if(dirty.value){event.preventDefault();event.returnValue='';}}
onMounted(()=>{load();window.addEventListener('beforeunload',beforeUnload);});
onBeforeUnmount(()=>window.removeEventListener('beforeunload',beforeUnload));
onBeforeRouteLeave(confirmDiscard);
</script>

<template>
 <section class="case-workbench">
  <div class="case-toolbar"><div><h2>从效果找到提示词</h2><p class="muted">一张原图可以关联多个风格效果，每个效果保存自己的完整提示词和适配机型。</p></div><el-button v-if="can('management_api.add_aiexample')" type="primary" @click="edit(null)">新增案例</el-button></div>
  <div class="case-search"><el-input v-model="query" aria-label="搜索案例与提示词" clearable placeholder="搜索案例、风格、机型或提示词"/><span class="muted">{{filtered.length}} 个案例 · {{filtered.reduce((sum,row)=>sum+row.results.length,0)}} 个效果</span><el-button :loading="loading" @click="load">刷新案例</el-button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
  <div v-loading="loading" class="case-grid">
   <article v-for="row in filtered" :key="row.id" class="case-card">
    <div class="case-comparison"><figure><img v-bind="imageAttributes(row.original_path,{sizes:'200px'})" :alt="row.name+' 原图'"/><figcaption>原图</figcaption></figure><figure><img v-if="row.results[0]" v-bind="imageAttributes(row.results[0].image_path,{sizes:'200px'})" :alt="row.name+' 效果图'"/><figcaption>效果图</figcaption></figure></div>
    <div class="case-body"><div class="case-title"><h3>{{row.name}}</h3><el-tag v-if="!row.active" type="info" size="small">已停用</el-tag></div><p>{{row.subject}}</p><div class="case-tags"><el-tag v-for="effect in row.results" :key="effect.style" size="small" type="info">{{effect.style_name}}</el-tag></div><p class="case-meta">{{filled(row)}} / {{row.results.length}} 份提示词 · {{[...new Set(row.results.map(item=>item.phone_model_name||'通用构图'))].join('、')}}</p><div class="case-actions"><el-button type="primary" plain :aria-label="'查看案例 '+row.name" @click="edit(row)">{{can('management_api.change_aiexample')?'查看 / 编辑提示词':'查看提示词'}}</el-button><el-button v-if="can('management_api.delete_aiexample')" link type="danger" :aria-label="'删除案例 '+row.name" @click="remove(row)">删除</el-button></div></div>
   </article>
  </div>
  <el-empty v-if="!loading&&!error&&!filtered.length" description="暂无匹配案例，可新增原图、效果图及提示词"/>
  <el-drawer v-model="open" :title="form?.id?'案例与提示词 · '+form.name:'新增案例与提示词'" size="min(960px, 100vw)" :before-close="close" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" destroy-on-close>
   <div v-loading="reading"><el-alert v-if="formError" :title="formError" type="error" :closable="false" class="form-alert"/>
    <template v-if="form">
     <el-alert title="修改提示词不会自动重生成效果图。请保存实际测试使用的内容，便于后续复用。" type="info" :closable="false" class="form-alert"/>
     <el-form label-position="top" :disabled="!editable||busy" @submit.prevent="save"><div class="case-basics"><el-form-item label="案例名称"><el-input v-model="form.name" aria-label="案例名称" maxlength="100"/></el-form-item><el-form-item label="唯一标识"><el-input v-model="form.code" aria-label="案例唯一标识" :disabled="Boolean(form.id)" maxlength="80" placeholder="例如 pet-gouache"/></el-form-item></div><el-form-item label="案例说明"><el-input v-model="form.subject" aria-label="案例说明" maxlength="200"/></el-form-item><div class="case-basics"><el-form-item label="显示顺序"><el-input-number v-model="form.sort_order" :min="0" :max="32767" aria-label="案例显示顺序"/></el-form-item><el-form-item label="前台展示"><el-switch v-model="form.active" aria-label="前台展示案例"/></el-form-item></div><el-form-item label="原图"><div class="case-original"><img v-if="form.original_path" v-bind="imageAttributes(form.original_path,{sizes:'120px'})" alt="案例原图预览"/><div><el-input v-model="form.original_path" aria-label="案例原图路径" placeholder="/assets/... 或上传原图"/><label v-if="editable" class="upload-button">上传原图<input type="file" accept="image/png,image/jpeg,image/webp" :disabled="busy" @change="upload"/></label></div></div></el-form-item></el-form>
     <AIResultsField v-model="form.results" :styles="styles" :models="models" :disabled="!editable||busy" @busy="uploading=$event" @error="formError=$event"/>
    </template>
   </div>
   <template #footer><div class="drawer-footer"><span>{{dirty?'有未保存的修改':'案例图片与提示词一起保存'}}</span><el-button :disabled="busy" @click="close">关闭</el-button><el-button v-if="editable&&form" type="primary" :loading="saving" :disabled="busy||!dirty" @click="save">保存案例与提示词</el-button></div></template>
  </el-drawer>
 </section>
</template>

<style scoped>
.case-toolbar{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:24px 0}.case-toolbar h2{font-size:20px;margin:0 0 10px}.case-toolbar p{font-size:12px;line-height:1.7;margin:0}.case-search{display:flex;align-items:center;gap:18px;margin-bottom:22px;flex-wrap:wrap}.case-search .el-input{max-width:330px}.case-search span{font-size:12px}.case-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:22px}.case-card{background:white;border:1px solid #e0e7e2;border-radius:12px;overflow:hidden}.case-comparison{display:grid;grid-template-columns:1fr 1fr;gap:7px;background:#eef2ed;padding:12px}.case-comparison figure{margin:0;position:relative}.case-comparison img{width:100%;height:235px;object-fit:contain;border-radius:6px;background:#e3e9e2}.case-comparison figcaption{position:absolute;bottom:10px;left:8px;font-size:10px;padding:4px 8px;border-radius:4px;background:#fffffff0;color:#44554a}.case-body{padding:20px}.case-title{display:flex;align-items:center;justify-content:space-between;gap:8px}.case-title h3{margin:0;font-size:17px}.case-body>p{font-size:12px;line-height:1.8;color:#7c8a80}.case-tags{display:flex;flex-wrap:wrap;gap:7px}.case-body .case-meta{font-size:11px;min-height:38px}.case-actions{display:flex;justify-content:space-between;gap:10px}.case-basics{display:grid;grid-template-columns:1fr 1fr;gap:20px}.case-original{display:flex;gap:20px;width:100%;align-items:center}.case-original img{width:100px;height:145px;object-fit:contain;background:#edf2ec;border-radius:8px}.case-original>div{flex:1;min-width:0}.case-original .upload-button{margin-top:12px}@media(max-width:650px){.case-basics{grid-template-columns:1fr;gap:0}.case-toolbar{align-items:start}.case-search{gap:10px}.case-grid{grid-template-columns:1fr}}
</style>
