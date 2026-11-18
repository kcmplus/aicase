<script setup>
import PhoneModelTemplates from './PhoneModelTemplates.vue';
import {imageAttributes} from "../../storefront/image-view.js";
import {computed,onMounted,onBeforeUnmount,ref,reactive,watch,toRaw} from 'vue';
import {ElMessage,ElMessageBox} from 'element-plus';
import {Plus,Search,Refresh,Upload} from '@element-plus/icons-vue';
import {api,can,session,allRecords} from './api.js';
import {resources,permissionFor,permissionModels,actionLabels,displayLabels} from './resources.js';
import AIResultsField from './AIResultsField.vue';
import OrderDetails from './OrderDetails.vue';
import {progressText,progressPaymentText,progressTime} from '../../storefront/order-progress.js';
import {startVisiblePolling} from '../../storefront/visible-polling.js';
import OrderCustomer from './OrderCustomer.vue';
import {onBeforeRouteLeave} from 'vue-router';
import {promptTemplates} from './prompt-templates.js';
const props=defineProps({resource:{type:String,required:true},embedded:Boolean});
const schema=computed(()=>resources[props.resource]);
const rows=ref([]),total=ref(0),page=ref(1),query=ref(''),active=ref(''),loading=ref(false),error=ref('');
const open=ref(false),saving=ref(false),editing=ref(null),form=reactive({}),options=reactive({}),permissions=ref([]),formError=ref(''),uploading=ref(false),optionLoading=ref(false);
let requestId=0,stopOrderPolling=()=>{};
const progressFilter=ref('');
const allowed=action=>can(permissionFor(props.resource,action))&&(!schema.value.access||session.user.is_superuser);
const permissionGroups=computed(()=>Object.entries(permissionModels).map(([model,name])=>({model,name,items:permissions.value.filter(p=>p.model===model)})).filter(g=>g.items.length));
const templateOpen=ref(false),templateModel=ref(null),templateBusy=ref(false);
async function showTemplates(row){templateModel.value=row;templateOpen.value=true;}
async function refreshTemplates(){if(templateModel.value)templateModel.value=await api(`admin/phone-models/${templateModel.value.id}/`);await load();}
function closeTemplates(done){if(!templateBusy.value)done();}
const saved=ref(''),preset=ref('');
const dirty=computed(()=>open.value&&!readOnly.value&&JSON.stringify(form)!==saved.value);
const styleTemplates=promptTemplates.filter(t=>t.kind==='style');
const readOnly=computed(()=>!allowed(editing.value?'change':'add'));
async function load(quiet=false){
  const id=++requestId;if(quiet!==true)loading.value=true;error.value='';
  try{const params=new URLSearchParams({page:String(page.value),search:query.value});if(active.value)params.set(props.resource==='orders'?'status':'active',active.value);if(props.resource==='orders'&&progressFilter.value)params.set('progress',progressFilter.value);const data=await api(`admin/${props.resource}/?${params}`);if(id===requestId){rows.value=data.results;total.value=data.count;}}
  catch(e){if(id===requestId)error.value=e.message;}
  finally{if(id===requestId)loading.value=false;}
}
function search(){page.value=1;load();}
watch(page,load);
onMounted(()=>{load();stopOrderPolling=startVisiblePolling({refresh:()=>load(true),interval:15000,enabled:()=>props.resource==='orders'&&!loading.value&&!open.value&&!saving.value});});
onBeforeUnmount(()=>{stopOrderPolling();++requestId;});
async function edit(row=null){
  editing.value=row;formError.value='';Object.keys(form).forEach(key=>delete form[key]);
  for(const field of schema.value.fields){const value=row?.[field.key]??field.default??(field.multiple?[]:'');form[field.key]=field.type==='json'?JSON.stringify(value,null,2):field.type==='number'?Number(value):structuredClone(toRaw(value));}
  form.password='';saved.value=JSON.stringify(form);preset.value='';open.value=true;optionLoading.value=true;
  try{
    for(const field of schema.value.fields.filter(f=>f.source))options[field.key]=await allRecords(field.source);
    if(props.resource==='roles')permissions.value=await api('admin/permissions/');
  }catch(e){formError.value=e.message;}finally{optionLoading.value=false;}
}
async function save(){
  formError.value='';const body={};
  try{
    for(const field of schema.value.fields){
      const value=form[field.key];
      if(field.required&&(value===''||value===null||value===undefined))throw new Error(`请填写${field.label}`);
      if(field.key==='password'&&!value)continue;
      body[field.key]=field.type==='json'?JSON.parse(value):value;
    }
    if(props.resource==='users'&&!editing.value&&!body.password)throw new Error('请设置初始密码（至少 12 位）。');
    saving.value=true;
    await api(`admin/${props.resource}/${editing.value?editing.value.id+'/':''}`,{method:editing.value?'PATCH':'POST',body});
    open.value=false;ElMessage.success('已保存到后台数据库');await load();
  }catch(e){formError.value=e instanceof SyntaxError?'图层布局 JSON 格式不正确，请检查。':e.message;}
  finally{saving.value=false;}
}
async function remove(row){
  try{
    await ElMessageBox.confirm(`确认删除“${row.name||row.username||row.id}”？此操作将删除后台记录。`,'删除记录',{type:'warning',confirmButtonText:'删除',cancelButtonText:'取消'});
    await api(`admin/${props.resource}/${row.id}/`,{method:'DELETE'});ElMessage.success('已删除');
    if(rows.value.length===1&&page.value>1)page.value--;else await load();
  }catch(e){if(e!=='cancel'&&e!=='close')ElMessage.error(e.message||'删除失败');}
}
async function upload(event,field){
  const file=event.target.files?.[0];if(!file)return;uploading.value=true;formError.value='';
  try{const body=new FormData();body.append('file',file);const result=await api('admin/uploads/',{method:'POST',body});form[field.key]=result.path;ElMessage.success('图片已上传');}
  catch(e){formError.value=e.message;}finally{uploading.value=false;event.target.value='';}
}
async function canLeave(){
  if(saving.value||uploading.value||optionLoading.value||templateBusy.value)return false;
  if(dirty.value){try{await ElMessageBox.confirm('有未保存的修改，离开后将丢弃。','离开编辑',{confirmButtonText:'丢弃修改',cancelButtonText:'继续编辑',type:'warning'});}catch{return false;}}
  open.value=false;return true;
}
async function close(done){if(await canLeave())if(typeof done==='function')done();}
async function fillTemplate(){
 const template=styleTemplates.find(t=>t.id===preset.value);if(!template)return;
 if(form.prompt?.trim()){try{await ElMessageBox.confirm('模板将替换当前提示词草稿，保存后生效。','填入英文模板',{confirmButtonText:'填入',cancelButtonText:'取消'});}catch{return;}}
 form.prompt=template.text;
}
function beforeUnload(event){if(dirty.value||templateBusy.value){event.preventDefault();event.returnValue='';}}
onMounted(()=>window.addEventListener('beforeunload',beforeUnload));
onBeforeUnmount(()=>window.removeEventListener('beforeunload',beforeUnload));
onBeforeRouteLeave(canLeave);
defineExpose({canLeave,load});
function format(row,key){const value=row[key];if(props.resource==='orders'&&key==='mode')return displayLabels[value]||value;if(key==='payment_status')return progressPaymentText(row.progress,'zh-CN');if(key==='progress_device')return row.progress?.device?`${row.progress.device.name} · ${row.progress.device.location||'位置未填写'}`:'尚未绑定';if(key==='progress_updated')return progressTime(row.progress,'zh-CN');if(key==='results')return `${value.length} 个效果`;if(key==='permissions')return `${value.length} 项`;if(Array.isArray(value))return value.join('、')||'未分配';if(key.endsWith('_at'))return new Date(value).toLocaleString('zh-CN');return displayLabels[value]||value||'—';}
</script>
<template><section><div class="page-heading"><div><p v-if="!embedded" class="eyebrow">{{schema.app==='auth'?'ACCESS & CONTROL':'STUDIO MANAGEMENT'}}</p><component :is="embedded?'h2':'h1'">{{schema.title}}<span v-if="!embedded" class="greeting-dot">.</span></component><p class="muted">{{schema.subtitle}}</p></div><el-button v-if="!schema.noCreate&&allowed('add')" type="primary" size="large" :icon="Plus" @click="edit()">新增{{props.resource==='users'?'账号':props.resource==='roles'?'角色':'记录'}}</el-button></div><el-alert v-if="schema.access&&!session.user.is_superuser" title="你可以查看授权信息。账号与角色变更仅限超级管理员。" type="info" :closable="false"/><PhoneModelTemplates v-if="resource==='phone-models'" :disabled="templateBusy" @busy="templateBusy=$event" @updated="load"/><div class="panel resource-panel"><div class="table-toolbar"><el-input v-model="query" clearable :prefix-icon="Search" placeholder="搜索名称、标识或关键词" aria-label="搜索记录" @keyup.enter="search" @clear="search"/><el-select v-if="schema.fields.some(f=>f.key==='active')" v-model="active" aria-label="状态筛选" placeholder="全部状态" clearable @change="search"><el-option label="启用" value="true"/><el-option label="停用" value="false"/></el-select><el-select v-if="props.resource==='orders'" v-model="active" aria-label="订单状态筛选" placeholder="全部状态" clearable @change="search"><el-option v-for="value in ['paid','printing','ready','completed','cancelled']" :key="value" :value="value" :label="displayLabels[value]"/></el-select><el-select v-if="resource==='orders'" v-model="progressFilter" aria-label="打印进度筛选" placeholder="全部打印进度" clearable @change="search"><el-option label="待处理" value="pending"/><el-option label="打印 / 出货中" value="printing"/><el-option label="已出货" value="dispensed"/><el-option label="异常 / 待核实" value="attention"/><el-option label="取消 / 退款 / 已结束" value="closed"/></el-select><el-button @click="search">搜索</el-button><el-button :icon="Refresh" aria-label="刷新列表" @click="load"/><span class="record-count">共 {{total}} 条记录</span></div><el-alert v-if="error" :title="error" type="error" :closable="false"/><el-table v-loading="loading" :data="rows" :empty-text="schema.empty||'暂无记录，点击右上角新增开始管理。'"><el-table-column v-for="[key,label] in schema.columns" :key="key" :label="label" :min-width="key==='progress'?190:key==='progress_device'?220:key==='progress_updated'?180:key==='summary'?250:key==='customer_email'?240:key==='created_at'?175:key==='image_path'?88:130"><template #default="{row}"><span v-if="key==='progress'"><el-tag :type="progressText(row.progress,'zh-CN').tone">{{progressText(row.progress,'zh-CN').label}}</el-tag><small v-if="row.progress?.stale" class="muted">设备反馈暂未更新</small></span><span v-else-if="key==='template_sources'" class="model-template-cell"><img v-if="row.template_sources?.find(s=>s.image)" :src="row.template_sources.find(s=>s.image).image" :alt="row.name+' 底图'" class="table-image" loading="lazy"/><span>{{row.template_sources?.some(s=>s.image)?'底图已导入':row.template_sources?.some(s=>s.has_source)?'待导入底图':'暂无供应商底图'}}</span></span><img v-else-if="['image_path','original_path'].includes(key)" v-bind="imageAttributes(row[key],{sizes:'64px'})" alt="素材缩略图" class="table-image" loading="lazy"/><el-tag v-else-if="typeof row[key]==='boolean'" :type="row[key]?'success':'info'" effect="light" round>{{row[key]?'是':'否'}}</el-tag><OrderCustomer v-else-if="resource==='orders'&&key==='customer_email'" :customer-id="row.customer_id" :email="row.customer_email"/><span v-else :class="{'cell-name':['name','username'].includes(key)}">{{format(row,key)}}</span></template></el-table-column><el-table-column v-if="!schema.noEdit||!schema.noDelete" label="操作" :width="resource==='phone-models'?260:150" fixed="right"><template #default="{row}"><el-button v-if="resource==='phone-models'" link type="primary" @click="showTemplates(row)">底图</el-button><el-button v-if="resource==='phone-models'" link type="primary" @click="$router.push({path:'/phone-colors',query:{phone_model:row.id}})">颜色</el-button><el-button v-if="!schema.noEdit" link type="primary" @click="edit(row)">{{props.resource==='orders'?'订单详情':allowed('change')?'编辑':'查看'}}</el-button><el-button v-if="!schema.noDelete&&allowed('delete')" link type="danger" @click="remove(row)">删除</el-button></template></el-table-column></el-table><div class="table-footer"><span>{{props.resource==='orders'?'订单由用户端同步 · 请核对付款模式与退款状态':props.resource==='phone-models'?'设备商品可同步至机型库 · 未扫码可设计全部已发布机型；扫码后按设备库存和模板筛选':['plans','ai-styles','ai-examples'].includes(props.resource)?'保存后刷新用户端生效':'配置保存在服务端 · 此模块尚未同步用户端'}}</span><el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" hide-on-single-page/></div></div><el-drawer v-model="open" :title="(editing?(readOnly?'查看':'编辑'):'新增')+' · '+schema.title" size="min(760px, 100vw)" :before-close="close" :close-on-click-modal="false" :close-on-press-escape="!saving&&!uploading" :show-close="!saving&&!uploading" destroy-on-close><el-alert v-if="formError" :title="formError" type="error" :closable="false" class="form-alert"/><OrderDetails v-if="props.resource==='orders'&&editing" :id="editing.id" @updated="load"/><el-form :model="form" label-position="top" :disabled="readOnly||saving||optionLoading" @submit.prevent="save"><el-form-item v-for="field in schema.fields" :key="field.key" :label="field.label" :required="field.required"><AIResultsField v-if="field.type==='effects'" v-model="form[field.key]" :styles="options[field.key]||[]" :disabled="readOnly||saving||optionLoading" @busy="uploading=$event" @error="formError=$event"/><el-switch v-else-if="field.type==='switch'" v-model="form[field.key]"/><el-input-number v-else-if="field.type==='number'" v-model="form[field.key]" :min="0" :precision="field.precision||0" :max="field.key==='price'?999999.99:1000000" controls-position="right"/><el-select v-else-if="field.type==='select'" v-model="form[field.key]" :multiple="field.multiple" filterable :placeholder="'请选择'+field.label"><el-option v-for="[value,label] in field.source?(options[field.key]||[]).map(row=>[row.id,row.name]):field.options" :key="value" :label="label" :value="value"/></el-select><el-color-picker v-else-if="field.type==='color'" v-model="form[field.key]"/><div v-else-if="field.type==='permissions'" class="permission-grid"><div class="permission-note">账号和角色的写入权限仍需超级管理员身份。</div><div v-for="group in permissionGroups" :key="group.model" class="permission-row"><strong>{{group.name}}</strong><el-checkbox-group v-model="form[field.key]"><el-checkbox v-for="permission in group.items" :key="permission.id" :value="permission.id">{{actionLabels[permission.codename.split('_')[0]]||permission.name}}</el-checkbox></el-checkbox-group></div></div><div v-else-if="field.type==='image'" class="image-field"><div class="image-entry"><img v-if="form[field.key]" v-bind="imageAttributes(form[field.key],{sizes:'160px',loading:'eager'})" alt="图片预览"/><span v-else>无图片</span></div><div><el-input v-model="form[field.key]" placeholder="/assets/... 或上传图片"/><label v-if="!readOnly" class="upload-button"><el-icon><Upload/></el-icon>{{uploading?'正在上传…':'上传图片'}}<input type="file" accept="image/png,image/jpeg,image/webp" :disabled="uploading||saving" @change="upload($event,field)"/></label><small>JPG / PNG / WebP，最多 10 MB；保留原图，自动生成轻量预览</small></div></div><div v-else-if="field.key==='prompt'&&resource==='ai-styles'" class="style-prompt-editor"><div v-if="!readOnly" class="style-template-row"><el-select v-model="preset" placeholder="选择英文提示词模板" aria-label="风格提示词模板"><el-option v-for="item in styleTemplates" :key="item.id" :value="item.id" :label="item.name"/></el-select><el-button :disabled="!preset" @click="fillTemplate">填入模板</el-button></div><el-input v-model="form[field.key]" type="textarea" :rows="10" maxlength="4000" show-word-limit placeholder="Describe the style, subject preservation and output requirements in English."/></div><el-input v-else-if="['textarea','json'].includes(field.type)" v-model="form[field.key]" type="textarea" :rows="field.rows||(field.type==='json'?9:3)" :maxlength="field.maxlength" :show-word-limit="Boolean(field.maxlength)" :class="{'json-input':field.type==='json'}"/><el-input v-else v-model="form[field.key]" :type="field.type==='password'?'password':'text'" :show-password="field.type==='password'" :disabled="Boolean(editing&&field.immutable)" :placeholder="field.placeholder" :autocomplete="field.type==='password'?'new-password':'off'"/><small v-if="field.help" class="muted">{{field.help}}</small></el-form-item></el-form><template #footer><div class="drawer-footer"><span>{{editing?'编辑后台记录':'新增后台记录'}}</span><el-button :disabled="saving||uploading||optionLoading" @click="close">{{readOnly?'关闭':'取消'}}</el-button><el-button v-if="!readOnly" type="primary" :loading="saving" :disabled="uploading||optionLoading" @click="save">保存</el-button></div></template></el-drawer><el-drawer v-model="templateOpen" :title="(templateModel?.name||'机型')+' · 底图与遮罩'" size="min(760px, 100vw)" :before-close="closeTemplates" :close-on-click-modal="!templateBusy" :close-on-press-escape="!templateBusy" destroy-on-close><PhoneModelTemplates v-if="templateModel" :model="templateModel" :disabled="templateBusy" @busy="templateBusy=$event" @updated="refreshTemplates"/></el-drawer></section></template>

<style scoped>
.model-template-cell{display:flex;align-items:center;gap:10px;font-size:12px}.model-template-cell .table-image{width:32px;height:64px;object-fit:contain}

.style-prompt-editor{width:100%}.style-template-row{display:flex;gap:10px;margin-bottom:12px}.style-template-row .el-select{flex:1;min-width:0}.style-prompt-editor :deep(textarea){line-height:1.8}
</style>
