<script setup>
import {ref,onMounted,onBeforeUnmount,computed} from 'vue';
import {api} from './api.js';
import OrderCustomer from './OrderCustomer.vue';
import OrderProgress from './OrderProgress.vue';
import {startVisiblePolling} from '../../storefront/visible-polling.js';
import OrderRefund from './OrderRefund.vue';
import {displayLabels} from './resources.js';
import {phone} from '../../storefront/art.js';
import {exportCase} from '../../storefront/print-export.js';
import {orderArtwork} from './order-artwork.js';
const props=defineProps({id:{type:Number,required:true}});
const emit=defineEmits(['updated']);
function updatedOrder(data){order.value=data;emit('updated');}
const order=ref(null),error=ref(''),artwork=ref(null),artworkError=ref('');
const printUrl=ref(''),printError=ref(''),printBusy=ref(false),effectiveDpi=ref(null);
let renderVersion=0,disposed=false,stopPolling=()=>{};
const progressError=ref(''),progressBusy=ref(false);
async function refreshProgress(){
 if(!order.value||progressBusy.value||disposed)return;
 progressBusy.value=true;const before=order.value;
 try{const data=await api(`admin/orders/${props.id}/progress/`);if(disposed||order.value!==before)return;order.value={...order.value,...data};progressError.value='';}
 catch{if(!disposed)progressError.value='进度暂时无法刷新，保留上次结果。请稍后重试。';}
 finally{progressBusy.value=false;}
}
function clearPrint(){if(printUrl.value)URL.revokeObjectURL(printUrl.value);printUrl.value='';}
async function renderPrint(){
 if(!artwork.value?.template||artwork.value.template.previewOnly||printBusy.value)return;
 const version=++renderVersion;printBusy.value=true;printError.value='';clearPrint();effectiveDpi.value=null;
 try{
  const result=await exportCase(artwork.value.design,artwork.value.pass.model);
  if(disposed||version!==renderVersion)return;
  printUrl.value=URL.createObjectURL(result.blob);effectiveDpi.value=result.effectiveDpi;
 }catch{if(!disposed&&version===renderVersion)printError.value='打印图生成失败，请检查设计素材是否能加载后重试。';}
 finally{if(!disposed&&version===renderVersion)printBusy.value=false;}
}
onMounted(async()=>{
 try{
  const data=await api(`admin/orders/${props.id}/`);if(disposed)return;order.value=data;
  stopPolling=startVisiblePolling({refresh:refreshProgress,interval:5000,enabled:()=>!['dispensed','cancelled','closed','refunded','test','delivery','unspecified'].includes(order.value?.progress?.code)||['requested','pending'].includes(order.value?.refund?.status)});
  try{artwork.value=orderArtwork(data);}catch{artworkError.value='订单设计或机型模板无法读取，请核对后再制作打印文件。';return;}
  await renderPrint();
 }catch(e){if(!disposed)error.value=e.message;}
});
onBeforeUnmount(()=>{stopPolling();disposed=true;++renderVersion;clearPrint();});
const preview=computed(()=>{try{return artwork.value?phone(artwork.value.design,artwork.value.pass.model).replaceAll('src="./assets/','src="/assets/') :'';}catch{return '';}});
</script>
<template><section class="order-detail"><el-alert v-if="error" :title="error" type="error" :closable="false"/><el-skeleton v-else-if="!order" :rows="4" animated/><template v-else><el-alert :title="order.mode==='demo'?'测试订单：支付和机器打印均为模拟，不代表实际到账或生产。':order.mode==='stripe_test'?'Stripe 测试订单：不实际扣款。':order.mode==='stripe_live'?'Stripe 正式订单：付款以 Stripe 验证通知为准。':order.mode==='airwallex_test'?'Airwallex 测试订单：不实际扣款。':order.mode==='airwallex_live'?'Airwallex 正式订单：付款以验证后的支付结果为准。':order.mode==='free_test'?'0 元免付联调：不产生实际收款，打印以设备反馈为准。':'历史订单'" type="info" :closable="false"/><el-alert v-if="artworkError" :title="artworkError" type="error" :closable="false" class="artwork-notice"/>
<OrderProgress :progress="order.progress"/><el-alert v-if="progressError" :title="progressError" type="warning" :closable="false"/><el-button :loading="progressBusy" @click="refreshProgress">刷新打印进度</el-button>
<OrderRefund :order="order" @updated="updatedOrder"/>
<section v-if="artwork" class="order-artwork" aria-label="订单图片与打印文件">
 <div class="order-artwork-grid">
  <article class="artwork-card"><h3>成品效果</h3><div class="artwork-stage"><div v-if="preview" class="order-design" v-html="preview"></div></div><p>镜头和壳边用于展示，不会印在设计上。</p></article>
  <article class="artwork-card"><h3>透明打印图</h3><div class="artwork-stage print-stage" :aria-busy="printBusy">
   <el-image v-if="printUrl" class="print-image" :src="printUrl" :preview-src-list="[printUrl]" preview-teleported fit="contain" :alt="order.model_name+' 打印图，镜头孔位透明'"/>
   <span v-else-if="printBusy" class="artwork-status" role="status">正在生成带孔位的打印图…</span>
   <div v-else-if="printError" class="artwork-status" role="alert"><p>{{printError}}</p><el-button @click="renderPrint">重试生成</el-button></div>
   <span v-else-if="artwork.template?.previewOnly" class="artwork-status">已保存供应商预览模板，打印参数尚待确认。</span><span v-else class="artwork-status">该订单没有固定的打印模板版本，暂不能生成孔位文件。</span>
  </div><p>棋盘格表示透明区域；镜头孔和壳外区域均不打印。</p>
  <a v-if="printUrl" class="print-download" :href="printUrl" :download="artwork.filename">下载{{artwork.template.calibrated?'打印':'打样'}} PNG</a></article>
 </div>
 <template v-if="artwork.template"><p class="print-spec">{{order.model_name}} · {{artwork.template.printWidth}} × {{artwork.template.printHeight}} px · {{artwork.template.dpi?artwork.template.dpi+' DPI':'原始像素 · 打印 DPI 待确认'}} · 订单版本 {{order.revision}}</p>
 <p v-if="!artwork.template.calibrated" class="print-calibration">待打样校准：孔位按当前机型模板留空，批量打印前请让供应商确认孔位、出血和偏移。{{artwork.template.sizeEvidence==='template-density-derived'?'此机型的输出尺寸也待供应商确认。':''}}</p>
 <p v-if="Number.isFinite(effectiveDpi)&&effectiveDpi>0&&effectiveDpi<150" class="print-calibration">图片有效分辨率约 {{Math.round(effectiveDpi)}} DPI。导出为 300 DPI 不会补充原图细节，请核对清晰度。</p></template>
 <p v-else class="print-calibration">历史订单需先确认对应机型模板，不能用相近机型代替。</p>
