<script setup>
import {computed,onMounted,reactive,ref,watch} from 'vue';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api,can,session} from './api.js';
const rows=ref([]),total=ref(0),page=ref(1),search=ref(''),query=ref(''),active=ref('all'),loading=ref(false),error=ref('');
const open=ref(false),detail=ref(null),detailError=ref(''),detailLoading=ref(false),saving=ref(false);
const ledger=ref([]),ledgerCursor=ref(null),ledgerBusy=ref(false),ledgerError=ref('');
const creditKinds={opening:'期初余额',signup:'注册赠送',grant:'后台补发',generation:'AI 生成扣减',cancel_refund:'取消退还',failure_refund:'失败退还',refund_expired:'原周期已到期，余额不变',subscription:'套餐额度发放',renewal:'月度额度更新',expiry:'月度额度到期'};
const form=reactive({active:true,notes:''}),grant=reactive({amount:1,reason:''});
const editable=computed(()=>can('management_api.change_customer'));
const dirty=computed(()=>detail.value&&(form.active!==detail.value.active||form.notes!==detail.value.notes));
let listVersion=0,detailVersion=0;
const date=value=>value?new Date(value).toLocaleString('zh-CN'):'—';
const statuses={queued:'排队中',generating:'生成中',ready:'已完成',failed:'生成失败',cancelled:'已取消',refunded:'已退还'};
async function load(){const version=++listVersion;loading.value=true;error.value='';try{const params=new URLSearchParams({page:String(page.value),search:query.value});if(active.value!=='all')params.set('active',active.value);const data=await api('admin/customers/?'+params);if(version===listVersion){rows.value=data.results;total.value=data.count;}}catch(e){if(version===listVersion)error.value=e.message;}finally{if(version===listVersion)loading.value=false;}}
function filter(){query.value=search.value.trim();if(page.value!==1)page.value=1;else load();}
watch(page,load);watch(active,()=>{if(page.value!==1)page.value=1;else load();});onMounted(load);
function accept(data){detail.value=data;form.active=data.active;form.notes=data.notes;}
async function show(row){const version=++detailVersion;open.value=true;detail.value=null;detailError.value='';detailLoading.value=true;ledger.value=[];ledgerCursor.value=null;ledgerError.value='';ledgerBusy.value=false;grant.amount=1;grant.reason='';try{const data=await api('admin/customers/'+row.id+'/');if(version===detailVersion){accept(data);detailLoading.value=false;await loadLedger(true);}}catch(e){if(version===detailVersion)detailError.value=e.message;}finally{if(version===detailVersion)detailLoading.value=false;}}
async function loadLedger(reset=false){
 if(!detail.value||ledgerBusy.value)return;
 const id=detail.value.id,version=detailVersion;ledgerBusy.value=true;ledgerError.value='';
 try{const data=await api('admin/customers/'+id+'/credits/'+(!reset&&ledgerCursor.value?'?before='+ledgerCursor.value:''));if(version===detailVersion){ledger.value=reset?data.results:[...ledger.value,...data.results];ledgerCursor.value=data.nextCursor;}}
 catch(e){if(version===detailVersion)ledgerError.value=e.message;}finally{if(version===detailVersion)ledgerBusy.value=false;}
}
async function close(done){if(saving.value)return;try{if(dirty.value||grant.reason.trim())await ElMessageBox.confirm('还有未保存的用户设置，是否关闭？','未保存的修改',{confirmButtonText:'关闭',cancelButtonText:'继续编辑'});++detailVersion;open.value=false;if(typeof done==='function')done();}catch{}}
async function save(){if(saving.value||!dirty.value)return;if(detail.value.active&&!form.active){try{await ElMessageBox.confirm('停用后该用户将无法登录或使用 AI，已有登录会话会失效。已有设计和次数会保留。','停用注册用户',{confirmButtonText:'停用并保存',cancelButtonText:'取消',type:'warning'});}catch{return;}}
 saving.value=true;detailError.value='';try{const data=await api('admin/customers/'+detail.value.id+'/',{method:'PATCH',body:{revision:detail.value.revision,...form}});accept({...detail.value,...data});ElMessage.success('用户设置已保存');await load();}catch(e){detailError.value=e.message;}finally{saving.value=false;}}
