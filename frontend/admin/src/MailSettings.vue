<script setup>
import {computed,onMounted,onBeforeUnmount,reactive,ref} from 'vue';
import {onBeforeRouteLeave} from 'vue-router';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api} from './api.js';
const config=ref(null),busy=ref(false),error=ref(''),recipient=ref(''),result=ref('');
const form=reactive({enabled:false,host:'',port:587,security:'starttls',username:'',from_email:'',from_name:'POPOMO'});
const password=ref(''),clearPassword=ref(false),signupCredits=ref(1);
const giftDirty=computed(()=>config.value&&signupCredits.value!==config.value.signup_credits);
const mailDirty=computed(()=>config.value&&(Object.keys(form).some(k=>form[k]!==config.value[k])||password.value||clearPassword.value));
const dirty=computed(()=>mailDirty.value||giftDirty.value);
function accept(data,resetGift=true){if(resetGift)signupCredits.value=data.signup_credits;config.value=data;for(const k of Object.keys(form))form[k]=data[k];password.value='';clearPassword.value=false;result.value='';}
async function discard(){if(busy.value)return false;if(!dirty.value)return true;try{await ElMessageBox.confirm('有未保存的邮件配置，是否丢弃？','未保存的配置',{confirmButtonText:'丢弃修改',cancelButtonText:'继续编辑'});return true;}catch{return false;}}
async function load(){if(!await discard())return;busy.value=true;error.value='';try{accept(await api('admin/mail/'));}catch(e){error.value=e.message;}finally{busy.value=false;}}
async function save(){if(busy.value)return;busy.value=true;error.value='';try{accept(await api('admin/mail/',{method:'PATCH',body:{...form,revision:config.value.revision,password:password.value,clear_password:clearPassword.value}}),false);ElMessage.success('邮件配置已保存');}catch(e){error.value=e.message;}finally{busy.value=false;}}
async function test(){if(busy.value||mailDirty.value)return;busy.value=true;error.value='';result.value='';try{result.value=(await api('admin/mail/test/',{method:'POST',body:{recipient:recipient.value,revision:config.value.revision}})).detail;}catch(e){error.value=e.message;}finally{busy.value=false;}}
async function saveRegistration(){
 if(busy.value||!giftDirty.value)return;
 busy.value=true;error.value='';
 try{const data=await api('admin/registration/',{method:'PATCH',body:{revision:config.value.revision,signup_credits:signupCredits.value}});config.value=data;signupCredits.value=data.signup_credits;ElMessage.success('注册赠送设置已保存');}
 catch(e){error.value=e.message;}finally{busy.value=false;}
}
function beforeUnload(e){if(dirty.value){e.preventDefault();e.returnValue='';}}
onMounted(()=>{load();window.addEventListener('beforeunload',beforeUnload);});
onBeforeUnmount(()=>{password.value='';window.removeEventListener('beforeunload',beforeUnload);});
onBeforeRouteLeave(discard);
</script>
<template>
 <section>
  <div class="page-heading"><div><p class="eyebrow">EMAIL & ACCOUNTS</p><h1>邮件与注册<span class="greeting-dot">.</span></h1><p class="muted">邮箱验证码注册与登录，首次验证成功后赠送 AI 次数。仅超级管理员可配置。</p></div><el-button :disabled="busy" @click="load">刷新配置</el-button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="notice"/>
  <el-skeleton v-if="!config&&!error" :rows="8" animated/>
  <div v-if="config" class="mail-layout">
   <el-form class="panel mail-panel" label-position="top" :disabled="busy" @submit.prevent="save">
    <el-form-item label="启用邮箱验证码"><el-switch v-model="form.enabled"/><p class="help">关闭时暂停发送注册／登录验证码，已登录用户的额度保留。</p></el-form-item>
    <el-form-item label="SMTP 服务器"><el-input v-model="form.host" placeholder="smtp.example.com" autocomplete="off"/></el-form-item>
    <div class="mail-row"><el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535"/></el-form-item><el-form-item label="连接加密"><el-select v-model="form.security"><el-option value="starttls" label="STARTTLS（通常 587）"/><el-option value="ssl" label="SSL / TLS（通常 465）"/></el-select></el-form-item></div>
    <el-form-item label="SMTP 用户名"><el-input v-model="form.username" placeholder="通常是完整邮箱地址" autocomplete="off"/></el-form-item>
    <el-form-item label="SMTP 密码／授权码"><el-input v-model="password" type="password" autocomplete="new-password" :disabled="clearPassword||!config.encryption_ready" :placeholder="config.has_password?'已加密保存，留空保留':'填写邮箱服务商的 SMTP 授权码'" maxlength="1024"/><p class="help">凭据只加密保存在服务端，不会返回浏览器。部分邮箱需先开启 SMTP，并使用独立授权码。</p></el-form-item>
    <el-checkbox v-if="config.has_password" v-model="clearPassword">保存时清除已存授权码</el-checkbox>
    <el-form-item label="发件邮箱"><el-input v-model="form.from_email" type="email" placeholder="hello@example.com"/><p class="help">使用服务商允许的发件地址；通常与 SMTP 登录邮箱一致。</p></el-form-item>
    <el-form-item label="发件人名称"><el-input v-model="form.from_name" maxlength="100"/></el-form-item>
    <el-alert v-if="!config.encryption_ready" title="服务端加密配置不可用，请先配置 AI_CONFIG_ENCRYPTION_KEY。" type="error" :closable="false"/>
    <el-button native-type="submit" type="primary" :loading="busy" :disabled="!mailDirty">保存邮件配置</el-button><span v-if="mailDirty" class="help"> 有未保存的修改</span>
   </el-form>
   <aside class="mail-aside">
    <div class="panel mail-panel gift-panel">
     <div class="gift-heading"><span class="gift-icon" aria-hidden="true">✦</span><div><span class="gift-eyebrow">WELCOME GIFT</span><h2>注册赠送次数</h2></div><span class="gift-status">{{ config.signup_credits>0?'赠送已开启':'赠送已关闭' }}</span></div>
     <p>每个邮箱首次验证成功后，一次性领取 AI 创作次数。</p>
     <el-form label-position="top" :disabled="busy" @submit.prevent="saveRegistration">
      <el-form-item label="新账号赠送额度"><div class="gift-amount"><el-input-number v-model="signupCredits" :min="0" :max="1000" :precision="0" controls-position="right"/><span>次 / 账号</span></div></el-form-item>
      <p class="gift-hint">{{ signupCredits===0?'设为 0 时不赠送次数，顾客仍可正常注册。':'修改只对新注册账号生效，已有账号额度不变。' }}</p>
      <el-button native-type="submit" type="primary" :loading="busy" :disabled="!giftDirty||signupCredits===undefined">保存注册设置</el-button>
     </el-form>
     <div class="gift-rules">独立于月度订阅套餐 · 同一邮箱仅领取一次<br>生成失败或取消排队，会退还本次使用的次数。</div>
    </div>
    <div class="panel mail-panel">
    <h2>发送测试邮件</h2><p>先保存配置，再填写你的收件邮箱。测试按钮会实际发送一封邮件；可在启用注册前测试。</p>
    <el-form label-position="top" @submit.prevent="test"><el-form-item label="测试收件邮箱"><el-input v-model="recipient" type="email" placeholder="you@example.com" :disabled="busy"/></el-form-item><el-button native-type="submit" :disabled="busy||mailDirty||!recipient||!config.host" :loading="busy">发送测试邮件</el-button></el-form>
    <el-alert v-if="result" :title="result" type="success" :closable="false" show-icon class="mail-result"/>
    <h2 class="mail-test-heading">顾客的操作</h2><p>输入邮箱 → 收到六位验证码 → 验证后自动注册或登录 → 领取一次性 AI 次数。无需另设密码。</p><p>验证码 10 分钟有效，60 秒后可重发。验证码限次尝试，每个邮箱每小时最多发送 5 次。</p><p>用户端默认英文，中文界面发送中文验证码邮件。当前配置用于验证码和测试邮件。</p>
    </div>
   </aside>
  </div>
 </section>
