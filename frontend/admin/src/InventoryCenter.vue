<script setup>
import {computed,ref,reactive,onMounted,onBeforeUnmount} from 'vue';
import {onBeforeRouteLeave} from 'vue-router';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api,can,session} from './api.js';
const permit=p=>can('management_api.'+p);
const tabs=computed(()=>[
 {key:'products',label:'商品管理',permission:'view_supplierproduct',path:'inventory/products'},
 {key:'stocks',label:'设备库存',permission:'view_deviceproduct',path:'inventory/stocks'},
 {key:'devices',label:'设备管理',permission:'view_device',path:'devices'},
 {key:'runs',label:'同步记录',permission:'view_inventorysyncrun',path:'inventory/sync-runs'},
].filter(t=>permit(t.permission)));
const tab=ref(tabs.value[0]?.key||''),rows=ref([]),total=ref(0),page=ref(1),search=ref(''),device=ref(''),state=ref('');
const loading=ref(false),error=ref(''),options=ref({devices:[],phone_models:[],connections:[],base_urls:[]});
const syncing=ref(null),connectionsOpen=ref(false),connections=ref([]),connectionsError=ref('');
const syncingModels=ref(false),modelSyncResult=ref(null);
const discovering=ref(null),discoveryResult=ref('');
function deviceInfoUrl(row){
 const url=new URL('/device.html',import.meta.env.DEV?'http://127.0.0.1:4173':location.origin);
 url.search=new URLSearchParams({mode:'info',device_id:row.vendor_device_id,shop_id:row.shop_id,lang:'zh-CN'}).toString();
 return url.href;
}
async function syncDevices(connection){
 if(discovering.value!==null)return;
 discovering.value=connection.id;connectionsError.value='';discoveryResult.value='';
 try{const result=await api(`admin/device-connections/${connection.id}/sync-devices/`,{method:'POST',body:{}});discoveryResult.value=result.message;await refresh();}
 catch(e){connectionsError.value=e.message;}finally{discovering.value=null;}
}
const editOpen=ref(false),kind=ref(''),editing=ref(null),form=reactive({}),saving=ref(false),formError=ref(''),saved=ref('');
const dirty=computed(()=>editOpen.value&&JSON.stringify(form)!==saved.value);
const schema=computed(()=>tabs.value.find(t=>t.key===tab.value));
const title=computed(()=>({product:'商品映射',stock:'设备商品设置',device:editing.value?'编辑设备':'登记设备',connection:editing.value?'编辑连接':'新增连接'}[kind.value]));
const time=v=>v?new Date(v).toLocaleString('zh-CN'):'尚未同步';
const specs=v=>(v||[]).map(s=>`${s.spec_name}：${s.spec_value}`).join(' · ')||'未提供规格';
const statusText={never:'未同步',running:'同步中',success:'成功',failed:'失败'};
let requestId=0;
async function loadOptions(){options.value=await api('admin/inventory/options/');}
async function load(){
 if(!schema.value)return;
 const id=++requestId;loading.value=true;error.value='';
 const q=new URLSearchParams({page:page.value,search:search.value});
 if(device.value&&tab.value!=='devices')q.set('device',device.value);
 if(tab.value==='stocks'&&state.value)q.set('state',state.value);
 if(tab.value==='products'&&state.value==='unmapped')q.set('unmapped','true');
 try{const data=await api(`admin/${schema.value.path}/?${q}`);if(id===requestId){rows.value=data.results;total.value=data.count;}}
 catch(e){if(id===requestId){error.value=e.message;rows.value=[];total.value=0;}}
 finally{if(id===requestId)loading.value=false;}
}
function filter(){page.value=1;load();}
function switchTab(){state.value='';search.value='';rows.value=[];modelSyncResult.value=null;filter();}
async function refresh(){try{await loadOptions();await load();}catch(e){error.value=e.message;}}
async function loadConnections(){
 connectionsError.value='';
 try{let all=[],next='admin/device-connections/';while(next){const data=await api(next);all.push(...data.results);next=data.next?data.next.split('/api/v1/')[1]:null;if(data.next&&!next)throw Error('连接列表地址不正确。');}connections.value=all;}
 catch(e){connectionsError.value=e.message;}
}
async function showConnections(){connectionsOpen.value=true;await loadConnections();}
function edit(type,row=null){
 kind.value=type;editing.value=row;formError.value='';Object.keys(form).forEach(k=>delete form[k]);
 if(type==='product')Object.assign(form,{phone_model:row.phone_model,display_name:row.display_name,active:row.active});
 if(type==='stock')Object.assign(form,{active:row.active,low_stock_threshold:row.low_stock_threshold});
 if(type==='device')Object.assign(form,{name:row?.name||'',connection:row?.connection||null,vendor_device_id:row?.vendor_device_id||'',location_note:row?.location_note||'',active:row?.active??true,...(row?{revision:row.revision}:{})});
 if(type==='connection')Object.assign(form,{name:row?.name||'',base_url:row?.base_url||options.value.base_urls[0]||'',shop_id:row?.shop_id||'',payment_currency:row?.payment_currency??'USD',authorization:'',active:row?.active??true,...(row?{revision:row.revision}:{})});
 saved.value=JSON.stringify(form);editOpen.value=true;
}
async function save(){
 saving.value=true;formError.value='';
 const path={product:'inventory/products',stock:'inventory/stocks',device:'devices',connection:'device-connections'}[kind.value];
 const body={...form};if(kind.value==='connection'&&editing.value&&!body.authorization)delete body.authorization;
 try{await api(`admin/${path}/${editing.value?editing.value.id+'/':''}`,{method:editing.value?'PATCH':'POST',body});
  if('authorization' in form)form.authorization='';saved.value=JSON.stringify(form);editOpen.value=false;ElMessage.success('已保存');await refresh();if(connectionsOpen.value)await loadConnections();
 }catch(e){formError.value=e.message;}finally{saving.value=false;}
}
async function closeEdit(done){
 if(saving.value)return false;
 if(dirty.value){try{await ElMessageBox.confirm('修改尚未保存，是否丢弃？','关闭编辑',{confirmButtonText:'丢弃',cancelButtonText:'继续编辑'});}catch{return false;}}
 if('authorization' in form)form.authorization='';editOpen.value=false;if(typeof done==='function')done();return true;
}
async function sync(id){
 if(syncing.value!==null)return;syncing.value=id;
 try{const result=await api(`admin/devices/${id}/sync/`,{method:'POST',body:{}});if(result.status==='success')ElMessage.success(result.message);else ElMessage.warning(result.message);await refresh();}
 catch(e){ElMessage.error(e.message);await load();}finally{syncing.value=null;}
}
async function syncModels(){
 if(!device.value||syncingModels.value)return;
 syncingModels.value=true;modelSyncResult.value=null;
 try{modelSyncResult.value=await api('admin/inventory/products/sync-models/',{method:'POST',body:{device:device.value}});await refresh();}
 catch(e){ElMessage.error(e.message);}finally{syncingModels.value=false;}
}
function unload(e){if(dirty.value){e.preventDefault();e.returnValue='';}}
onMounted(()=>{refresh();window.addEventListener('beforeunload',unload);});
onBeforeUnmount(()=>{requestId++;window.removeEventListener('beforeunload',unload);if('authorization' in form)form.authorization='';});
onBeforeRouteLeave(()=>editOpen.value?closeEdit():true);
</script>