async function addCredits(){if(saving.value||dirty.value||!grant.reason.trim())return;try{await ElMessageBox.confirm(`为 ${detail.value.email} 补发 ${grant.amount} 次 AI 创作额度？`,'确认补发',{confirmButtonText:'确认补发',cancelButtonText:'取消'});}catch{return;}
 saving.value=true;detailError.value='';try{await api('admin/customers/'+detail.value.id+'/grant/',{method:'POST',body:{revision:detail.value.revision,amount:grant.amount,reason:grant.reason.trim()}});grant.reason='';accept(await api('admin/customers/'+detail.value.id+'/'));ElMessage.success('次数已补发');await loadLedger(true);await load();}catch(e){detailError.value=e.message;}finally{saving.value=false;}}
</script>
<template>
<section>
 <div class="page-heading"><div><p class="eyebrow">CUSTOMER ACCOUNTS</p><h1>注册用户<span class="greeting-dot">.</span></h1><p class="muted">管理通过邮箱验证的顾客账号、AI 额度与使用情况。</p></div><el-button :loading="loading" @click="load">刷新列表</el-button></div>
 <div class="customer-context"><span>顾客账号通过邮箱验证码注册，不具备后台权限。</span><router-link v-if="can('auth.view_user')" to="/users">管理后台管理员 →</router-link></div>
 <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice"/>
 <div class="panel customer-panel">
  <div class="customer-toolbar"><form @submit.prevent="filter"><el-input v-model="search" placeholder="搜索邮箱或昵称" aria-label="搜索注册用户" clearable/><el-button native-type="submit">搜索</el-button></form><el-select v-model="active" aria-label="账号状态" style="width:150px"><el-option label="全部状态" value="all"/><el-option label="正常使用" value="true"/><el-option label="已停用" value="false"/></el-select></div>
  <el-table v-loading="loading" :data="rows" empty-text="暂无符合条件的注册用户。顾客完成邮箱验证后会出现在这里。">
   <el-table-column label="顾客" min-width="240"><template #default="{row}"><button class="customer-link" @click="show(row)">{{row.display_name||row.email}}</button><div v-if="row.display_name" class="small muted">{{row.email}}</div></template></el-table-column>
   <el-table-column label="账号状态" width="110"><template #default="{row}"><el-tag :type="row.active?'success':'info'" effect="plain">{{row.active?'正常':'已停用'}}</el-tag></template></el-table-column>
   <el-table-column label="剩余赠送次数" width="135"><template #default="{row}"><strong>{{row.credits.remaining}}</strong><span class="muted"> 次</span></template></el-table-column>
   <el-table-column label="已用 / 预留" width="120"><template #default="{row}">{{row.credits.used}} 次</template></el-table-column>
   <el-table-column label="注册时间" min-width="175"><template #default="{row}">{{date(row.created_at)}}</template></el-table-column>
   <el-table-column label="最近登录" min-width="175"><template #default="{row}">{{date(row.last_login_at)}}</template></el-table-column>
   <el-table-column label="操作" fixed="right" width="90"><template #default="{row}"><el-button link type="primary" @click="show(row)">查看详情</el-button></template></el-table-column>
  </el-table>
  <div class="customer-pagination"><span class="muted">共 {{total}} 位注册用户</span><el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" hide-on-single-page/></div>
 </div>
 <el-drawer v-model="open" title="注册用户详情" size="min(680px, 100vw)" :before-close="close" :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving" destroy-on-close>
  <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" class="notice"/>
  <el-skeleton v-if="detailLoading" :rows="8" animated/>
  <template v-if="detail">
   <div class="customer-identity"><span class="customer-avatar">{{(detail.display_name||detail.email).slice(0,1).toUpperCase()}}</span><div><h2>{{detail.display_name||'未设置昵称'}}</h2><p>{{detail.email}}</p><small class="muted">邮箱已验证 · {{date(detail.verified_at)}}</small></div></div>
   <div class="customer-stats"><div><strong>{{detail.credits.remaining}}</strong><span>剩余赠送次数</span></div><div><strong>{{detail.credits.welcome_granted}}</strong><span>注册赠送</span></div><div><strong>{{detail.credits.bonus_granted}}</strong><span>后台补发</span></div><div><strong>{{detail.credits.used}}</strong><span>已用 / 预留</span></div></div>
   <p class="muted small">排队和生成中的任务会预留次数，失败或取消排队后退还。月度套餐额度单独计算。</p>
   <p v-if="detail.subscription" class="small">月度套餐：本期已用 {{detail.subscription.used}} / {{detail.subscription.monthlyLimit}} 次 · 本期结束 {{date(detail.subscription.endsAt)}}</p>
   <section class="customer-section credit-section"><div class="credit-heading"><h3>积分变动</h3><el-button link type="primary" :disabled="ledgerBusy" @click="loadLedger(true)">刷新明细</el-button></div><p class="small muted">1 积分用于 1 次 AI 生成。赠送额度与月度额度分别记账，余额为该类额度的变动后余额。</p>
    <el-alert v-if="ledgerError" :title="ledgerError" type="error" :closable="false"/>
    <el-table v-loading="ledgerBusy" :data="ledger" max-height="360" empty-text="暂无积分变动"><el-table-column label="变动" min-width="145"><template #default="{row}">{{creditKinds[row.kind]||row.kind}}<div class="small muted">{{row.pool==='gift'?'赠送额度':'月度额度'}}</div></template></el-table-column><el-table-column label="数量" width="75"><template #default="{row}"><strong :class="row.amount>0?'credit-plus':row.amount<0?'credit-minus':''">{{row.amount>0?'+':''}}{{row.amount}}</strong></template></el-table-column><el-table-column prop="balanceAfter" label="余额" width="70"/><el-table-column label="说明 / 关联任务" min-width="185"><template #default="{row}"><span>{{row.reason||'—'}}</span><div v-if="row.renderId" class="small muted credit-reference">任务 {{row.renderId}}</div><div v-if="row.actorName" class="small muted">操作人：{{row.actorName}}</div></template></el-table-column><el-table-column label="时间" min-width="165"><template #default="{row}">{{date(row.createdAt)}}</template></el-table-column></el-table>
    <el-button v-if="ledgerCursor" class="credit-more" :loading="ledgerBusy" @click="loadLedger(false)">加载更早记录</el-button><p class="small muted">旧账号上线前的可用次数以期初余额记入，不补造历史流水。</p>
   </section>
   <el-form label-position="top" :disabled="!editable||saving" @submit.prevent="save" class="customer-section"><h3>账号设置</h3><el-form-item label="允许登录与使用 AI"><el-switch v-model="form.active"/><span class="small muted status-note">停用会使已有登录会话失效</span></el-form-item><el-form-item label="客服备注（仅后台可见）"><el-input v-model="form.notes" type="textarea" :rows="3" maxlength="1000" show-word-limit placeholder="记录客服处理情况"/></el-form-item><el-button v-if="editable" native-type="submit" type="primary" :disabled="!dirty" :loading="saving">保存用户设置</el-button></el-form>
   <el-form v-if="session.user.is_superuser" label-position="top" class="customer-section" :disabled="saving||!detail.active" @submit.prevent="addCredits"><h3>补发 AI 次数</h3><p class="small muted">在现有额度上增加，不会重置已使用次数。操作会记录管理员和补发原因。</p><el-form-item label="补发数量"><el-input-number v-model="grant.amount" :min="1" :max="1000" :precision="0"/></el-form-item><el-form-item label="补发原因"><el-input v-model="grant.reason" maxlength="200" placeholder="例如：活动奖励、生成问题补偿"/></el-form-item><el-button native-type="submit" :disabled="dirty||!grant.reason.trim()||!grant.amount" :loading="saving">补发次数</el-button><span v-if="dirty" class="small muted status-note">请先保存账号设置</span></el-form>
   <section class="customer-section"><h3>最近生成记录 <small class="muted">最近 20 条</small></h3><el-table :data="detail.recent_renders" empty-text="尚无 AI 生成记录"><el-table-column prop="style_name" label="效果" min-width="120"/><el-table-column prop="phone_model" label="机型" min-width="110"/><el-table-column label="状态" width="110"><template #default="{row}">{{statuses[row.status]||row.status}}<small v-if="row.credit_restored" class="refund-note">次数已退还</small></template></el-table-column><el-table-column label="时间" min-width="165"><template #default="{row}">{{date(row.created_at)}}</template></el-table-column></el-table></section>
   <section class="customer-section"><h3>管理记录 <small class="muted">最近 20 条</small></h3><p v-if="!detail.history.length" class="muted small">暂无管理操作</p><div v-for="item in detail.history" :key="item.id" class="customer-history"><p>{{item.summary}}</p><small class="muted">{{item.actor_name}} · {{date(item.created_at)}}</small></div></section>
  </template>
 </el-drawer>
