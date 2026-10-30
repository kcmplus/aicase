<script setup>
import {computed,onMounted,onBeforeUnmount,reactive,ref} from 'vue';
import {onBeforeRouteLeave} from 'vue-router';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api} from './api.js';
const config=ref(null),busy=ref(false),error=ref('');
const form=reactive({enabled:false,mode:'test',storefront_url:''});
const keys=reactive({test:{secret_key:'',webhook_secret:'',clear:false},live:{secret_key:'',webhook_secret:'',clear:false}});
const labels={test:'测试环境',live:'正式环境'};
const dirty=computed(()=>config.value&&(Object.keys(form).some(k=>form[k]!==config.value[k])||Object.values(keys).some(v=>v.secret_key||v.webhook_secret||v.clear)));
const webhook=computed(()=>form.storefront_url?form.storefront_url.replace(/\/$/,'')+'/api/v1/payments/stripe/webhook/':'填写网站地址后显示回调地址');
function accept(data){config.value=data;for(const k of Object.keys(form))form[k]=data[k];for(const mode of ['test','live'])Object.assign(keys[mode],{secret_key:'',webhook_secret:'',clear:false});}
async function discard(){if(busy.value)return false;if(!dirty.value)return true;try{await ElMessageBox.confirm('有未保存的支付配置，是否丢弃？','未保存的配置',{confirmButtonText:'丢弃修改',cancelButtonText:'继续编辑'});return true;}catch{return false;}}
async function load(){if(!await discard())return;busy.value=true;error.value='';try{accept(await api('admin/stripe/'));}catch(e){error.value=e.message;}finally{busy.value=false;}}
async function save(){if(busy.value)return;busy.value=true;error.value='';try{accept(await api('admin/stripe/',{method:'PATCH',body:{revision:config.value.revision,...form,test:{...keys.test},live:{...keys.live}}}));ElMessage.success('Stripe 支付配置已保存');}catch(e){error.value=e.message;}finally{busy.value=false;}}
function beforeUnload(event){if(dirty.value){event.preventDefault();event.returnValue='';}}
onMounted(()=>{load();window.addEventListener('beforeunload',beforeUnload);});
onBeforeUnmount(()=>{window.removeEventListener('beforeunload',beforeUnload);for(const mode of ['test','live'])Object.assign(keys[mode],{secret_key:'',webhook_secret:'',clear:false});});
onBeforeRouteLeave(discard);
</script>
<template>
 <section>
  <div class="page-heading"><div><p class="eyebrow">PAYMENTS</p><h1>Stripe 支付配置<span class="greeting-dot">.</span></h1><p class="muted">手机壳订单使用 Stripe 收银台付款。仅超级管理员可以管理。</p></div><el-button :disabled="busy" @click="load">刷新配置</el-button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="notice"/>
  <el-skeleton v-if="!config&&!error" :rows="8" animated/>
  <template v-if="config">
   <el-alert v-if="!config.encryption_ready" title="服务端密钥加密尚未就绪，请配置 AI_CONFIG_ENCRYPTION_KEY 后保存支付密钥。" type="error" :closable="false" class="notice"/>
   <div class="stripe-layout">
    <el-form class="panel stripe-form" label-position="top" :disabled="busy" @submit.prevent="save">
     <el-form-item label="启用 Stripe 壳单支付"><el-switch v-model="form.enabled"/><span class="switch-note">{{form.enabled?'新壳单通过 Stripe 付款':'保留现有演示付款，不实际扣款'}}</span></el-form-item>
     <el-form-item label="付款环境"><el-radio-group v-model="form.mode"><el-radio-button value="test">测试环境</el-radio-button><el-radio-button value="live">正式收款</el-radio-button></el-radio-group></el-form-item>
     <el-alert :title="form.mode==='live'?'正式模式会实际扣款，请先完成测试和 Stripe 账号激活。':'测试模式不实际扣款。注册 Stripe 后可先使用测试密钥联调。'" :type="form.mode==='live'?'warning':'info'" :closable="false" class="notice"/>
     <el-form-item label="用户端网站地址"><el-input v-model="form.storefront_url" placeholder="https://你的域名"/><p class="help">填写顾客当前访问的网站根地址，用于支付后返回订单。本机测试可填 http://localhost:4173。</p></el-form-item>
     <section v-for="mode in ['test','live']" :key="mode" class="credentials">
      <h2>{{labels[mode]}}密钥 <el-tag v-if="mode===form.mode" size="small">当前选择</el-tag></h2>
      <el-form-item label="Secret Key"><el-input v-model="keys[mode].secret_key" type="password" autocomplete="new-password" :spellcheck="false" :disabled="keys[mode].clear||!config.encryption_ready" :placeholder="config[mode].secret_key.configured?'已保存 '+config[mode].secret_key.masked+'，留空保留':`sk_${mode}_…`" maxlength="1024"/></el-form-item>
      <el-form-item label="Webhook 签名密钥"><el-input v-model="keys[mode].webhook_secret" type="password" autocomplete="new-password" :spellcheck="false" :disabled="keys[mode].clear||!config.encryption_ready" :placeholder="config[mode].webhook_secret.configured?'已保存 '+config[mode].webhook_secret.masked+'，留空保留':'whsec_…'" maxlength="1024"/></el-form-item>
      <el-checkbox v-if="config[mode].secret_key.configured||config[mode].webhook_secret.configured" v-model="keys[mode].clear">保存时清除这一环境的密钥</el-checkbox>
     </section>
     <p class="help">密钥加密保存在服务端，保存后仅显示末四位。托管收银台无需填写 Publishable Key。</p>
     <el-button native-type="submit" type="primary" :loading="busy" :disabled="!dirty">保存配置</el-button><span v-if="dirty" class="switch-note">有未保存的修改</span>
    </el-form>
    <aside class="panel setup-guide">
     <h2>注册后这样启用</h2>
     <ol><li>在 <a href="https://dashboard.stripe.com/register" target="_blank" rel="noopener noreferrer">Stripe</a> 注册账号，复制测试环境的 Secret Key。</li><li>在 Stripe Workbench → Webhooks 创建事件接收地址，选择当前账号的事件。</li><li>勾选下方事件，复制签名密钥（whsec_…），填入左侧。</li><li>保存测试配置并启用 Stripe，完成一笔测试壳单。确认订单变为已付款后，再配置正式环境。</li></ol>
     <h3>Webhook 地址</h3><code class="webhook">{{webhook}}</code><p class="help">线上需要 HTTPS。测试和正式环境分别创建接收地址；都使用上面的地址。本机测试使用 Stripe CLI 转发。</p>
     <h3>订阅事件</h3><code v-for="event in config.webhook_events" :key="event" class="event">{{event}}</code>
     <h3>价格与订单</h3><p>金额取自「价格与套餐」中的单次打印套餐（USD，至少 $0.50）。只有验证通过的 Stripe 付款通知才会将订单标记为已付款。</p><p>返回或关闭收银台不会取消订单，可在「我的订单」继续付款。支付链接 24 小时后过期。</p><p>关闭开关只停止新订单使用 Stripe，已创建订单仍可完成付款。打印设备仍为演示，Stripe 订单不会进入模拟打印或模拟退款流程。</p>
     <router-link to="/plans">管理壳单价格 →</router-link>
    </aside>
   </div>
  </template>
 </section>
</template>
<style scoped>
.stripe-layout{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:22px}.stripe-form,.setup-guide{padding:26px}.notice{margin-bottom:20px}.switch-note{font-size:12px;color:#71857b;margin-left:12px}.help{font-size:12px;color:#71857b;line-height:1.8;margin:8px 0 16px;width:100%}.credentials{border-top:1px solid #e6ece7;padding-top:18px;margin-top:18px}.stripe-layout h2{font-size:17px;margin:0 0 20px}.setup-guide h3{font-size:13px;margin-top:24px}.setup-guide p,.setup-guide li{font-size:13px;color:#60766a;line-height:1.9}.setup-guide ol{padding-left:20px}.setup-guide a{color:#196967}.webhook{display:block;background:#f1f6f2;padding:12px;overflow-wrap:anywhere;font-size:12px}.event{display:block;font-size:11px;overflow-wrap:anywhere;line-height:2}@media(max-width:1050px){.stripe-layout{grid-template-columns:1fr}}
</style>