</template>
<style scoped>
.mail-aside{display:grid;gap:24px;align-content:start}.gift-panel{background:linear-gradient(135deg,#f4f8ef,#fff 75%)}.gift-heading{display:flex;align-items:center;gap:12px}.gift-icon{display:grid;place-items:center;width:42px;height:42px;border-radius:13px;background:#e5efdd;color:#52713e;font-size:24px}.gift-eyebrow{font-size:10px;letter-spacing:1.6px;color:#708362}.gift-heading h2{margin:4px 0 0}.gift-status{margin-left:auto;font-size:11px;color:#526b44;white-space:nowrap}.gift-amount{display:flex;align-items:center;gap:12px;color:#70806d;font-size:13px}.gift-amount .el-input-number{width:160px}.gift-panel .gift-hint{margin:-6px 0 20px}.gift-rules{margin-top:24px;padding-top:18px;border-top:1px solid #e4ebdd;font-size:12px;line-height:1.9;color:#7b8675}.mail-layout{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(280px,1fr);gap:24px}.mail-panel{padding:26px}.notice{margin-bottom:20px}.mail-row{display:grid;grid-template-columns:150px 1fr;gap:20px}.help,.mail-panel p{font-size:13px;line-height:1.8;color:#6a7e71}.mail-panel h2{font-size:17px;margin-top:0}.mail-panel .mail-test-heading{margin-top:34px}.mail-result{margin-top:18px}.mail-panel a{font-size:13px;color:#196967}.mail-panel .el-checkbox{margin-bottom:18px}@media(max-width:1050px){.mail-layout{grid-template-columns:1fr}}@media(max-width:500px){.mail-row{grid-template-columns:1fr}}
</style>