</section>
</template>
<style scoped>
.credit-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}.credit-heading h3{margin:0}.credit-plus{color:#39744d}.credit-minus{color:#a74b59}.credit-reference{overflow-wrap:anywhere}.credit-more{margin:14px 0}.credit-section>p{margin:12px 0}

.customer-context{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:16px 20px;background:#edf4ee;border:1px solid #dce8dd;border-radius:12px;margin-bottom:20px;font-size:13px;color:#58715c}.customer-context a,.customer-link{color:#216059}.customer-panel{overflow:hidden}.customer-toolbar{display:flex;gap:16px;justify-content:space-between;flex-wrap:wrap;padding:20px}.customer-toolbar form{display:flex;gap:10px;max-width:440px;flex:1;min-width:230px}.customer-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 20px;font-size:13px}.customer-link{border:0;padding:0;background:none;cursor:pointer;font:inherit;font-weight:600;text-align:left;overflow-wrap:anywhere}.small{font-size:12px;line-height:1.7}.notice{margin-bottom:16px}.customer-identity{display:flex;gap:16px;align-items:center;overflow-wrap:anywhere}.customer-identity h2{font-size:22px;margin:0 0 6px}.customer-identity p{margin:0 0 6px}.customer-avatar{flex-shrink:0;display:grid;place-items:center;width:54px;height:54px;background:#edf2e9;color:#526846;border-radius:16px;font-size:24px;font-weight:700}.customer-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:24px}.customer-stats>div{display:flex;flex-direction:column;gap:6px;background:#f5f7f2;border-radius:10px;padding:16px 12px}.customer-stats strong{font-size:25px;color:#274d3f}.customer-stats span{font-size:11px;color:#6e7d70}.customer-section{padding-top:22px;margin-top:24px;border-top:1px solid #edf0e9}.customer-section h3{font-size:16px;margin:0 0 18px}.customer-section h3 small{font-weight:400;font-size:11px;margin-left:8px}.status-note{margin-left:12px}.refund-note{display:block;color:#688251;font-size:10px}.customer-history{border-bottom:1px solid #f0f2ec;padding:12px 0}.customer-history p{font-size:13px;margin:0 0 5px;overflow-wrap:anywhere}@media(max-width:500px){.customer-stats{grid-template-columns:repeat(2,1fr)}.customer-pagination{flex-wrap:wrap}}
</style>