<template>
 <section class="inventory-page">
  <div class="inventory-heading"><div><h1>商品与库存</h1><p>统一查看设备商品、维护机型对应关系和库存快照。</p></div><el-button v-if="session.user?.is_superuser" @click="showConnections">设备连接配置</el-button></div>
  <el-alert title="库存以设备方为准。同步库存时自动新增、关联机型；不调整库存、不下单或打印。" type="info" :closable="false" show-icon/>
  <el-tabs v-model="tab" @tab-change="switchTab"><el-tab-pane v-for="item in tabs" :key="item.key" :label="item.label" :name="item.key"/></el-tabs>
  <div class="inventory-toolbar">
   <el-input v-model="search" clearable :placeholder="tab==='devices'?'搜索设备名称、编号或位置':'搜索商品、机型或设备'" aria-label="搜索库存" @keyup.enter="filter" @clear="filter"/>
   <el-select v-if="tab!=='devices'" v-model="device" clearable filterable placeholder="全部设备" aria-label="筛选设备" @change="filter"><el-option v-for="d in options.devices" :key="d.id" :value="d.id" :label="`${d.name} · ${d.vendor_device_id}`"/></el-select>
   <el-select v-if="tab==='stocks'||tab==='products'" v-model="state" clearable placeholder="全部状态" aria-label="筛选库存状态" @change="filter"><template v-if="tab==='stocks'"><el-option label="缺货" value="empty"/><el-option label="低库存" value="low"/><el-option label="数据已过期" value="stale"/></template><el-option v-else label="待映射机型" value="unmapped"/></el-select>
   <el-button @click="filter">搜索</el-button><el-button :loading="loading" @click="refresh">刷新列表</el-button>
   <el-button v-if="tab==='devices'&&permit('add_device')" type="primary" @click="edit('device')">登记设备</el-button>
   <el-button v-if="tab==='products'&&options.can_sync_models" type="primary" :loading="syncingModels" :disabled="!device||syncingModels" @click="syncModels">同步所选设备机型</el-button>
   <el-button v-if="tab==='stocks'&&device&&permit('sync_device')" type="primary" :loading="syncing===device" :disabled="syncing!==null" @click="sync(device)">同步所选设备</el-button>
  </div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon/>
  <p v-if="tab==='products'" class="inventory-hint">库存同步成功时会自动关联机型。选择设备也可立即补齐已有商品的机型，不受当前筛选限制；保留人工映射，新机型默认停用。底图需在机型管理中导入。</p>
  <template v-if="tab==='products'&&modelSyncResult"><el-alert :title="`${modelSyncResult.device_name}：${modelSyncResult.message}`" :type="modelSyncResult.skipped?'warning':'success'" :closable="false" show-icon/><p v-for="item in modelSyncResult.items.filter(i=>i.status==='skipped')" :key="item.product" class="inventory-hint">商品 {{item.goods_id}}：{{item.message}}</p></template>
  <p v-if="tab==='stocks'" class="inventory-hint">数量为该商品各货道的库存合计，超过 15 分钟标记过期；有库存不代表设备在线或已开放打印。来源价格不影响当前销售套餐。</p>
  <el-table v-if="tab==='products'" v-loading="loading" :data="rows" empty-text="暂无商品，请先登记设备并同步库存。">
   <el-table-column label="供应商商品" min-width="230"><template #default="{row}"><strong>{{row.display_name||row.name}}</strong><div class="inventory-secondary">{{row.brand_name}} · 商品 {{row.goods_id}}</div><div class="inventory-secondary">{{specs(row.specs)}}</div></template></el-table-column>
   <el-table-column prop="connection_name" label="来源连接" min-width="150"/>
   <el-table-column label="本地机型" min-width="170"><template #default="{row}">{{row.phone_model_name||'待映射'}}<div class="inventory-secondary">{{row.print_ready?'机型已标记校准':'待打印校准'}}</div></template></el-table-column>
   <el-table-column label="我方配置" width="110"><template #default="{row}"><el-tag :type="row.active?'success':'info'">{{row.active?'启用':'停用'}}</el-tag></template></el-table-column>
   <el-table-column v-if="permit('change_supplierproduct')" label="操作" width="110"><template #default="{row}"><el-button text type="primary" @click="edit('product',row)">设置映射</el-button></template></el-table-column>
  </el-table>
  <el-table v-else-if="tab==='stocks'" v-loading="loading" :data="rows" empty-text="暂无库存快照，请在设备管理中同步库存。">
   <el-table-column type="expand"><template #default="{row}"><div class="inventory-expanded"><p>{{specs(row.specs)}} · {{row.lanes.length}} 条货道</p><el-table :data="row.lanes" size="small"><el-table-column prop="lane_number" label="货道编号"/><el-table-column prop="vendor_record_id" label="货道记录 ID"/><el-table-column prop="stock" label="剩余库存"/><el-table-column label="采集时间"><template #default="{row:lane}">{{time(lane.observed_at)}}</template></el-table-column></el-table><p class="inventory-secondary">货道仅用于查看；下单由设备方选道。{{row.template_url?'供应商已提供模板，仍需审核校准。':'供应商模板待补充，可再次同步。'}}</p><div v-if="row.template_asset?.image" class="inventory-template-preview"><a :href="row.template_asset.image" target="_blank" rel="noopener"><img :src="row.template_asset.image" :alt="row.phone_model_name+' 供应商底图'" loading="lazy"/></a><span>{{row.template_asset.width}} × {{row.template_asset.height}} px · {{row.template_asset.mask?'预览遮罩已生成':'遮罩待补充'}}</span></div><a v-if="row.template_url" :href="row.template_url" target="_blank" rel="noopener noreferrer">查看供应商模板</a><router-link v-if="permit('view_phonemodel')" to="/phone-models" class="inventory-template-link">在机型管理查看底图与遮罩</router-link></div></template></el-table-column>
   <el-table-column label="商品 / 设备" min-width="220"><template #default="{row}"><strong>{{row.product_name}}</strong><div class="inventory-secondary">{{row.device_name}} · 商品 {{row.goods_id}}</div><div class="inventory-secondary">{{specs(row.specs)}}</div></template></el-table-column>
   <el-table-column label="库存合计" width="120"><template #default="{row}"><strong>{{row.stock}}</strong><el-tag v-if="row.low_stock" :type="row.stock===0?'danger':'warning'" size="small">{{row.stock===0?'缺货':'低库存'}}</el-tag></template></el-table-column>
   <el-table-column label="来源价格" min-width="140"><template #default="{row}">{{row.source_price??'—'}}<div class="inventory-secondary">{{row.source_currency||'币种未提供'}}</div></template></el-table-column>
   <el-table-column label="数据状态" min-width="190"><template #default="{row}"><el-tag :type="row.stale?'warning':'success'">{{row.stale?'已过期':'最近快照'}}</el-tag><div v-if="!row.device_active" class="inventory-secondary">设备或连接已停用</div><div class="inventory-secondary">{{time(row.observed_at)}}</div></template></el-table-column>
   <el-table-column label="预警阈值" width="100" prop="low_stock_threshold"/>
   <el-table-column v-if="permit('change_deviceproduct')" label="操作" width="90"><template #default="{row}"><el-button text type="primary" @click="edit('stock',row)">设置</el-button></template></el-table-column>
  </el-table>
  <el-table v-else-if="tab==='devices'" v-loading="loading" :data="rows" empty-text="尚未登记设备。先配置供应商连接，再登记设备。">
   <el-table-column label="设备" min-width="180"><template #default="{row}"><strong>{{row.name}}</strong><div class="inventory-secondary">设备 {{row.vendor_device_id}} · 商家 {{row.shop_id}}</div><div class="inventory-secondary">{{row.provider_profile?.device_num||'设备序列号待同步'}}</div><div class="inventory-secondary">{{row.location_note||'未填写设备位置'}}</div></template></el-table-column>
   <el-table-column prop="connection_name" label="来源连接" min-width="150"/>
   <el-table-column label="启用状态" width="110"><template #default="{row}"><el-tag :type="row.active&&row.connection_active?'success':'info'">{{row.active&&row.connection_active?'启用':'停用'}}</el-tag></template></el-table-column>
   <el-table-column label="同步状态" min-width="250"><template #default="{row}"><el-tag :type="row.sync_status==='failed'?'danger':row.stale?'warning':'success'">{{statusText[row.sync_status]||row.sync_status}}</el-tag><div class="inventory-secondary">{{row.sync_message||'尚未查询供应商库存'}}</div><div class="inventory-secondary">最近成功：{{time(row.last_success_at)}}</div></template></el-table-column>
   <el-table-column label="操作" min-width="180"><template #default="{row}"><a v-if="row.active&&row.connection_active" :href="deviceInfoUrl(row)" target="_blank" rel="noopener" class="inventory-template-link">设备信息页</a><el-button v-if="permit('change_device')" text @click="edit('device',row)">编辑</el-button><el-button v-if="permit('sync_device')" text type="primary" :disabled="syncing!==null||!row.active||!row.connection_active" :loading="syncing===row.id" @click="sync(row.id)">同步库存</el-button></template></el-table-column>
  </el-table>
  <el-table v-else-if="tab==='runs'" v-loading="loading" :data="rows" empty-text="暂无同步记录。">
   <el-table-column type="expand"><template #default="{row}"><div class="inventory-expanded"><p>仅记录库存快照变化，不代表销售或补货流水。</p><el-table :data="row.changes" size="small" empty-text="没有库存变化或本次未发布"><el-table-column prop="goods_id" label="商品 ID"/><el-table-column label="上次库存"><template #default="{row:change}">{{change.before??'首次同步'}}</template></el-table-column><el-table-column prop="after" label="本次库存"/></el-table></div></template></el-table-column>
   <el-table-column prop="device_name" label="设备" min-width="140"/><el-table-column prop="actor_name" label="触发人" width="130"/><el-table-column label="结果" width="90"><template #default="{row}"><el-tag :type="row.status==='failed'?'danger':row.status==='success'?'success':'info'">{{statusText[row.status]||row.status}}</el-tag></template></el-table-column><el-table-column prop="message" label="详情" min-width="280"/><el-table-column label="开始时间" min-width="190"><template #default="{row}">{{time(row.started_at)}}</template></el-table-column>
  </el-table>
  <el-pagination v-if="total>20" v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next, total" @current-change="load"/>
  <el-dialog v-model="connectionsOpen" title="设备连接配置" width="760px">
   <el-alert v-if="!options.encryption_ready" title="服务端尚未配置凭据加密，请先完成加密配置。" type="warning" :closable="false"/><el-alert v-if="connectionsError" :title="connectionsError" type="error" :closable="false"/>
   <p>每个服务地址与商家独立配置。保存后点击「同步设备列表」自动登记设备；新设备默认停用，请到设备管理启用并同步库存。</p><el-alert v-if="discoveryResult" :title="discoveryResult" type="success" :closable="false"/><el-button type="primary" :disabled="!options.encryption_ready" @click="edit('connection')">新增连接</el-button>
   <el-table :data="connections" empty-text="暂无连接"><el-table-column prop="name" label="名称"/><el-table-column prop="shop_id" label="商家编号"/><el-table-column label="自营收款币种"><template #default="{row}">{{row.payment_currency||'未确认'}}</template></el-table-column><el-table-column prop="masked_key" label="凭据"/><el-table-column label="状态"><template #default="{row}">{{row.active?'启用':'停用'}}</template></el-table-column><el-table-column label="操作"><template #default="{row}"><el-button text @click="edit('connection',row)">编辑</el-button><el-button text type="primary" :loading="discovering===row.id" :disabled="discovering!==null||!row.active" @click="syncDevices(row)">同步设备列表</el-button></template></el-table-column></el-table>
  </el-dialog>
  <el-dialog v-model="editOpen" :title="title" width="560px" :before-close="closeEdit" :close-on-click-modal="false">
   <el-alert v-if="formError" :title="formError" type="error" :closable="false"/>
   <el-form label-position="top" :disabled="saving" @submit.prevent="save">
    <template v-if="kind==='product'"><p>{{editing?.name}} · {{specs(editing?.specs)}}</p><el-form-item label="本地机型"><el-select v-model="form.phone_model" filterable clearable placeholder="选择对应机型" @clear="form.phone_model=null"><el-option v-for="m in options.phone_models" :key="m.id" :value="m.id" :label="`${m.name}${m.active?'':'（停用）'}`"/></el-select></el-form-item><el-form-item label="展示名称（可选）"><el-input v-model="form.display_name" maxlength="200"/></el-form-item><p class="inventory-secondary">模板校准仍在机型管理中维护；映射不会自动开放真实打印。</p></template>
    <template v-if="kind==='stock'"><p>{{editing?.product_name}} · {{editing?.device_name}}</p><el-form-item label="低库存提醒阈值"><el-input-number v-model="form.low_stock_threshold" :min="0" :max="32767" :precision="0"/></el-form-item><p class="inventory-secondary">这里只设置提醒，不改变设备库存。</p></template>
    <template v-if="kind==='device'"><el-form-item label="设备名称"><el-input v-model="form.name" maxlength="120"/></el-form-item><el-form-item label="供应商连接"><el-select v-model="form.connection" :disabled="!!editing" placeholder="请选择已配置的连接"><el-option v-for="c in options.connections" :key="c.id" :value="c.id" :label="`${c.name} · 商家 ${c.shop_id}`"/></el-select></el-form-item><el-form-item label="供应商设备编号"><el-input v-model="form.vendor_device_id" :disabled="!!editing" maxlength="40"/></el-form-item><el-form-item label="设备位置（向客户展示）"><el-input v-model="form.location_note" maxlength="200" placeholder="地址、楼层及安装点，例如：商场一楼东门旁"/></el-form-item></template>
    <template v-if="kind==='connection'"><el-form-item label="连接名称"><el-input v-model="form.name" maxlength="120"/></el-form-item><el-form-item label="设备服务地址"><el-select v-model="form.base_url" :disabled="!!editing"><el-option v-for="url in options.base_urls" :key="url" :value="url" :label="url"/></el-select></el-form-item><el-form-item label="商家编号"><el-input v-model="form.shop_id" :disabled="!!editing" maxlength="40"/></el-form-item><el-form-item label="自营收款记账币种"><el-select v-model="form.payment_currency"><el-option value="" label="未确认（不允许自动开印）"/><el-option value="USD" label="USD · 美元"/></el-select><p class="inventory-secondary">供应商未返回币种时使用。请确认与我方实付金额币种一致，不做汇率换算。</p></el-form-item><el-form-item :label="editing?'更新 Authorization（留空保留原凭据）':'Authorization'"><el-input v-model="form.authorization" type="password" show-password autocomplete="new-password"/></el-form-item></template>
    <el-form-item :label="kind==='stock'?'该设备商品销售开关':'启用'"><el-switch v-model="form.active"/></el-form-item>
   </el-form>
   <template #footer><el-button :disabled="saving" @click="closeEdit">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
  </el-dialog>
 </section>
</template>
<style scoped>
.inventory-template-preview{display:flex;align-items:center;gap:16px;margin:12px 0}.inventory-template-preview img{width:60px;height:120px;object-fit:contain}.inventory-template-link{margin-left:18px}

.inventory-heading{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:20px}.inventory-heading h1{margin:0 0 8px;font-size:28px}.inventory-heading p,.inventory-hint,.inventory-secondary{color:#65716b}.inventory-heading p{margin:0}.inventory-toolbar{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0 20px}.inventory-toolbar .el-input{width:250px}.inventory-toolbar .el-select{width:190px}.inventory-secondary{font-size:12px;line-height:1.7;margin-top:4px;overflow-wrap:anywhere}.inventory-expanded{padding:12px 28px}.inventory-hint{font-size:13px;line-height:1.7}.el-pagination{margin-top:20px}.el-form .el-select{width:100%}.el-table .el-tag{margin-left:5px}.inventory-page :deep(.el-dialog){max-width:calc(100vw - 28px)}@media(max-width:640px){.inventory-heading{align-items:flex-start;flex-direction:column}.inventory-toolbar .el-input,.inventory-toolbar .el-select{width:100%}.inventory-expanded{padding:10px}.inventory-heading h1{font-size:24px}}
</style>
