<script setup>
import {computed,onMounted,onBeforeUnmount,reactive,ref} from 'vue';
import {ElMessage} from 'element-plus';
import {api} from './api.js';
import AIRenderImage from './AIRenderImage.vue';
defineProps({embedded:Boolean});

const report=ref(null),rows=ref([]),total=ref(0),page=ref(1),loading=ref(false),error=ref(''),selected=ref(null),syncing=ref('');
const dateKey=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
const range=days=>{const end=new Date(),start=new Date();start.setDate(end.getDate()-days+1);return [dateKey(start),dateKey(end)];};
const dates=ref(range(30)),filters=reactive({provider:'',model:'',status:'',search:''}),chart=ref('calls'),currency=ref('USD');
const statuses={queued:'排队中',generating:'生成中',ready:'成功',failed:'失败',cancelled:'已取消'};
const providers=ref([{id:'openai',label:'OpenAI',models:[]},{id:'ai778',label:'七七八 AI',models:[]}]);
const providerLabel=id=>providers.value.find(item=>item.id===id)?.label||id;
const models=computed(()=>providers.value.filter(item=>!filters.provider||item.id===filters.provider).flatMap(item=>item.models));
const summary=computed(()=>report.value?.summary);
const currencies=computed(()=>summary.value?.costs.map(item=>item.cost_currency)||[]);
const unit=value=>({USD:'USD',CNY:'CNY',AI778:'七七八算力'}[value]||value);
const number=value=>Number(value).toLocaleString('zh-CN',{maximumFractionDigits:8});
const axisNumber=value=>Number(value).toLocaleString('zh-CN',{maximumSignificantDigits:3});
const money=(value,code)=>value==null?'—':`${code==='USD'?'$':code==='CNY'?'¥':''}${number(value)} ${unit(code)}`;
const duration=value=>value==null?'—':`${(value/1000).toFixed(1)} 秒`;
const date=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'—';
const sourceLabels={unknown:'未知',estimated:'估算',reported:'平台实报'};
const reasonLabels={pending:'尚未完成调用',usage_missing:'接口未返回 Token 用量',usage_incomplete:'缺少完整的图文 Token 明细',usage_inconsistent:'用量合计与明细不一致',price_unavailable:'暂无对应计价规则',usage_estimate:'根据本次实际 Token 用量和单价快照估算，最终以平台账单为准。',awaiting_relay_cost:'等待查询七七八实际费用',relay_task_missing:'接口未返回可查询的任务号',relay_lookup_failed:'费用暂未查到，可稍后补查',relay_pending:'平台尚未结算，可稍后补查',relay_reported:'来自七七八任务状态接口的实际费用'};
const costReason=row=>reasonLabels[row.cost_details?.reason]||'历史记录未保存用量，无法还原当时费用。';
const chartRows=computed(()=>(report.value?.daily||[]).map(day=>{
 const cost=day.costs.find(item=>item.cost_currency===currency.value);
 return {...day,value:chart.value==='calls'?day.total:Number(cost?.total||0),label:chart.value==='calls'?`${day.total} 次 · 成功 ${day.ready} · 失败 ${day.failed}`:cost?money(cost.total,currency.value):'无已记录费用'};
}));
const chartMax=computed(()=>Math.max(...chartRows.value.map(day=>day.value),0)||1);
const chartLabel=computed(()=>chart.value==='calls'?'每日生图任务数':`每日已记录成本 · ${unit(currency.value)}`);
let sequence=0;
function query(){return new URLSearchParams({...filters,start:dates.value?.[0]||'',end:dates.value?.[1]||'',page:String(page.value)}).toString();}
async function load(reset=true){
 if(reset)page.value=1;
 if(!dates.value?.length){error.value='请选择日期范围。';return;}
 const request=++sequence;loading.value=true;error.value='';
 try{
  const q=query(),[stats,logs]=await Promise.all([api(`admin/ai-usage/?${q}`),api(`admin/ai-renders/?${q}`)]);
  if(request!==sequence)return;
  report.value=stats;rows.value=logs.results;total.value=logs.count;page.value=logs.page;providers.value=stats.providers;
  if(!currencies.value.includes(currency.value))currency.value=currencies.value[0]||'USD';
 }catch(e){if(request===sequence){error.value=e.message;report.value=null;rows.value=[];total.value=0;}}
 finally{if(request===sequence)loading.value=false;}
}
function recent(days){dates.value=range(days);load();}
async function syncCost(row){
 syncing.value=row.id;
 try{
  const updated=await api(`admin/ai-renders/${row.id}/cost/`,{method:'POST'});
  if(selected.value?.id===row.id)selected.value=updated;
  ElMessage[updated.cost_source==='reported'?'success':'info'](updated.cost_source==='reported'?'实际费用已更新':costReason(updated));
  await load(false);
 }catch(e){ElMessage.error(e.message);}finally{syncing.value='';}
}
onMounted(()=>load());onBeforeUnmount(()=>sequence++);
</script>

