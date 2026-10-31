<script setup>
import {ref,computed} from 'vue';
import {api,session} from './api.js';
const props=defineProps({order:{type:Object,required:true}}),emit=defineEmits(['updated']);
const open=ref(false),busy=ref(false),reason=ref(''),error=ref('');
const labels={requested:'退款结果待核实',pending:'退款处理中',succeeded:'已退款',failed:'退款失败'};
const refund=computed(()=>props.order.refund);
const canManage=computed(()=>session.user?.is_superuser);
async function reload(){emit('updated',await api(`admin/orders/${props.order.id}/`));}
async function act(submit=false){
 if(busy.value)return;busy.value=true;error.value='';
 try{
  await api(`admin/orders/${props.order.id}/refund/`,submit?{method:'POST',body:{revision:props.order.revision,confirmed:true,reason:refund.value?.reason||reason.value.trim()}}:{});
  open.value=false;
 }catch(e){error.value=e.message;}
 finally{try{await reload();}catch(e){error.value=error.value||e.message;}busy.value=false;}
}
function showConfirm(){reason.value=refund.value?.reason||'';error.value='';open.value=true;}
</script>
<template>
 <section v-if="order.can_refund||refund" class="refund-panel">
  <h3>退款</h3>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon/>
  <template v-if="refund">
   <p><strong>{{labels[refund.status]||refund.status}}</strong> · {{refund.currency}} {{refund.amount}}</p>
   <p>退款原因：{{refund.reason}}</p><p>退款单号：{{refund.provider_id||refund.reference}}</p>
   <p v-if="refund.completed_at">退款确认时间：{{new Date(refund.completed_at).toLocaleString('zh-CN')}}</p>
   <p v-if="refund.status==='requested'">请求已保存，渠道是否受理尚待核实。先刷新状态；重试提交会复用同一退款请求。</p>
   <p v-if="refund.status==='pending'">支付渠道正在处理，请勿在渠道后台重复发起退款。</p>
   <p v-if="refund.status==='succeeded'">支付渠道已确认退款，顾客实际到账时间由银行或支付方式决定。</p>
   <p v-if="refund.status==='failed'">支付渠道已拒绝此次退款，请核对渠道退款记录和余额后处理。</p>
   <el-button v-if="canManage" :loading="busy" @click="act(false)">刷新退款状态</el-button>
   <el-button v-if="canManage&&refund.status==='requested'&&!refund.provider_id" :disabled="busy" @click="showConfirm">重试提交</el-button>
  </template>
  <el-button v-else-if="order.can_refund" type="danger" plain :disabled="busy" @click="showConfirm">整单退款</el-button>
  <el-dialog v-model="open" title="确认整单退款" width="min(480px, 94vw)" append-to-body :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy">
   <p>订单：{{order.reference}}</p>
   <p class="refund-amount">原路退回 {{order.currency}} {{order.amount}}</p>
   <p>{{order.mode.endsWith('_live')?'这是正式订单，确认后将发起实际退款。':'这是测试订单，将模拟退款。'}} 当前仅支持全额退款。</p>
   <p v-if="['printing','ready','completed'].includes(order.status)">此订单已进入打印或交付流程。退款不会自动停止设备或收回商品，请先核对处理情况。</p>
   <el-input v-model="reason" type="textarea" :rows="3" maxlength="128" show-word-limit placeholder="填写退款原因" :disabled="busy||!!refund"/>
   <el-alert v-if="error" :title="error" type="error" :closable="false"/>
   <template #footer><el-button :disabled="busy" @click="open=false">取消</el-button><el-button type="danger" :loading="busy" :disabled="!reason.trim()" @click="act(true)">确认退款 {{order.currency}} {{order.amount}}</el-button></template>
  </el-dialog>
 </section>
</template>
<style scoped>
.refund-panel{border:1px solid #e5d6cc;border-radius:10px;padding:18px;margin:20px 0}.refund-panel h3{margin-top:0}.refund-panel p{font-size:13px;line-height:1.8;overflow-wrap:anywhere}.refund-amount{font-size:20px;font-weight:700;color:#b13d3d}
</style>
