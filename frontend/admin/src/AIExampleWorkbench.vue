<script setup>
import {computed,nextTick,onMounted,onBeforeUnmount,ref} from 'vue';
import {onBeforeRouteLeave} from 'vue-router';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api,allRecords,can} from './api.js';
import {imageAttributes} from '../../storefront/image-view.js';
import {groupAIExamples} from '../../storefront/ai-example-groups.js';
import AIResultsField from './AIResultsField.vue';

const rows=ref([]),styles=ref([]),models=ref([]),query=ref(''),loading=ref(false),error=ref('');
const open=ref(false),form=ref(null),saved=ref(''),reading=ref(false),saving=ref(false),uploading=ref(false),formError=ref(''),initialStyle=ref(null);
const effectEditor=ref(null);
const busy=computed(()=>reading.value||saving.value||uploading.value);
const editable=computed(()=>can(`management_api.${form.value?.id?'change':'add'}_aiexample`));
const dirty=computed(()=>form.value&&JSON.stringify(form.value)!==saved.value);
const filtered=computed(()=>groupAIExamples(rows.value).filter(group=>group.examples.some(row=>`${row.name} ${row.name_zh} ${row.subject} ${row.subject_zh} ${row.results.map(item=>`${item.style_name} ${item.phone_model_name} ${item.prompt}`).join(' ')}`.toLowerCase().includes(query.value.trim().toLowerCase()))).map(group=>({...group,effects:group.examples.flatMap(row=>row.results.map(result=>({row,result})))})));
const filled=group=>group.effects.filter(({result})=>result.prompt?.trim()).length;
async function load(){
 loading.value=true;error.value='';
 try{rows.value=await allRecords('ai-examples');}catch(e){error.value=e.message;}finally{loading.value=false;}
}
function accept(data){form.value={id:data.id,revision:data.revision||0,code:data.code||'',name:data.name||'',name_zh:data.name_zh||'',subject:data.subject||'',subject_zh:data.subject_zh||'',sort_order:data.sort_order||0,active:data.active??true,original_path:data.original_path||'',results:structuredClone(data.results||[])};saved.value=JSON.stringify(form.value);}
async function edit(row,style=null){
 initialStyle.value=style;
 open.value=true;form.value=null;formError.value='';reading.value=true;
 try{
  accept(row?await api(`admin/ai-examples/${row.id}/`):{});
  const options=await Promise.allSettled([can('management_api.view_aistyle')?allRecords('ai-styles'):[],can('management_api.view_phonemodel')?allRecords('phone-models'):[]]);
  styles.value=options[0].status==='fulfilled'?options[0].value:[];
  models.value=options[1].status==='fulfilled'?options[1].value:[];
  if(options.some(result=>result.status==='rejected'))formError.value='部分风格或机型选项加载失败，已有关联会保留。请关闭后重新打开重试。';
 }catch(e){formError.value=e.message;}finally{reading.value=false;}
 await nextTick();revealEffect();
}
function revealEffect(){if(initialStyle.value!==null)effectEditor.value?.$el.querySelector('.recipe-editor')?.scrollIntoView({block:'start'});}
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
  <div class="case-toolbar"><div><h2>一组原图，多种 AI 效果</h2><p class="muted">与用户端一致，使用同一张原图的案例合并展示。点击效果图即可编辑对应的英文提示词。</p></div><el-button v-if="can('management_api.add_aiexample')" type="primary" @click="edit(null)">新增案例</el-button></div>
  <div class="case-search"><el-input v-model="query" aria-label="搜索案例与提示词" clearable placeholder="搜索案例、风格、机型或提示词"/><span class="muted">{{filtered.length}} 组图片 · {{filtered.reduce((sum,group)=>sum+group.effects.length,0)}} 个效果</span><el-button :loading="loading" @click="load">刷新案例</el-button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
  <div v-loading="loading" class="case-grid">
   <article v-for="group in filtered" :key="group.key" class="case-card">
    <header class="case-body case-title"><div><h3>{{group.example.name_zh||group.example.name}}</h3><p>{{group.example.subject_zh||group.example.subject}}</p></div><el-tag type="info">{{group.effects.length}} 个效果</el-tag></header>
    <div class="case-comparison">
     <figure class="case-source"><img v-bind="imageAttributes(group.original,{sizes:'180px'})" :alt="group.example.name+' 原图'"/><figcaption>原图</figcaption></figure>
     <div class="case-result-grid"><button v-for="{row,result} in group.effects" :key="row.id+'-'+result.style" type="button" class="case-result" :aria-label="'查看效果 '+result.style_name+' · '+row.name" @click="edit(row,result.style)"><img v-bind="imageAttributes(result.image_path,{sizes:'200px'})" :alt="result.style_name+' 效果图'"/><strong>{{result.style_name}}</strong><span>{{result.prompt?.trim()?'查看提示词':'待填写提示词'}}<span v-if="!row.active"> · 案例已停用</span></span></button></div>
    </div>
    <footer class="case-body case-footer"><p class="case-meta">{{filled(group)}} / {{group.effects.length}} 份提示词 · {{group.examples.length}} 个关联案例</p><div class="case-records"><div v-for="row in group.examples" :key="row.id" class="case-actions"><span>{{row.name_zh||row.name}}</span><el-tag v-if="!row.active" type="info" size="small">已停用</el-tag><el-button link type="primary" :aria-label="'查看案例 '+row.name" @click="edit(row)">{{can('management_api.change_aiexample')?'编辑案例':'查看案例'}}</el-button><el-button v-if="can('management_api.delete_aiexample')" link type="danger" :aria-label="'删除案例 '+row.name" @click="remove(row)">删除</el-button></div></div></footer>
   </article>
  </div>
  <el-empty v-if="!loading&&!error&&!filtered.length" description="暂无匹配案例，可新增原图、效果图及提示词"/>
  <el-drawer v-model="open" :title="form?.id?'案例与提示词 · '+form.name:'新增案例与提示词'" size="min(960px, 100vw)" :before-close="close" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" destroy-on-close @opened="revealEffect">
   <div v-loading="reading"><el-alert v-if="formError" :title="formError" type="error" :closable="false" class="form-alert"/>
    <template v-if="form">
     <el-alert title="修改提示词不会自动重生成效果图。请保存实际测试使用的内容，便于后续复用。" type="info" :closable="false" class="form-alert"/>
     <el-form label-position="top" :disabled="!editable||busy" @submit.prevent="save"><div class="case-basics"><el-form-item label="案例名称（英文）"><el-input v-model="form.name" aria-label="案例名称（英文）" maxlength="100"/></el-form-item><el-form-item label="唯一标识"><el-input v-model="form.code" aria-label="案例唯一标识" :disabled="Boolean(form.id)" maxlength="80" placeholder="例如 pet-gouache"/></el-form-item></div><el-form-item label="案例说明（英文）"><el-input v-model="form.subject" aria-label="案例说明（英文）" maxlength="200"/></el-form-item><div class="case-basics"><el-form-item label="案例名称（中文，可选）"><el-input v-model="form.name_zh" aria-label="案例中文名称" maxlength="120"/></el-form-item><el-form-item label="案例说明（中文，可选）"><el-input v-model="form.subject_zh" aria-label="案例中文说明" maxlength="200"/></el-form-item></div><div class="case-basics"><el-form-item label="显示顺序"><el-input-number v-model="form.sort_order" :min="0" :max="32767" aria-label="案例显示顺序"/></el-form-item><el-form-item label="前台展示"><el-switch v-model="form.active" aria-label="前台展示案例"/></el-form-item></div><el-form-item label="原图"><div class="case-original"><img v-if="form.original_path" v-bind="imageAttributes(form.original_path,{sizes:'120px'})" alt="案例原图预览"/><div><el-input v-model="form.original_path" aria-label="案例原图路径" placeholder="/assets/... 或上传原图"/><label v-if="editable" class="upload-button">上传原图<input type="file" accept="image/png,image/jpeg,image/webp" :disabled="busy" @change="upload"/></label></div></div></el-form-item></el-form>
     <AIResultsField ref="effectEditor" v-model="form.results" :styles="styles" :models="models" :original="form.original_path" :initial-style="initialStyle" :disabled="!editable||busy" @busy="uploading=$event" @error="formError=$event"/>
    </template>
   </div>
   <template #footer><div class="drawer-footer"><span>{{dirty?'有未保存的修改':'案例图片与提示词一起保存'}}</span><el-button :disabled="busy" @click="close">关闭</el-button><el-button v-if="editable&&form" type="primary" :loading="saving" :disabled="busy||!dirty" @click="save">保存案例与提示词</el-button></div></template>
  </el-drawer>
 </section>
