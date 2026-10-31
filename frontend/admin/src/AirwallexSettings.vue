<script setup>
import {computed,onMounted,onBeforeUnmount,reactive,ref} from 'vue';
import {onBeforeRouteLeave} from 'vue-router';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api} from './api.js';
defineProps({embedded:Boolean});
const config=ref(null),busy=ref(false),error=ref('');
const form=reactive({enabled:false,mode:'test',storefront_url:''});
const empty=()=>({client_id:'',api_key:'',webhook_secret:'',account_id:'',clear:false});
const keys=reactive({test:empty(),live:empty()});
const labels={test:'Sandbox 测试环境',live:'正式环境'},fields={client_id:'Client ID',api_key:'API Key',webhook_secret:'Webhook 签名密钥',account_id:'收款账户 Account ID（多账户密钥必填）'};
const dirty=computed(()=>config.value&&(Object.keys(form).some(k=>form[k]!==config.value[k])||Object.values(keys).some(v=>Object.values(v).some(Boolean))));
const webhook=computed(()=>form.storefront_url?form.storefront_url.replace(/\/$/,'')+'/api/v1/payments/airwallex/webhook/':'填写网站地址后显示回调地址');
function accept(data){config.value=data;for(const k of Object.keys(form))form[k]=data[k];for(const mode of ['test','live'])Object.assign(keys[mode],empty());}
async function discard(){if(busy.value)return false;if(!dirty.value)return true;try{await ElMessageBox.confirm('有未保存的支付配置，是否丢弃？','未保存的配置',{confirmButtonText:'丢弃修改',cancelButtonText:'继续编辑'});return true;}catch{return false;}}
async function load(){if(!await discard())return;busy.value=true;error.value='';try{accept(await api('admin/airwallex/'));}catch(e){error.value=e.message;}finally{busy.value=false;}}
async function save(){if(busy.value)return;busy.value=true;error.value='';try{accept(await api('admin/airwallex/',{method:'PATCH',body:{revision:config.value.revision,...form,test:{...keys.test},live:{...keys.live}}}));ElMessage.success('Airwallex 支付配置已保存');}catch(e){error.value=e.message;}finally{busy.value=false;}}
function beforeUnload(event){if(dirty.value){event.preventDefault();event.returnValue='';}}
onMounted(()=>{load();window.addEventListener('beforeunload',beforeUnload);});
onBeforeUnmount(()=>{window.removeEventListener('beforeunload',beforeUnload);for(const mode of ['test','live'])Object.assign(keys[mode],empty());});
onBeforeRouteLeave(discard);
</script>
<template>
 <section>
  <div :class="embedded?'payment-section-heading':'page-heading'"><div><p v-if="!embedded" class="eyebrow">PAYMENTS</p><h2 v-if="embedded">Airwallex</h2><h1 v-else>Airwallex 支付配置<span class="greeting-dot">.</span></h1><p class="muted">顾客通过 Airwallex 托管收银台支付手机壳订单。仅超级管理员可以管理。</p></div><el-button :disabled="busy" @click="load">刷新配置</el-button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="notice"/>
  <el-skeleton v-if="!config&&!error" :rows="8" animated/>
  <template v-if="config">
   <el-alert v-if="!config.encryption_ready" title="服务端密钥加密尚未就绪，请配置 AI_CONFIG_ENCRYPTION_KEY 后保存支付密钥。" type="error" :closable="false" class="notice"/>
   <div class="payment-layout">
    <el-form class="panel payment-form" label-position="top" :disabled="busy" @submit.prevent="save">
     <el-form-item label="启用 Airwallex 壳单支付"><el-switch v-model="form.enabled"/><span class="switch-note">{{form.enabled?'保存后新订单使用 Airwallex，并停用 Stripe':'未启用 Airwallex；所有渠道关闭时使用演示付款'}}</span></el-form-item>
     <el-form-item label="收款环境"><el-radio-group v-model="form.mode"><el-radio-button value="test">Sandbox 测试</el-radio-button><el-radio-button value="live">正式收款</el-radio-button></el-radio-group></el-form-item>
     <el-alert :title="form.mode==='live'?'正式模式将向顾客收取实际订单款项，请先完成 Sandbox 联调和商户收款激活。':'Sandbox 仅模拟收款，不向顾客收取实际款项，需使用 Sandbox 账号的凭据。'" :type="form.mode==='live'?'warning':'info'" :closable="false" class="notice"/>
     <el-form-item label="用户端网站地址"><el-input v-model="form.storefront_url" placeholder="https://你的域名"/><p class="help">填写顾客访问的网站根地址。Airwallex 返回地址需使用 HTTPS；本机联调请用 HTTPS 测试域名并把同一域名的 /api/ 转发到后端。</p></el-form-item>
     <section v-for="mode in ['test','live']" :key="mode" class="credentials">
      <h2>{{labels[mode]}}凭据 <el-tag v-if="mode===form.mode" size="small">当前选择</el-tag></h2>
      <el-form-item v-for="(label,key) in fields" :key="key" :label="label"><el-input v-model="keys[mode][key]" type="password" autocomplete="new-password" :spellcheck="false" :disabled="keys[mode].clear||!config.encryption_ready" :placeholder="config[mode][key]?.configured?'已保存 '+config[mode][key].masked+'，留空保留':'填写 '+label" maxlength="1024"/></el-form-item>
      <el-checkbox v-if="Object.keys(fields).some(k=>config[mode][k]?.configured)" v-model="keys[mode].clear">保存时清除这一环境的凭据</el-checkbox>
     </section>
     <p class="help">Account ID 在 Airwallex「设置 → 账户详情」中查看，不能填写组织 ID。密钥关联多个账户时必须指定收款账户；只关联一个账户时可留空。保存后仅新订单使用新配置。</p>
     <p class="help">凭据加密保存，返回页面仅显示末四位。测试和正式环境互不共用凭据。</p>
     <el-button native-type="submit" type="primary" :loading="busy" :disabled="!dirty">保存配置</el-button><span v-if="dirty" class="switch-note">有未保存的修改</span>
    </el-form>
    <aside class="panel setup-guide">
     <h2>接入步骤</h2>
     <ol><li>登录 Airwallex Sandbox，开通 Payments 并激活至少一种支持 USD 的支付方式。</li><li>在 Developer → API keys 获取 Client ID 和 API Key，在账户级权限中选择收款账户，并启用 Payment Acceptance（收单）的写入权限（包含查询）。关联多个账户时，在此填写对应 Account ID。</li><li>在 Developer → Webhooks 创建下方地址，勾选下方事件，复制签名密钥。</li><li>保存并启用测试配置，从用户端完成成功、拒付及 3DS 测试，核对后台付款状态后再切正式环境。</li></ol>
     <h3>Webhook 地址</h3><code class="webhook">{{webhook}}</code><p class="help">需要公网 HTTPS。Sandbox 和正式账号分别配置订阅；不能把浏览器的返回地址当作回调地址。</p>
     <h3>订阅事件</h3><code v-for="event in config.webhook_events" :key="event" class="event">{{event}}</code>
     <h3>订单规则</h3><p>金额由「价格与套餐」决定，当前支持 USD，至少 $0.50。后台验证签名并查询 Airwallex 确认成功后才记为已付款。</p><p>切换渠道仅影响新订单。已有订单仍按创建时的渠道和环境付款；失败可在「我的订单」重试，重复点击复用同一笔付款。</p><p>本次接入一次性壳单支付。退款、AI 订阅收款和实际打印下发另行接入。</p>
     <p><a href="https://www.airwallex.com/docs/payments/get-started/quickstart" target="_blank" rel="noopener noreferrer">Airwallex 官方接入文档 →</a></p><router-link to="/plans">管理壳单价格 →</router-link>
    </aside>
   </div>
  </template>
 </section>
</template>
<style scoped>
.payment-layout{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:22px}.payment-form,.setup-guide{padding:26px}.notice{margin-bottom:20px}.switch-note{font-size:12px;color:#71857b;margin-left:12px}.help{font-size:12px;color:#71857b;line-height:1.8;margin:8px 0 16px;width:100%}.credentials{border-top:1px solid #e6ece7;padding-top:18px;margin-top:18px}.payment-layout h2{font-size:17px;margin:0 0 20px}.setup-guide h3{font-size:13px;margin-top:24px}.setup-guide p,.setup-guide li{font-size:13px;color:#60766a;line-height:1.9}.setup-guide ol{padding-left:20px}.setup-guide a{color:#196967}.webhook{display:block;background:#f1f6f2;padding:12px;overflow-wrap:anywhere;font-size:12px}.event{display:block;font-size:11px;overflow-wrap:anywhere;line-height:2}@media(max-width:1050px){.payment-layout{grid-template-columns:1fr}}
</style>
