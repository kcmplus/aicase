<script setup>
import {computed,onMounted,onBeforeUnmount,reactive,ref} from 'vue';
import {onBeforeRouteLeave} from 'vue-router';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api} from './api.js';
const rows=reactive([]),loading=ref(false),error=ref('');
const names={google:'Google',facebook:'Facebook'};
const edited=row=>row.saved&&(JSON.stringify(row.form)!==JSON.stringify(row.saved)||row.secret||row.clear);
const dirty=computed(()=>rows.some(edited));
function accept(row,data){row.data=data;row.form={enabled:data.enabled,client_id:data.client_id,site_origin:data.site_origin,graph_version:data.graph_version};row.saved={...row.form};row.secret='';row.clear=false;}
async function discard(){if(rows.some(r=>r.busy))return false;if(!dirty.value)return true;try{await ElMessageBox.confirm('有未保存的第三方登录配置，是否丢弃？','未保存的配置');return true;}catch{return false;}}
async function load(){if(!await discard())return;loading.value=true;error.value='';try{const data=await Promise.all(['google','facebook'].map(p=>api('admin/social-login/'+p+'/')));rows.splice(0,rows.length,...data.map(d=>{const r={provider:d.provider,busy:false,error:''};accept(r,d);return r;}));}catch(e){error.value=e.message;}finally{loading.value=false;}}
async function save(row){if(row.busy)return;row.busy=true;row.error='';try{accept(row,await api('admin/social-login/'+row.provider+'/',{method:'PATCH',body:{...row.form,revision:row.data.revision,secret:row.secret,clear_secret:row.clear}}));ElMessage.success(names[row.provider]+' 登录配置已保存');}catch(e){row.error=e.message;}finally{row.busy=false;}}
const callback=row=>row.form.site_origin?row.form.site_origin.replace(/\/$/,'')+'/api/v1/store/customer/social/'+row.provider+'/callback/':'';
async function copy(row){try{await navigator.clipboard.writeText(callback(row));ElMessage.success('回调地址已复制');}catch{ElMessage.info('请选中回调地址手动复制');}}
function beforeUnload(e){if(dirty.value){e.preventDefault();e.returnValue='';}}
onMounted(()=>{load();window.addEventListener('beforeunload',beforeUnload);});
onBeforeUnmount(()=>{rows.forEach(r=>r.secret='');window.removeEventListener('beforeunload',beforeUnload);});
onBeforeRouteLeave(discard);
</script>
<template>
 <section class="social-settings">
  <div class="page-heading"><div><h2>第三方登录</h2><p class="muted">独立开启 Google 或 Facebook。首次注册沿用上方赠送次数，已有账号不会重复赠送。</p></div><el-button :loading="loading" @click="load">刷新登录配置</el-button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
  <div class="social-settings-grid" v-loading="loading">
   <el-form v-for="row in rows" :key="row.provider" class="panel" label-position="top" :disabled="row.busy" @submit.prevent="save(row)">
    <h3>{{names[row.provider]}} 登录 <el-tag :type="row.data.available?'success':'info'">{{row.data.available?'已启用':'未启用'}}</el-tag></h3>
    <el-alert v-if="row.error" :title="row.error" type="error" :closable="false"/>
    <el-form-item label="启用登录按钮"><el-switch v-model="row.form.enabled"/><p class="help">保存完整配置并开启后，客户页面才会显示。</p></el-form-item>
    <el-form-item label="客户网站域名"><el-input v-model="row.form.site_origin" placeholder="https://aicase.chunpat.cc"/><p class="help">填写客户实际访问的 HTTPS 域名，不带 /admin、路径或参数。</p></el-form-item>
    <el-form-item :label="row.provider==='google'?'Google Client ID':'Facebook App ID'"><el-input v-model="row.form.client_id" autocomplete="off" maxlength="255"/></el-form-item>
    <el-form-item :label="row.provider==='google'?'Google Client Secret':'Facebook App Secret'"><el-input v-model="row.secret" type="password" autocomplete="new-password" maxlength="2048" :disabled="row.clear||!row.data.encryption_ready" :placeholder="row.data.has_secret?'已加密保存，留空保留':'填写应用密钥'"/><p class="help">仅加密保存在服务器，不会返回客户页面。更换应用 ID 时请同时更换密钥。</p></el-form-item>
    <el-checkbox v-if="row.data.has_secret" v-model="row.clear">保存时清除密钥（请先关闭登录）</el-checkbox>
    <el-form-item v-if="row.provider==='facebook'" label="Graph API 版本"><el-input v-model="row.form.graph_version" placeholder="v27.0"/><p class="help">与 Meta 应用支持的版本一致。</p></el-form-item>
    <el-form-item label="授权回调地址"><el-input :model-value="callback(row)" readonly placeholder="先填写客户网站域名"><template #append><el-button :disabled="!callback(row)" @click="copy(row)">复制</el-button></template></el-input></el-form-item>
    <p v-if="row.provider==='google'" class="help">在 <a href="https://console.cloud.google.com/auth/clients" target="_blank" rel="noopener noreferrer">Google Auth Platform</a> 创建“Web 应用”客户端，将上面的完整地址填入“已获授权的重定向 URI”。网站来源填写同一域名，完成品牌、受众及测试用户设置。</p>
    <p v-else class="help">在 <a href="https://developers.facebook.com/apps/" target="_blank" rel="noopener noreferrer">Meta for Developers</a> 配置 Facebook Login，将上面的地址加入“有效 OAuth 重定向 URI”。开发模式仅应用角色／测试用户可用，对公众开放前完成平台要求的审核及上线。</p>
    <p class="help">首次 Facebook 登录或 Google 非托管邮箱，需要再验证一次邮箱才能关联现有账号。请先配置并测试邮箱发送。</p>
    <el-alert v-if="!row.data.encryption_ready" title="服务端加密配置不可用，暂不能保存密钥或开启登录。" type="error" :closable="false"/>
    <el-button type="primary" native-type="submit" :loading="row.busy" :disabled="!edited(row)">保存 {{names[row.provider]}} 配置</el-button>
    <p class="help">保存成功只表示配置已保存。请用实际测试账号完成一次授权，核对回到网站后的登录状态。</p>
   </el-form>
  </div>
 </section>
</template>
<style scoped>
.social-settings{margin-top:32px}.social-settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.panel{padding:26px;min-width:0}.help{font-size:13px;line-height:1.7;color:#62736b}.help a{color:#196967}.el-checkbox{margin-bottom:18px}h3{display:flex;justify-content:space-between;align-items:center;margin:0 0 22px}.el-alert{margin-bottom:18px}@media(max-width:1000px){.social-settings-grid{grid-template-columns:1fr}}
</style>