<template>
 <section class="ai-usage-page">
  <div class="page-heading" :class="{'ai-section-heading':embedded}"><div><p v-if="!embedded" class="eyebrow">AI USAGE & COST</p><component :is="embedded?'h2':'h1'">生图统计与日志<span v-if="!embedded" class="greeting-dot">.</span></component><p class="muted">每张图片的用量、耗时与成本，一处查看。</p></div><router-link v-if="!embedded" to="/ai/service"><el-button>生图配置</el-button></router-link></div>
  <section class="panel usage-filters">
   <div class="date-filters"><el-date-picker v-model="dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" :clearable="false" :disabled="loading" aria-label="统计日期范围"/><div class="quick-ranges"><el-button v-for="days in [7,30,90]" :key="days" :disabled="loading" @click="recent(days)">近 {{days}} 天</el-button></div></div>
   <div class="filter-fields"><el-select v-model="filters.provider" aria-label="服务商筛选" placeholder="全部服务商" clearable :disabled="loading" @change="filters.model=''"><el-option v-for="item in providers" :key="item.id" :label="item.label" :value="item.id"/></el-select><el-select v-model="filters.model" aria-label="模型筛选" placeholder="全部模型" clearable :disabled="loading"><el-option v-for="item in models" :key="item" :value="item" :label="item"/></el-select><el-select v-model="filters.status" aria-label="状态筛选" placeholder="全部状态" clearable :disabled="loading"><el-option v-for="(label,key) in statuses" :key="key" :value="key" :label="label"/></el-select><el-input v-model="filters.search" aria-label="搜索调用记录" placeholder="任务号 / 风格 / 机型" clearable :disabled="loading" maxlength="150" @keyup.enter="load()"/><el-button type="primary" :loading="loading" @click="load()">查询 / 刷新</el-button></div>
   <p>按任务创建日期统计 · {{report?.timezone||'Asia/Shanghai'}} · 仅统计本站调用</p>
  </section>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="form-alert"/>
  <el-skeleton v-if="loading&&!report" :rows="8" animated/>
  <template v-if="report">
   <div class="image-retention-note"><div><strong>图片保留 {{report.image_retention_days}} 天</strong><p>新生成的图片按此期限保存；已有图片以详情中的到期时间为准。到期清理图片，调用日志和费用继续保留。</p></div><router-link to="/ai/service#image-retention">调整保留时间 ↗</router-link></div>
   <div class="usage-cards">
    <section class="panel cost-card"><span class="metric-label">已记录成本</span><strong v-for="cost in summary.costs" :key="cost.cost_currency">{{money(cost.total,cost.cost_currency)}}</strong><strong v-if="!summary.costs.length">—</strong><small>{{summary.priced}} 笔有成本 · {{summary.unpriced}} 笔已结束任务成本未知</small><div v-for="cost in summary.costs" :key="cost.cost_currency" class="cost-parts">实报 {{money(cost.reported,cost.cost_currency)}} · 估算 {{money(cost.estimated,cost.cost_currency)}}</div></section>
    <section class="panel"><span class="metric-label">生成任务</span><strong>{{number(summary.total)}}</strong><small>成功 {{summary.ready}} · 失败 {{summary.failed}}</small><small>进行中 {{summary.pending}} · 取消 {{summary.cancelled}}</small></section>
    <section class="panel"><span class="metric-label">生成成功率</span><strong>{{summary.success_rate==null?'—':summary.success_rate+'%'}}</strong><small>成功 /（成功 + 失败）</small></section>
    <section class="panel"><span class="metric-label">平均接口耗时</span><strong>{{duration(summary.avg_duration_ms)}}</strong><small>已记录 {{summary.recorded_calls}} 次调用</small><small>不含排队和费用补查</small></section>
   </div>
   <p class="cost-explainer">OpenAI 按返回的 Token 用量及调用时单价估算；七七八费用为平台实际扣除的算力，不是人民币。不同单位分别统计，未知成本不计入合计。旧记录不会按 0 元计算。</p>
   <section class="panel trend-panel"><div class="report-heading"><div><h2>每日趋势</h2><p>{{chartLabel}}</p></div><div class="chart-controls"><el-radio-group v-model="chart" size="small" aria-label="趋势指标"><el-radio-button value="calls">调用量</el-radio-button><el-radio-button value="cost">成本</el-radio-button></el-radio-group><el-select v-if="chart==='cost'&&currencies.length" v-model="currency" size="small" aria-label="成本单位"><el-option v-for="value in currencies" :key="value" :value="value" :label="unit(value)"/></el-select></div></div>
    <el-empty v-if="!summary.total||chart==='cost'&&!currencies.length" :description="summary.total?'本时段尚无可计算的成本':'所选时段暂无生图任务'" :image-size="70"/>
    <div v-else class="trend-chart"><svg viewBox="0 0 960 250" role="img" :aria-label="chartLabel"><line v-for="tick in [0,1,2,3]" :key="tick" x1="60" :y1="20+tick*60" x2="940" :y2="20+tick*60" stroke="#e9eeeb"/><text v-for="tick in [0,1,2,3]" :key="'label'+tick" x="50" :y="24+tick*60" text-anchor="end">{{axisNumber(chartMax*(3-tick)/3)}}</text><g v-for="(day,i) in chartRows" :key="day.day"><title>{{day.day}}：{{day.label}}；{{day.unpriced}} 笔成本未知</title><rect :x="62+i*876/chartRows.length" :y="200-day.value/chartMax*180" :width="Math.max(1,876/chartRows.length-4)" :height="day.value/chartMax*180" rx="2" :fill="chart==='cost'?'#b69858':'#35746a'"/><text v-if="i===0||i===chartRows.length-1||i%Math.max(1,Math.ceil(chartRows.length/6))===0" :x="62+(i+.5)*876/chartRows.length" y="225" text-anchor="middle">{{day.day.slice(5)}}</text></g></svg></div>
   </section>
   <section class="panel model-panel"><div class="report-heading"><h2>服务商 / 模型分布</h2><span>成本不含未知记录</span></div><el-table :data="report.models" empty-text="暂无模型调用"><el-table-column label="服务商 / 模型" min-width="240"><template #default="{row}"><strong>{{providerLabel(row.provider)}}</strong><div class="muted">{{row.model_name}}</div></template></el-table-column><el-table-column prop="total" label="任务数" width="90"/><el-table-column prop="ready" label="成功" width="80"/><el-table-column prop="failed" label="失败" width="80"/><el-table-column label="平均耗时" width="120"><template #default="{row}">{{duration(row.avg_duration_ms)}}</template></el-table-column><el-table-column label="已记录成本" min-width="190"><template #default="{row}"><div v-for="cost in row.costs" :key="cost.cost_currency">{{money(cost.total,cost.cost_currency)}}</div><span v-if="!row.costs.length">—</span><small v-if="row.unpriced" class="unknown-cost">{{row.unpriced}} 笔未知</small></template></el-table-column></el-table></section>
   <section class="panel call-panel"><div class="report-heading"><h2>逐笔调用日志 <span>{{total}}</span></h2><span>点击详情查看图片、用量及计价依据</span></div><el-table :data="rows" v-loading="loading" empty-text="当前筛选下没有生图记录"><el-table-column label="创建时间 / 任务" min-width="185"><template #default="{row}"><div>{{date(row.created_at)}}</div><code class="short-id">{{row.id.slice(0,8)}}</code></template></el-table-column><el-table-column label="服务商 / 模型" min-width="210"><template #default="{row}">{{row.provider_label}}<div class="muted">{{row.model_name}}</div></template></el-table-column><el-table-column label="状态" width="105"><template #default="{row}"><el-tag size="small" :type="row.status==='ready'?'success':row.status==='failed'?'danger':'info'">{{statuses[row.status]}}</el-tag></template></el-table-column><el-table-column label="接口耗时" width="110"><template #default="{row}">{{duration(row.api_duration_ms)}}</template></el-table-column><el-table-column label="Token 用量" width="130"><template #default="{row}">{{row.usage.total_tokens==null?'—':number(row.usage.total_tokens)}}</template></el-table-column><el-table-column label="成本" min-width="155"><template #default="{row}">{{money(row.cost_amount,row.cost_currency)}}<small :class="['cost-label',row.cost_source]">{{sourceLabels[row.cost_source]}}</small></template></el-table-column><el-table-column label="图片" width="115"><template #default="{row}"><el-button v-if="row.image?.state==='available'" link type="primary" @click="selected=row">预览 / 下载</el-button><span v-else class="muted">{{{pending:'生成中',none:'无图片',expired:'已到期',deleted:'已清理',missing:'无资源'}[row.image?.state]||'—'}}</span></template></el-table-column><el-table-column label="操作" width="85" fixed="right"><template #default="{row}"><el-button link type="primary" @click="selected=row">详情</el-button></template></el-table-column></el-table><el-pagination v-if="total" v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next, total" :disabled="loading" @current-change="load(false)"/></section>
  </template>
  <el-drawer :model-value="Boolean(selected)" title="生图调用详情" size="min(700px, 100%)" @close="selected=null">
   <template v-if="selected"><AIRenderImage :key="selected.id" :record="selected"/><el-descriptions :column="1" border><el-descriptions-item label="任务号"><code>{{selected.id}}</code></el-descriptions-item><el-descriptions-item label="服务商请求号"><code>{{selected.provider_request_id||'未返回'}}</code></el-descriptions-item><el-descriptions-item label="接口地址">{{selected.endpoint}}</el-descriptions-item><el-descriptions-item label="模型">{{selected.model_name}}</el-descriptions-item><el-descriptions-item label="风格 / 机型">{{selected.style_name}} · {{selected.phone_model}}</el-descriptions-item><el-descriptions-item label="状态">{{statuses[selected.status]}} · HTTP {{selected.http_status||'未记录'}}</el-descriptions-item><el-descriptions-item label="请求参数">{{selected.request_params.size||'未记录'}} · {{selected.request_params.quality||'—'}} · {{selected.request_params.n||'—'}} 张</el-descriptions-item><el-descriptions-item label="调用开始">{{date(selected.api_started_at)}}</el-descriptions-item><el-descriptions-item label="调用结束 / 耗时">{{date(selected.api_finished_at)}} / {{duration(selected.api_duration_ms)}}</el-descriptions-item><el-descriptions-item label="顾客生成次数">{{selected.credit_restored?'已退还':selected.status==='cancelled'?'未消耗':'未退还'}}<small class="field-help">与上游平台的实际费用分别记账。</small></el-descriptions-item><el-descriptions-item v-if="selected.error_code" label="失败原因">{{selected.error_code}}<p>{{selected.error_message}}</p></el-descriptions-item></el-descriptions>
    <h3>用量与费用</h3><div class="detail-cost"><strong>{{money(selected.cost_amount,selected.cost_currency)}}</strong><el-tag :type="selected.cost_source==='reported'?'success':'info'">{{sourceLabels[selected.cost_source]}}</el-tag></div><p class="cost-explainer">{{costReason(selected)}}</p>
    <el-descriptions :column="1" border><el-descriptions-item label="输入 Token">{{selected.usage.input_tokens??'未返回'}}</el-descriptions-item><el-descriptions-item label="输入文本 / 图片">{{selected.usage.input_tokens_details?.text_tokens??'未返回'}} / {{selected.usage.input_tokens_details?.image_tokens??'未返回'}}</el-descriptions-item><el-descriptions-item label="输出 Token">{{selected.usage.output_tokens??'未返回'}}</el-descriptions-item><el-descriptions-item label="总 Token">{{selected.usage.total_tokens??'未返回'}}</el-descriptions-item><el-descriptions-item label="费用记录时间">{{date(selected.cost_recorded_at)}}</el-descriptions-item></el-descriptions>
    <template v-if="selected.cost_details.pricing?.version"><h3>计价快照 · {{selected.cost_details.pricing.version}}</h3><p class="cost-explainer">美元 / 百万 Token，按直接 Images API 标准单价计算。</p><dl class="price-snapshot"><template v-for="(label,key) in {input_text:'输入文本',input_image:'输入图片',output_image:'输出图片',output_text:'输出文本'}" :key="key"><dt>{{label}}</dt><dd>{{selected.cost_details.pricing.rates_per_million[key]??'无报价'}}</dd></template></dl><a :href="selected.cost_details.pricing.source_url" target="_blank" rel="noopener noreferrer">查看官方计价依据 ↗</a></template>
    <el-button v-if="selected.provider==='ai778'&&selected.cost_source!=='reported'&&selected.provider_request_id&&['ready','failed'].includes(selected.status)" type="primary" class="sync-cost" :loading="syncing===selected.id" :disabled="Boolean(syncing)" @click="syncCost(selected)">补查七七八实际费用</el-button>
   </template>
  </el-drawer>
 </section>
