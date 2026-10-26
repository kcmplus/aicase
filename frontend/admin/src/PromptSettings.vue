<script setup>
import {computed,onMounted,onBeforeUnmount,ref} from 'vue';
import {onBeforeRouteLeave,useRoute} from 'vue-router';
import AIExampleWorkbench from './AIExampleWorkbench.vue';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api,allRecords,can,session} from './api.js';
import {composePrompt,promptTemplates} from './prompt-templates.js';

const definitions={
  style:{resource:'ai-styles',field:'prompt',model:'aistyle',label:'风格提示词'},
  model:{resource:'phone-models',field:'adaptation_prompt',model:'phonemodel',label:'机型适配提示词'},
};
const visible=key=>can(`management_api.view_${definitions[key].model}`);
const route=useRoute();
const tabs=[...(can('management_api.view_aiexample')?['examples']:[]),...Object.keys(definitions).filter(visible)];
const kind=ref(tabs.includes(route.query.tab)?route.query.tab:tabs[0]);
const exampleWorkbench=ref(null);
async function beforeTabChange(){if(!await confirmDiscard())return false;if(exampleWorkbench.value&&!await exampleWorkbench.value.canLeave())return false;open.value=false;return true;}
function refreshAll(){load();exampleWorkbench.value?.load();}
const styles=ref([]),models=ref([]),loading=ref(false),error=ref(''),query=ref('');
const open=ref(false),record=ref(null),editorKind=ref('style'),draft=ref(''),saving=ref(false),reading=ref(false),formError=ref(''),preset=ref(''),partner=ref(null);
const definition=computed(()=>definitions[editorKind.value]);
const editable=computed(()=>can(`management_api.change_${definition.value.model}`));
const dirty=computed(()=>Boolean(record.value)&&draft.value!==(record.value[definition.value.field]||''));
const rows=computed(()=>{
  const term=query.value.trim().toLowerCase();
  return (kind.value==='style'?styles.value:models.value).filter(row=>!term||`${row.name} ${row.code} ${row[definitions[kind.value].field]||''}`.toLowerCase().includes(term));
});
const templates=computed(()=>promptTemplates.filter(t=>t.kind===editorKind.value&&(t.id!=='iphone15pro-study'||record.value?.name==='iPhone 15 Pro')));
const partners=computed(()=>editorKind.value==='style'?models.value:styles.value);
const combined=computed(()=>{
  if(!record.value)return '';
  const current={...record.value,[definition.value.field]:draft.value};
  const other=partners.value.find(row=>row.id===partner.value);
  return editorKind.value==='style'?composePrompt(current,other):composePrompt(other,current);
});
const formatDate=value=>value?new Date(value).toLocaleString('zh-CN'):'—';
const configured=(row,key)=>Boolean(row[definitions[key].field]?.trim());
const excerpt=(row,key)=>(row[definitions[key].field]||'').replace(/\s+/g,' ').slice(0,85);

async function load(){
  loading.value=true;error.value='';
  const keys=Object.keys(definitions).filter(visible);
  const results=await Promise.allSettled(keys.map(key=>allRecords(definitions[key].resource)));
  for(let i=0;i<keys.length;i++){
    const target=keys[i]==='style'?styles:models;
    if(results[i].status==='fulfilled')target.value=results[i].value;
    else{target.value=[];error.value+=`${definitions[keys[i]].label}加载失败：${results[i].reason.message} `;}
  }
  loading.value=false;
}
async function edit(row){
  editorKind.value=kind.value;record.value=null;draft.value='';formError.value='';preset.value='';partner.value=null;open.value=true;reading.value=true;
  try{
    const data=await api(`admin/${definition.value.resource}/${row.id}/`);
    record.value=data;draft.value=data[definition.value.field]||'';
  }catch(e){formError.value=e.message;}finally{reading.value=false;}
}
async function save(){
  if(!record.value||!editable.value||saving.value)return;
  saving.value=true;formError.value='';
  try{
    const data=await api(`admin/${definition.value.resource}/${record.value.id}/`,{method:'PATCH',body:{[definition.value.field]:draft.value}});
    record.value=data;draft.value=data[definition.value.field]||'';
    ElMessage.success('提示词已保存到后台');await load();
  }catch(e){formError.value=e.message;}finally{saving.value=false;}
}
async function confirmDiscard(){
  if(saving.value||reading.value)return false;
  if(!dirty.value)return true;
  try{await ElMessageBox.confirm('提示词有未保存的修改，关闭后将丢弃这些修改。','关闭编辑',{confirmButtonText:'丢弃修改',cancelButtonText:'继续编辑',type:'warning'});return true;}catch{return false;}
}
async function close(done){if(await confirmDiscard()){record.value=null;draft.value='';typeof done==='function'?done():open.value=false;}}
async function fillTemplate(){
  const template=templates.value.find(item=>item.id===preset.value);
  if(!template||!editable.value)return;
  if(draft.value.trim()){
    try{await ElMessageBox.confirm('模板将替换编辑框里的内容。点击保存后才会更新后台。','填入模板',{confirmButtonText:'填入',cancelButtonText:'取消'});}catch{return;}
  }
  draft.value=template.text;
}
async function copy(){try{await navigator.clipboard.writeText(combined.value);ElMessage.success('已复制组合提示词');}catch{ElMessage.warning('复制失败，请在预览框内选中文本后复制。');}}
function beforeUnload(event){if(dirty.value){event.preventDefault();event.returnValue='';}}
onMounted(()=>{load();window.addEventListener('beforeunload',beforeUnload);});
onBeforeUnmount(()=>window.removeEventListener('beforeunload',beforeUnload));
onBeforeRouteLeave(()=>confirmDiscard());
</script>