</template>

<style scoped>
.case-toolbar{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:24px 0}.case-toolbar h2{font-size:20px;margin:0 0 10px}.case-toolbar p{font-size:12px;line-height:1.7;margin:0}
.case-search{display:flex;align-items:center;gap:18px;margin-bottom:22px;flex-wrap:wrap}.case-search .el-input{max-width:330px}.case-search span{font-size:12px}
.case-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:24px}.case-card{min-width:0;background:white;border:1px solid #e0e7e2;border-radius:12px;overflow:hidden}
.case-body{padding:20px 24px}.case-title{display:flex;align-items:center;justify-content:space-between;gap:14px}.case-title h3{margin:0;font-size:18px}.case-title p{font-size:12px;line-height:1.7;color:#7c8a80;margin:7px 0 0}
.case-comparison{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,4fr);gap:20px;background:#f7f9f6;padding:18px 24px;align-items:start}
.case-source{margin:0;min-width:0;padding-right:16px;border-right:1px solid #dce5dc}.case-source img,.case-result img{display:block;width:100%;height:200px;object-fit:contain;border-radius:7px;background:#e9eee7}
.case-source figcaption{font-size:12px;line-height:1.5;color:#697a70;margin-top:12px;text-align:center}
.case-result-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;align-items:start}
.case-result{display:flex;flex-direction:column;min-width:0;border:1px solid #dce5dc;border-radius:9px;background:white;padding:6px;cursor:pointer;text-align:left;color:#314b3e;transition:border-color .15s,box-shadow .15s}
.case-result:hover{border-color:#268278;box-shadow:0 3px 12px #28564916}.case-result:focus-visible{outline:3px solid #196967;outline-offset:3px}.case-result strong{font-size:12px;font-weight:600;line-height:1.5;margin:10px 4px 4px;overflow-wrap:anywhere}.case-result>span{font-size:10px;line-height:1.6;color:#7c8a80;margin:0 4px 5px}
.case-footer{padding-top:14px;padding-bottom:16px}.case-meta{font-size:11px;color:#7c8a80;line-height:1.6;margin:0 0 10px}.case-records{display:flex;gap:8px 20px;flex-wrap:wrap}.case-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:11px}.case-actions .el-button+.el-button{margin-left:0}.case-actions>span{color:#52685b}
.case-basics{display:grid;grid-template-columns:1fr 1fr;gap:20px}.case-original{display:flex;gap:20px;width:100%;align-items:center}.case-original img{width:100px;height:145px;object-fit:contain;background:#edf2ec;border-radius:8px}.case-original>div{flex:1;min-width:0}.case-original .upload-button{margin-top:12px}
@media(max-width:1100px){.case-comparison{grid-template-columns:minmax(0,1fr) minmax(0,3fr);gap:14px}.case-result-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.case-source img,.case-result img{height:170px}}
@media(max-width:650px){.case-basics{grid-template-columns:1fr;gap:0}.case-toolbar{align-items:start}.case-search{gap:10px}.case-body{padding:16px}.case-comparison{padding:14px;gap:10px;grid-template-columns:minmax(0,1fr) minmax(0,2fr)}.case-result-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.case-source{padding-right:8px}.case-source img,.case-result img{height:auto;aspect-ratio:2/3}.case-result{padding:4px}.case-result strong{font-size:10px}.case-result>span{font-size:9px}}
</style>