</section><el-descriptions :column="1" border><el-descriptions-item label="订单编号">{{order.reference}}</el-descriptions-item><el-descriptions-item label="配送方式">{{displayLabels[order.fulfillment_type]||'待确认'}}</el-descriptions-item><el-descriptions-item label="机型">{{order.model_name}}</el-descriptions-item><el-descriptions-item label="手机壳物料">{{({standard:"普通款",magnetic:"磁吸款"})[order.case_material]||"待确认"}}</el-descriptions-item><el-descriptions-item label="确认金额">{{order.currency}} {{order.amount}}</el-descriptions-item><el-descriptions-item label="客户邮箱"><OrderCustomer :customer-id="order.customer_id" :email="order.customer_email"/></el-descriptions-item><el-descriptions-item label="设计码">{{order.snapshot?.code||'—'}}</el-descriptions-item><el-descriptions-item label="订单版本">{{order.revision}}</el-descriptions-item><el-descriptions-item v-if="order.stripe_session_id" label="Stripe Checkout">{{order.stripe_session_id}}</el-descriptions-item><el-descriptions-item v-if="order.stripe_payment_intent" label="Stripe 付款编号">{{order.stripe_payment_intent}}</el-descriptions-item><el-descriptions-item v-if="order.airwallex_payment_intent" label="Airwallex 付款编号">{{order.airwallex_payment_intent}}</el-descriptions-item><el-descriptions-item v-if="order.paid_at" label="付款时间">{{new Date(order.paid_at).toLocaleString('zh-CN')}}</el-descriptions-item><template v-if="order.fulfillment"><el-descriptions-item label="打印设备">{{order.fulfillment.device_name}} · {{order.fulfillment.device_location||'位置未填写'}}</el-descriptions-item><el-descriptions-item label="供应商支付记录">{{order.fulfillment.cloud_status?.payment_recorded?'金额已核实':order.fulfillment.print_confirmed?'正在核实':'尚未确认开印'}}</el-descriptions-item><el-descriptions-item v-if="order.fulfillment.status_updated_at" label="设备状态更新时间">{{new Date(order.fulfillment.status_updated_at).toLocaleString('zh-CN')}}</el-descriptions-item><el-descriptions-item v-if="order.fulfillment.cloud_status?.pay_status!==undefined" label="供应商原始状态">支付 {{order.fulfillment.cloud_status.pay_status}} · 打印 {{order.fulfillment.cloud_status.print_status}} · 出货 {{order.fulfillment.cloud_status.shipment_status}}（{{order.fulfillment.cloud_status.phase_verified?'已按确认规则解释':'临时映射，待核验'}}）</el-descriptions-item><el-descriptions-item v-if="order.fulfillment.message" label="履约提示">{{order.fulfillment.message}}</el-descriptions-item></template><el-descriptions-item v-if="order.mode==='demo'" label="演示设备">{{order.station_id||'尚未开印'}}</el-descriptions-item><el-descriptions-item label="创建时间">{{new Date(order.created_at).toLocaleString('zh-CN')}}</el-descriptions-item></el-descriptions><p class="muted">订单快照独立保存。可修改客服备注；退款通过上方退款入口处理，付款与打印状态由订单流程更新。</p></template></section></template>
<style scoped>
.order-detail{margin-bottom:26px;overflow-wrap:anywhere}.order-design{width:170px;max-width:100%;margin:0 auto}.order-detail .muted{font-size:12px;line-height:1.6}
.order-design :deep(.phone-case){width:100%;aspect-ratio:300/570;position:relative;border-radius:17% / 9%;background:#d8d8cd;box-shadow:inset 0 0 0 3px #aaa99d,10px 17px 22px #24291f29,2px 2px 2px #fff;overflow:hidden;border:4px solid #b1b1a5;container-type:inline-size}.order-design :deep(.case-art){position:absolute;inset:0;transform-origin:center;overflow:hidden}.order-design :deep(.case-art>svg),.order-design :deep(.case-art>img){width:100%;height:100%;object-fit:cover;display:block}.order-design :deep(.case-edge){position:absolute;inset:0;border:2px solid #ffffff8f;border-radius:15% / 8%;box-shadow:inset 0 0 10px #24251e35;pointer-events:none}.order-design :deep(.camera){position:absolute;top:4%;left:7%;width:45%;height:24%;border-radius:23%;background:linear-gradient(130deg,#b7b7ac,#e3e3d7 65%,#92958b);border:1px solid #7b8078;box-shadow:2px 3px 4px #252a254d;z-index:6}.order-design :deep(.camera i){position:absolute;width:37%;height:36%;border-radius:50%;border:3px solid #424740;background:radial-gradient(circle at 40% 35%,#486376 0,#0e141e 23%,#182533 44%,#05090d 48%,#373d40 58%,#1c201f 60%);box-shadow:0 1px 3px #111}.order-design :deep(.camera i:nth-child(1)){left:8%;top:8%}.order-design :deep(.camera i:nth-child(2)){right:6%;top:32%}.order-design :deep(.camera i:nth-child(3)){left:8%;bottom:8%}.order-design :deep(.camera b){position:absolute;width:15%;height:15%;right:15%;top:10%;background:#faf2da;border-radius:50%}.order-design :deep(.samsung .camera){width:22%;height:30%;background:none;border:0;box-shadow:none;left:6%}.order-design :deep(.samsung .camera i){left:0;right:auto;width:80%;height:29%}.order-design :deep(.samsung .camera i:nth-child(2)){top:35%}.order-design :deep(.samsung .camera i:nth-child(3)){bottom:0}.order-design :deep(.samsung .camera b){display:none}.order-design :deep(.design-layers){position:absolute;inset:0;z-index:2;pointer-events:none}.order-design :deep(.design-layer){position:absolute;line-height:1;transform-origin:center;user-select:none}.order-design :deep(.design-layer img){display:block;width:100%;height:auto;pointer-events:none}.order-design :deep(.layer-text){display:block;white-space:pre-wrap;overflow-wrap:anywhere;text-align:center;font-weight:700;line-height:1.15}
.order-design :deep(.case-art>.placed-photo){position:absolute;transform-origin:center;max-width:none}
.order-design :deep(.phone-case.vendor-template){border:0;border-radius:0;background:transparent;box-shadow:none;overflow:visible;isolation:isolate;filter:drop-shadow(3px 5px 6px #24291f25)}
.order-design :deep(.vendor-template .print-surface){position:absolute;inset:0;overflow:hidden;mask-image:var(--print-mask);-webkit-mask-image:var(--print-mask);mask-size:100% 100%;-webkit-mask-size:100% 100%;mask-repeat:no-repeat;-webkit-mask-repeat:no-repeat;mask-mode:alpha}
.order-design :deep(.vendor-template .template-overlay){position:absolute;inset:0;width:100%;height:100%;z-index:6;pointer-events:none;user-select:none}
.order-artwork{margin:22px 0}.order-artwork-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.artwork-card{min-width:0;padding:16px;border:1px solid #dde6e2;border-radius:12px;background:#fafcfb}.artwork-card h3{font-size:14px;margin:0 0 16px}.artwork-card p{font-size:12px;line-height:1.7;color:#637773;margin:12px 0 0}.artwork-stage{min-height:348px;display:flex;align-items:center;justify-content:center}.print-stage{border-radius:8px;background:repeating-conic-gradient(#e3e9e6 0% 25%,#fff 0% 50%) 0 0/16px 16px}.print-image{display:block;width:170px;max-width:100%;cursor:zoom-in}.print-image :deep(img){display:block;width:100%;height:auto}.artwork-status{padding:20px;text-align:center;font-size:12px;line-height:1.8;background:#ffffffdc}.artwork-status .el-button{margin-top:12px}.print-download{display:block;width:fit-content;margin-top:14px;padding:10px 15px;border-radius:7px;background:#216059;color:white;text-decoration:none;font-size:13px}.print-download:hover{background:#184c46}.print-download:focus-visible{outline:2px solid #216059;outline-offset:3px}.print-spec{font-size:12px;line-height:1.8;color:#4d6560;margin:14px 0 6px}.print-calibration{font-size:12px;line-height:1.8;color:#916a29;margin:6px 0}.artwork-notice{margin-top:18px}@media(max-width:520px){.order-artwork-grid{grid-template-columns:1fr}}

</style>