<template>
  <section class="prompt-page">
    <div class="page-heading"><div><p class="eyebrow">AI CONFIGURATION</p><h1>AI 案例与提示词<span class="greeting-dot">.</span></h1><p class="muted">对照原图与效果图，管理案例提示词、通用风格及机型适配规则。</p></div><div><router-link v-if="session.user?.is_superuser" to="/ai-service" style="font-size:13px;color:#196967;margin-right:15px">生图服务配置</router-link><el-button :loading="loading" @click="refreshAll">刷新</el-button></div></div>
    <el-alert title="案例图片与提示词在同一处管理。修改提示词不会自动重新生成效果图；真实生图服务尚未接入。" type="info" :closable="false" show-icon/>
    <el-tabs v-model="kind" class="workspace-tabs" :before-leave="beforeTabChange"><el-tab-pane v-if="can('management_api.view_aiexample')" label="案例与提示词" name="examples"/><el-tab-pane v-if="visible('style')" label="通用风格提示词" name="style"/><el-tab-pane v-if="visible('model')" label="机型适配提示词" name="model"/></el-tabs>
    <AIExampleWorkbench v-if="kind==='examples'" ref="exampleWorkbench"/>
    <div v-else class="panel prompt-panel">
      <div class="prompt-toolbar"><el-input v-model="query" aria-label="搜索提示词" placeholder="搜索名称、标识或提示词内容" clearable/><span class="muted">{{rows.length}} 条配置</span></div>
      <p class="muted prompt-help">{{kind==='style'?'每个 AI 风格保存一份提示词，描述画风、主体保留要求和输出效果。新增风格请到「AI 风格」管理。':'每个机型单独保存构图要求，例如主体位置、镜头避让与边缘裁切。文字规则不能替代实测打印模板。'}}</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false"/>
      <el-table v-loading="loading" :data="rows" empty-text="暂无匹配配置">
        <el-table-column :label="kind==='style'?'风格':'机型'" min-width="155"><template #default="{row}"><strong class="cell-name">{{row.name}}</strong><div class="prompt-code">{{row.code}}{{row.active?'':' · 已停用'}}</div></template></el-table-column>
        <el-table-column label="提示词内容" min-width="260"><template #default="{row}"><el-tag :type="configured(row,kind)?'success':'info'" size="small">{{configured(row,kind)?'已设置':'未设置'}}</el-tag><p class="prompt-excerpt">{{excerpt(row,kind)||'尚未填写，打开后可编辑或填入模板。'}}</p></template></el-table-column>
        <el-table-column label="最后更新" min-width="170"><template #default="{row}">{{formatDate(row.updated_at)}}</template></el-table-column>
        <el-table-column label="操作" width="120" fixed="right"><template #default="{row}"><el-button link type="primary" :aria-label="'查看提示词 '+row.name" @click="edit(row)">{{can(`management_api.change_${definitions[kind].model}`)?'查看 / 编辑':'查看'}}</el-button></template></el-table-column>
      </el-table>
    </div>

    <el-drawer v-model="open" :title="definition.label+(record?' · '+record.name:'')" size="760px" :before-close="close" :close-on-click-modal="false" :close-on-press-escape="!saving&&!reading" :show-close="!saving&&!reading" destroy-on-close>
      <div v-loading="reading">
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" class="form-alert"/>
        <template v-if="record">
          <div class="prompt-meta"><el-tag :type="editable?'success':'info'">{{editable?'可编辑':'仅查看'}}</el-tag><span>更新于 {{formatDate(record.updated_at)}}</span><el-tag v-if="dirty" type="warning">未保存</el-tag></div>
          <el-alert v-if="editorKind==='model'" title="请以实际壳型的打印模板为准。填写适配提示词不会将机型标记为打印已校准。" type="info" :closable="false" class="form-alert"/>
          <div v-if="editable" class="template-row"><el-select v-model="preset" aria-label="选择提示词模板" placeholder="选择一个模板作为起点" :disabled="saving"><el-option v-for="item in templates" :key="item.id" :value="item.id" :label="item.name"/></el-select><el-button :disabled="!preset||saving" @click="fillTemplate">填入模板</el-button></div>
          <label class="prompt-label" for="prompt-draft">{{definition.label}}</label>
          <el-input id="prompt-draft" v-model="draft" type="textarea" :rows="13" :readonly="!editable" :disabled="saving" maxlength="4000" show-word-limit :placeholder="editorKind==='style'?'描述画面风格、主体保留要求和输出限制…':'描述此机型的画布比例、镜头避让和主体安全区域…'"/>
          <p class="muted draft-note">{{editable?'修改后点击保存；留空保存可清除这份提示词。':'你可以查看和复制提示词，修改需要相应管理权限。'}}</p>
          <div class="prompt-preview">
            <h2>组合预览</h2><p class="muted">将风格与机型要求放在一起，方便复制测试。此处不会发起生图请求。{{dirty?'当前预览包含未保存的修改。':''}}</p>
            <el-select v-if="partners.length" v-model="partner" clearable filterable :aria-label="editorKind==='style'?'选择预览机型':'选择预览风格'" :placeholder="editorKind==='style'?'选择机型，一起预览适配要求':'选择风格，一起预览生成要求'"><el-option v-for="item in partners" :key="item.id" :value="item.id" :label="item.name+(item.active?'':'（已停用）')"/></el-select>
            <p v-else class="muted">暂无可选择的{{editorKind==='style'?'机型':'风格'}}，或当前账号没有查看权限。</p>
            <p v-if="partner&&!configured(partners.find(item=>item.id===partner)||{},editorKind==='style'?'model':'style')" class="prompt-warning">所选{{editorKind==='style'?'机型':'风格'}}尚未设置提示词，组合内容暂不包含对应要求。</p>
            <el-input :model-value="combined" aria-label="组合提示词预览" type="textarea" :rows="8" readonly/>
            <el-button @click="copy" :disabled="!combined">复制组合提示词</el-button>
          </div>
        </template>
      </div>
      <template #footer><div class="drawer-footer"><span>{{dirty?'有未保存的修改':'配置保存在服务端'}}</span><el-button :disabled="saving||reading" @click="close">关闭</el-button><el-button v-if="record&&editable" type="primary" :loading="saving" :disabled="!dirty||reading" @click="save">保存提示词</el-button></div></template>
    </el-drawer>
  </section>