</template>

<style scoped>
.image-retention-note{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;padding:18px 20px;margin-bottom:20px;background:#eaf1ed;border-radius:10px;color:#385b49;font-size:13px}.image-retention-note p{font-size:12px;line-height:1.8;color:#73847b;margin:5px 0 0}.image-retention-note a{white-space:nowrap;color:#196967}
.usage-filters{padding:20px;margin-bottom:20px}.date-filters,.filter-fields,.quick-ranges,.chart-controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.date-filters{margin-bottom:12px}.date-filters :deep(.el-date-editor){flex:0 1 350px}.quick-ranges .el-button+.el-button{margin-left:0}.filter-fields>.el-select{width:180px}.filter-fields>.el-input{width:230px}.usage-filters>p,.cost-explainer{font-size:12px;line-height:1.9;color:#73847b;margin:13px 0 0}.usage-cards{display:grid;grid-template-columns:1.5fr repeat(3,1fr);gap:16px}.usage-cards>section{padding:23px;display:flex;flex-direction:column;gap:9px}.usage-cards .cost-card{background:#eff6f0;border-color:#dbe9de}.metric-label{font-size:12px;color:#6d8075}.usage-cards strong{font-size:28px;letter-spacing:-.7px;color:#254f40;font-weight:600}.usage-cards small,.cost-parts{font-size:11px;color:#748379;line-height:1.7}.cost-parts{border-top:1px solid #dce7de;padding-top:9px}.trend-panel,.model-panel,.call-panel{margin-top:22px;padding:24px;min-width:0}.report-heading{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:20px;flex-wrap:wrap}.report-heading h2{font-size:16px;margin:0;color:#385b49}.report-heading p,.report-heading>span{font-size:12px;color:#7b8a81;margin:6px 0 0}.report-heading h2 span{font-size:12px;margin-left:8px;color:#8c9b91}.chart-controls>.el-select{width:130px}.trend-chart{overflow-x:auto}.trend-chart svg{width:100%;min-width:640px;max-height:300px;display:block;overflow:visible}.trend-chart text{font-size:11px;fill:#809187}.muted{font-size:12px;overflow-wrap:anywhere}.short-id{font-size:11px;color:#8a998f}.cost-label,.unknown-cost{display:block;font-size:11px;color:#9b8a66;margin-top:2px}.cost-label.reported{color:#3a8668}.el-pagination{margin-top:22px;justify-content:flex-end}.ai-usage-page :deep(.el-drawer__body){overflow-wrap:anywhere}.ai-usage-page :deep(.el-descriptions__label){min-width:110px}.detail-cost{display:flex;align-items:center;gap:14px}.detail-cost strong{font-size:27px;color:#285843}.ai-usage-page h3{margin:28px 0 16px;font-size:15px}.detail-cost+.cost-explainer{margin-bottom:16px}.price-snapshot{display:grid;grid-template-columns:1fr 1fr;gap:12px;background:#f3f6f1;border-radius:9px;padding:20px;font-size:13px}.price-snapshot dd{margin:0;text-align:right}.sync-cost{display:block;margin-top:24px}.field-help{display:block;color:#87958c;font-size:11px;margin-top:5px}@media(max-width:1200px){.usage-cards{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.trend-chart text{font-size:16px}.usage-cards{grid-template-columns:1fr}.usage-cards>section{padding:18px}.trend-panel,.model-panel,.call-panel{padding:15px}.filter-fields>.el-select,.filter-fields>.el-input{width:100%}.date-filters :deep(.el-date-editor){width:100%;max-width:100%;min-width:0}.date-filters :deep(.el-range-input){min-width:0}.el-pagination{justify-content:center}}
</style>
