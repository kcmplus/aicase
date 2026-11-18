<script setup>
import {computed,onMounted,reactive,ref} from 'vue';
import {useRoute,onBeforeRouteLeave} from 'vue-router';
import {api,can} from './api.js';
const route=useRoute();
const models=ref([]),modelId=ref(Number(route.query.phone_model)||null),rows=ref([]),loading=ref(false),busy=ref(false),error=ref(''),notice=ref('');
const open=ref(false),editing=ref(null),form=reactive({rgb:{r:255,g:255,b:255}}),files=reactive({overlay:null,mask:null}),templateId=ref(''),review=ref('');
const initOpen=ref(false),initReport=ref(null),initError=ref('');
const initLabels={matched:'精确匹配',unmatched:'未匹配，跳过',ambiguous:'多匹配，跳过',needs_review:'待确认，跳过',would_create:'待新增停用草稿',created:'已新增停用草稿',existing:'已存在，保持原样'};
onBeforeRouteLeave(()=>!busy.value);
const allowed=action=>can(`management_api.${action}_phonecolor`);
const model=computed(()=>models.value.find(m=>m.id===modelId.value));
const colorHex=computed({get:()=>[form.rgb?.r,form.rgb?.g,form.rgb?.b].every(Number.isInteger)?'#'+['r','g','b'].map(k=>form.rgb[k].toString(16).padStart(2,'0')).join(''):'#ffffff',set:value=>{if(/^#[0-9a-f]{6}$/i.test(value||''))form.rgb={r:parseInt(value.slice(1,3),16),g:parseInt(value.slice(3,5),16),b:parseInt(value.slice(5,7),16)};}});
const swatch=rgb=>`rgb(${rgb.r},${rgb.g},${rgb.b})`;
async function load(){
 loading.value=true;error.value='';rows.value=[];
 try{
  if(!modelId.value)return;
  const all=[];let page=1;
  while(true){const data=await api(`admin/phone-colors/?phone_model=${modelId.value}&page=${page}`);all.push(...data.results);if(!data.next)break;page++;}
  rows.value=all;
 }catch(e){error.value=e.message;}finally{loading.value=false;}
}
onMounted(async()=>{loading.value=true;try{models.value=await api('admin/phone-colors/options_catalog/');if(!models.value.some(m=>m.id===modelId.value))modelId.value=null;await load();}catch(e){error.value=e.message;}finally{loading.value=false;}});
function edit(row=null){
 editing.value=row;Object.assign(form,row?{code:row.code,name:row.name,rgb:{...row.rgb},region_note:row.region_note,source:row.source,sort_order:row.sort_order,is_default:row.is_default,active:row.active}:{code:'',name:'',rgb:{r:255,g:255,b:255},region_note:'',source:'',sort_order:0,is_default:false,active:false});
 files.overlay=files.mask=null;review.value='';templateId.value=row?.resource?.template_id||model.value?.templates?.[0]?.id||'';error.value='';notice.value='';open.value=true;
}
async function action(work,message){
 if(busy.value)return;
 busy.value=true;error.value='';notice.value='';
 try{await work();notice.value=message;await load();}catch(e){error.value=e.message;}finally{busy.value=false;}
}
async function save(){
 await action(async()=>{const body={...form,rgb:{...form.rgb}};if(!editing.value)body.phone_model=modelId.value;
  const row=await api(`admin/phone-colors/${editing.value?editing.value.id+'/':''}`,{method:editing.value?'PATCH':'POST',body});editing.value=row;Object.assign(form,{active:row.active});
 },'颜色配置已保存。');
}
async function upload(){
 if(!editing.value||!files.overlay||!files.mask)return;
 await action(async()=>{const body=new FormData();body.append('overlay',files.overlay);body.append('mask',files.mask);body.append('template_id',templateId.value);
  editing.value=await api(`admin/phone-colors/${editing.value.id}/resources/`,{method:'POST',body});form.active=false;review.value='';files.overlay=files.mask=null;
 },'新版本已保存并停用颜色，请核验当前资源后再启用。');
}
async function verify(){
 await action(async()=>{editing.value=await api(`admin/phone-colors/${editing.value.id}/verify-resources/`,{method:'POST',body:{version:editing.value.resource.version,review_note:review.value}});},'当前资源已人工核验；启用仍需单独保存。');
}
async function previewInitialization(){
 if(busy.value)return;
 initOpen.value=true;initReport.value=null;initError.value='';busy.value=true;
 try{initReport.value=await api('admin/phone-colors/initialize-reference/');}
 catch(e){initError.value=e.message;}finally{busy.value=false;}
}
async function initializeColors(){
 if(busy.value||!initReport.value||initReport.value.mode!=='preview')return;
 busy.value=true;initError.value='';
 try{
  initReport.value=await api('admin/phone-colors/initialize-reference/',{method:'POST',body:{reference_sha256:initReport.value.reference_sha256,confirm:true}});
  await load();
 }catch(e){initError.value=e.message+' 可重新预览核实；已有配置不会被覆盖。';}finally{busy.value=false;}
}
function closeInitialization(done){if(!busy.value)done();}
function close(done){if(!busy.value){if(typeof done==='function')done();else open.value=false;}}
</script>
<template>
 <section>
  <div class="page-heading"><div><p class="eyebrow">PREVIEW CONFIGURATION</p><h1>机型颜色</h1><p class="muted">RGB 是近似显示色。颜色仅用于机身预览，不改变壳体 SKU、库存、打印模板或校准状态。</p></div><el-button v-if="allowed('add')" type="primary" :disabled="!modelId||busy" @click="edit()">新增颜色草稿</el-button></div>
  <div class="panel initialization-entry"><div><strong>参考颜色初始化</strong><p>仅按品牌与机型名称精确匹配；待确认和多匹配项跳过。只新增停用草稿，不创建机型、不覆盖人工配置、不启用或生成预览资源。</p></div><el-button :disabled="busy||loading" @click="previewInitialization">预览初始化</el-button></div>
  <div class="panel color-panel">
   <el-select v-model="modelId" filterable placeholder="选择现有机型" aria-label="选择颜色所属机型" :disabled="busy||loading" @change="load"><el-option v-for="item in models" :key="item.id" :value="item.id" :label="item.brand+' · '+item.name"/></el-select>
   <el-button :disabled="busy||loading" @click="load">刷新</el-button>
   <el-alert v-if="error&&!open" :title="error" type="error" :closable="false"/>
   <el-empty v-if="!modelId" description="请选择机型。颜色可选，未配置不影响原有有效预览。"/>
   <el-table v-else v-loading="loading" :data="rows" empty-text="尚无颜色，颜色可选；用户端沿用原有效预览。">
    <el-table-column label="颜色 / RGB" min-width="200"><template #default="{row}"><span class="swatch" :style="{background:swatch(row.rgb)}"></span>{{row.name||row.code}} · {{row.rgb.r}}, {{row.rgb.g}}, {{row.rgb.b}}</template></el-table-column>
    <el-table-column prop="code" label="稳定编码"/><el-table-column prop="sort_order" label="排序"/>
    <el-table-column label="状态"><template #default="{row}">{{row.active?'启用':'停用'}}{{row.is_default?' · 默认':''}}</template></el-table-column>
    <el-table-column label="预览资源" min-width="200"><template #default="{row}">{{row.resource?`v${row.resource.version} · ${row.resource.verified_at?'已人工核验':'待人工核验'}`:'缺资源，可保存草稿'}}</template></el-table-column>
    <el-table-column label="操作"><template #default="{row}"><el-button link type="primary" @click="edit(row)">{{allowed('change')?'管理':'查看'}}</el-button></template></el-table-column>
   </el-table>
  </div>
  <el-drawer v-model="initOpen" title="参考颜色初始化 · 预览与结果" size="min(1000px,100vw)" :before-close="closeInitialization" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy" destroy-on-close>
   <el-alert v-if="initError" :title="initError" type="error" :closable="false"/>
   <div v-loading="busy" class="initialization-report">
    <p>唯一资料：phone-color-reference.json。RGB 为近似显示色，官方资料核实不代表预览资源核验、库存可售或打印校准。当前机型筛选不限制此操作；以下列出全库实际匹配情况。展开内容为参考值；已有项保留实际配置，不用参考值覆盖。</p>
    <template v-if="initReport">
     <el-alert :title="initReport.mode==='executed'?'本次执行已保存；新增项全部停用且无资源。':'以下为只读预览，尚未写入。执行时重新核对数据库，结果可能随配置变化。'" :type="initReport.mode==='executed'?'success':'info'" :closable="false"/>
     <p class="reference-digest">资料 v{{initReport.reference_version}} · {{initReport.researched_at}} · SHA-256 {{initReport.reference_sha256}}</p>
     <dl class="initialization-counts"><template v-for="[key,label] in [['total_models','参考机型'],['verified_models','已核实机型'],['reference_colors','参考颜色'],['matched_models','匹配机型'],['unmatched_models','未匹配'],['ambiguous_models','多匹配'],['needs_review_models','待确认'],['new_colors',initReport.mode==='executed'?'本次新增':'预计新增'],['existing_colors','已有保留']]" :key="key"><div><dt>{{label}}</dt><dd>{{initReport.summary[key]}}</dd></div></template></dl>
     <el-table :data="initReport.items" row-key="model_name">
      <el-table-column type="expand"><template #default="{row}"><p v-if="!row.colors.length">{{initLabels[row.result]}}；未导入颜色，未猜测其他机型或共用模板。</p><el-table v-else :data="row.colors"><el-table-column prop="code" label="编码" min-width="150"/><el-table-column prop="name" label="辅助名称" min-width="170"/><el-table-column label="近似 RGB" min-width="150"><template #default="{row:color}"><span class="swatch" :style="{background:swatch(color.rgb)}"></span>{{color.rgb.r}}, {{color.rgb.g}}, {{color.rgb.b}}</template></el-table-column><el-table-column label="处理" min-width="170"><template #default="{row:color}">{{initLabels[color.result]}}</template></el-table-column><el-table-column prop="region_note" label="区域 / 网络 / 特别版" min-width="250"/><el-table-column prop="source" label="来源（不抓取）" min-width="250"/></el-table></template></el-table-column>
      <el-table-column prop="brand" label="品牌" width="100"/><el-table-column prop="model_name" label="参考机型" min-width="190"/><el-table-column label="处理结果" min-width="160"><template #default="{row}">{{initLabels[row.result]}}</template></el-table-column><el-table-column label="现有机型 ID" min-width="130"><template #default="{row}">{{row.candidate_ids.join(', ')||'—'}}</template></el-table-column><el-table-column prop="notes" label="核实 / 待确认说明" min-width="250"/>
     </el-table>
    </template>
   </div>
   <template #footer><el-button :disabled="busy" @click="previewInitialization">重新预览</el-button><el-button v-if="allowed('add')" type="primary" :loading="busy" :disabled="busy||initReport?.mode!=='preview'" @click="initializeColors">确认仅新增停用草稿</el-button></template>
  </el-drawer>
  <el-drawer v-model="open" :title="(editing?'管理':'新增')+' · '+(model?.name||'机型')+'颜色'" size="min(760px,100vw)" :before-close="close" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy" destroy-on-close>
   <el-alert v-if="error" :title="error" type="error" :closable="false"/><el-alert v-if="notice" :title="notice" type="success" :closable="false"/>
   <el-form label-position="top" :disabled="busy||!(editing?allowed('change'):allowed('add'))" @submit.prevent="save">
    <el-form-item label="稳定颜色编码（创建后不可修改）" required><el-input v-model="form.code" :disabled="Boolean(editing)" maxlength="80" placeholder="例如 natural-titanium"/></el-form-item>
    <el-form-item label="辅助名称"><el-input v-model="form.name" maxlength="120"/></el-form-item>
    <el-form-item label="近似显示色 RGB" required><div class="rgb-fields"><el-color-picker v-model="colorHex" color-format="hex" aria-label="颜色取色器"/><label v-for="channel in ['r','g','b']" :key="channel">{{channel.toUpperCase()}} <el-input-number v-model="form.rgb[channel]" :min="0" :max="255" :precision="0" :aria-label="channel.toUpperCase()+'通道'"/></label><span>{{colorHex}}</span></div></el-form-item>
    <el-form-item label="区域 / 网络 / 特别版备注"><el-input v-model="form.region_note" maxlength="300"/></el-form-item>
    <el-form-item label="资料来源（不自动抓取）"><el-input v-model="form.source" maxlength="500"/></el-form-item>
    <el-form-item label="排序"><el-input-number v-model="form.sort_order" :min="0" :precision="0"/></el-form-item>
    <el-form-item label="默认项（每机型最多一项）"><el-switch v-model="form.is_default"/></el-form-item>
    <el-form-item label="启用（须资源完整且已人工核验）"><el-switch v-model="form.active" :disabled="!editing?.resource?.verified_at"/></el-form-item>
    <el-button v-if="editing?allowed('change'):allowed('add')" type="primary" :loading="busy" native-type="submit">保存颜色配置</el-button>
   </el-form>
   <section v-if="editing" class="resource-panel">
    <h2>预览资源</h2><p>仅上传有权使用的 PNG。两张图须与所绑定模板尺寸一致，均含透明与不透明区域，每张最多 10 MB / 800 万像素。不得上传客户照片。资源替换后自动停用并等待重新核验。</p>
    <template v-if="editing.resource"><p>v{{editing.resource.version}} · {{editing.resource.width}} × {{editing.resource.height}} px · {{editing.resource.template_id}}</p><div class="previews"><figure v-for="role in ['overlay','mask']" :key="role"><a :href="editing.resource[role]" target="_blank" rel="noopener"><img :src="editing.resource[role]" :alt="role==='overlay'?'机身覆盖图':'透明遮罩'"/></a><figcaption>{{role==='overlay'?'机身覆盖图':'透明遮罩'}}</figcaption></figure></div><p>{{editing.resource.verified_at?'已核验：'+editing.resource.verified_by+' · '+editing.resource.verified_at:'尚未人工核验'}} {{editing.resource.review_note}}</p></template>
    <el-empty v-else description="缺资源，可保留停用草稿。"/>
    <fieldset v-if="allowed('change')" :disabled="busy"><legend>上传新资源版本</legend><el-select v-model="templateId" placeholder="选择所绑定的模板版本" aria-label="资源模板版本"><el-option v-for="t in model?.templates||[]" :key="t.id" :value="t.id" :label="`${t.id} · ${t.width} × ${t.height}`"/></el-select><p v-if="!model?.templates?.length">当前机型没有可绑定的模板，先配置底图与遮罩。</p><label>机身覆盖图 <input type="file" accept="image/png" @change="files.overlay=$event.target.files[0]||null"/></label><label>透明遮罩 <input type="file" accept="image/png" @change="files.mask=$event.target.files[0]||null"/></label><el-button :loading="busy" :disabled="busy||!files.overlay||!files.mask||!templateId" @click="upload">上传新版本并停用</el-button></fieldset>
    <fieldset v-if="allowed('verify')&&allowed('change')&&editing.resource" :disabled="busy"><legend>人工核验当前版本</legend><p>检查链接中的实际资源、透明范围、尺寸和使用权。此操作不代表库存可售或真机打印已校准。</p><el-input v-model="review" type="textarea" maxlength="500" placeholder="记录资源来源、检查内容与结果"/><el-button :loading="busy" :disabled="busy||!review.trim()" @click="verify">核验 v{{editing.resource.version}}</el-button></fieldset>
   </section>
  </el-drawer>
 </section>
</template>
<style scoped>
.color-panel{padding:20px}.color-panel>.el-select{width:330px;max-width:75%;margin-right:12px}.swatch{display:inline-block;width:20px;height:20px;border:1px solid #aaa;border-radius:50%;vertical-align:middle;margin-right:8px}.rgb-fields{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.rgb-fields .el-input-number{width:100px}.resource-panel{margin-top:24px;padding:0}.resource-panel p{font-size:13px;line-height:1.8;color:#65716b}.previews{display:flex;gap:20px}.previews figure{margin:0}.previews img{width:130px;max-height:260px;object-fit:contain;background:repeating-conic-gradient(#ddd 0% 25%,#fff 0% 50%) 0/16px 16px}.previews figcaption{font-size:12px}fieldset{border:1px solid #ddd;border-radius:8px;margin-top:20px;padding:16px;min-width:0}fieldset>label{display:block;margin:16px 0}input[type=file]{max-width:100%}
.initialization-entry{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:20px;margin-bottom:20px}.initialization-entry p,.initialization-report p{font-size:13px;line-height:1.8;color:#65716b}.initialization-counts{display:flex;flex-wrap:wrap;gap:20px}.initialization-counts dt{font-size:12px;color:#65716b}.initialization-counts dd{margin:6px 0;font-size:22px}.reference-digest{overflow-wrap:anywhere}.initialization-report{min-height:130px}@media(max-width:600px){.initialization-entry{align-items:flex-start;flex-direction:column}}
</style>