</template>

<style scoped>
.workspace-tabs{margin-top:25px}.prompt-panel{margin-top:22px;padding:12px 24px 24px}.prompt-toolbar{display:flex;align-items:center;gap:16px;margin:12px 0}.prompt-toolbar .el-input{max-width:360px}.prompt-toolbar>span{white-space:nowrap}.prompt-help{font-size:12px}.prompt-excerpt{font-size:12px;line-height:1.7;margin:8px 0 0;color:#73847c;white-space:normal;overflow-wrap:anywhere}.prompt-code{font-size:10px;color:#96a39d;margin-top:6px}.prompt-meta{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:11px;color:#7b8887;margin-bottom:20px}.template-row{display:flex;gap:10px;margin:20px 0}.template-row .el-select{flex:1;min-width:0}.prompt-label{display:block;font-size:13px;color:#587165;margin:0 0 10px}.draft-note{font-size:11px;margin:10px 0 22px}.prompt-preview{background:#f6f9f7;border:1px solid #e0e7e3;border-radius:9px;padding:20px;margin-top:25px}.prompt-preview h2{font-size:16px;margin-bottom:10px}.prompt-preview>.muted{font-size:12px}.prompt-preview .el-select{margin-bottom:14px}.prompt-preview .el-button{margin-top:12px}.prompt-warning{font-size:12px;line-height:1.6;color:#9b712e}.prompt-page :deep(textarea){line-height:1.8;font-size:13px;overflow-wrap:anywhere}@media(max-width:700px){.prompt-panel{padding:8px 12px 18px}.prompt-preview{padding:14px}.prompt-toolbar{flex-wrap:wrap}}
</style>
