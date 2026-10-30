<script setup>
import {computed,onMounted,onBeforeUnmount,ref} from 'vue';
import {onBeforeRouteLeave} from 'vue-router';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api} from './api.js';
defineProps({embedded:Boolean});

const config=ref(null),provider=ref('openai'),model=ref(''),keyInput=ref(''),loading=ref(false),saving=ref(false),checking=ref(false),error=ref('');
const busy=computed(()=>loading.value||saving.value||checking.value);
const dirty=computed(()=>Boolean(config.value)&&(provider.value!==config.value.provider||model.value!==config.value.model_name||Boolean(keyInput.value)));
const selectedProvider=computed(()=>config.value?.available_providers.find(item=>item.id===provider.value));
function changeProvider(){model.value=selectedProvider.value.model_name;keyInput.value='';}
const checkLabels={untested:'尚未检查',ok:'连接检查通过',error:'连接检查未通过'};
const renderLabels={queued:'排队中',generating:'生成中',ready:'生成成功',failed:'生成未完成',cancelled:'已取消'};
const renderErrors={credit_balance_exhausted:'OpenAI API 预付余额已用完，请检查 API 平台的计费设置。',project_spend_limit_exceeded:'此 OpenAI API 项目已达到支出上限。',organization_spend_limit_exceeded:'OpenAI API 企业组织已达到支出上限。',organization_usage_limit_exceeded:'OpenAI API 企业组织已达到获批的使用额度上限。',rate_limit_exceeded:'该模型的请求速率已达到限制，请查看 API 项目的模型限额。',slow_down:'OpenAI 暂时限制新请求，请等待后再试。',rate_limit:'OpenAI 返回 429：生图请求受到用量或计费限制，请检查该 API 项目的余额、账单及模型限额。',quota:'OpenAI API 余额不足或已达到计费上限。',credentials:'OpenAI 拒绝了当前密钥，请检查已保存的配置。',permission:'该 API 项目缺少图片生成或模型访问权限。',model:'该 API 项目无法使用此模型。',network:'连接图片服务超时或网络不可达。',content_policy:'该图片未通过生图服务的内容审核。',interrupted:'任务中断，生成次数已返还。'};
function accept(data){config.value=data;provider.value=data.provider;model.value=data.model_name;keyInput.value='';}
const formatDate=value=>value?new Date(value).toLocaleString('zh-CN'):'尚无记录';
async function confirmDiscard(){
  if(busy.value)return false;
  if(!dirty.value)return true;
  try{await ElMessageBox.confirm('配置有未保存的修改，离开后将丢弃这些修改。','未保存的配置',{confirmButtonText:'丢弃修改',cancelButtonText:'继续编辑',type:'warning'});return true;}catch{return false;}
}
async function load(){
  loading.value=true;error.value='';
  try{accept(await api('admin/ai-service/'));}catch(e){error.value=e.message;}finally{loading.value=false;}
}
async function refresh(){if(await confirmDiscard())await load();}
async function save(){
  if(!config.value||busy.value)return;
  saving.value=true;error.value='';
  try{
    const body={revision:config.value.revision,provider:provider.value,model_name:model.value};
    if(keyInput.value.trim())body.api_key=keyInput.value.trim();
    accept(await api('admin/ai-service/',{method:'PATCH',body}));
    ElMessage.success('生图配置已保存');
  }catch(e){error.value=e.message;}finally{saving.value=false;}
}
async function clearKey(){
  if(!config.value?.has_api_key||busy.value)return;
  try{await ElMessageBox.confirm('清除当前服务商的密钥后，需要重新填写才能生图。其他服务商的密钥会保留。','清除已保存的密钥',{confirmButtonText:'清除密钥',cancelButtonText:'取消',type:'warning'});}catch{return;}
  saving.value=true;error.value='';
  try{accept(await api('admin/ai-service/',{method:'PATCH',body:{revision:config.value.revision,clear_api_key:true}}));ElMessage.success('已清除保存的 API Key');}
  catch(e){error.value=e.message;}finally{saving.value=false;}
}
async function checkConnection(){
  if(!config.value?.has_api_key||dirty.value||busy.value)return;
  checking.value=true;error.value='';
  try{accept(await api('admin/ai-service/check/',{method:'POST',body:{revision:config.value.revision}}));}
  catch(e){error.value=e.message;}finally{checking.value=false;}
}
function beforeUnload(event){if(dirty.value){event.preventDefault();event.returnValue='';}}
onMounted(()=>{load();window.addEventListener('beforeunload',beforeUnload);});
onBeforeUnmount(()=>{keyInput.value='';window.removeEventListener('beforeunload',beforeUnload);});
onBeforeRouteLeave(()=>confirmDiscard());
</script>

<template>
  <section class="ai-service-page">
    <div class="page-heading" :class="{'ai-section-heading':embedded}"><div><p v-if="!embedded" class="eyebrow">AI CONNECTION</p><component :is="embedded?'h2':'h1'">AI 生图配置<span v-if="!embedded" class="greeting-dot">.</span></component><p class="muted">统一管理生图服务商、API Key 与图像模型。仅超级管理员可以管理。</p></div><el-button :disabled="busy" @click="refresh">刷新配置</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="form-alert"/>
    <el-skeleton v-if="loading&&!config" :rows="7" animated/>
    <template v-if="config">
      <el-alert v-if="!config.encryption_ready" title="服务端加密存储尚未就绪，请联系维护人员完成配置后再保存密钥。" type="error" :closable="false" show-icon class="form-alert"/>
      <div class="service-layout">
        <section class="panel service-form">
          <div class="service-heading"><h2>{{selectedProvider.label}}</h2><el-tag :type="selectedProvider.has_api_key?'success':'info'">{{selectedProvider.has_api_key?'密钥已配置':'待填写密钥'}}</el-tag></div>
          <el-form label-position="top" @submit.prevent="save">
            <el-form-item label="生图服务商"><el-select v-model="provider" aria-label="生图服务商" :disabled="busy" @change="changeProvider"><el-option v-for="item in config.available_providers" :key="item.id" :value="item.id" :label="item.label"/></el-select><p class="field-help">各服务商分别保存密钥和模型，保存后前台使用所选服务商。切换不会把原服务商的 Key 发送给其他平台。</p></el-form-item>
            <el-form-item label="服务地址"><div class="service-url">{{selectedProvider.base_url}}</div></el-form-item>
            <el-form-item label="图像模型"><el-select v-model="model" aria-label="图像模型" :disabled="busy"><el-option v-for="value in selectedProvider.models" :key="value" :value="value" :label="selectedProvider.model_labels[value]||value"/></el-select><p class="field-help">选择当前服务商账号可使用的模型。<a :href="selectedProvider.docs_url" target="_blank" rel="noopener noreferrer">查看接口文档</a><template v-if="provider==='ai778'">。TT Image 2 支持原图编辑；实际输出尺寸以服务商返回为准。</template></p></el-form-item>
            <el-form-item :label="selectedProvider.label+' API Key'" for="ai-api-key">
              <div class="key-field"><div v-if="selectedProvider.has_api_key" class="saved-key">已加密保存 <code>{{selectedProvider.masked_api_key}}</code><span>保存后不回显完整密钥</span></div>
              <el-input id="ai-api-key" v-model="keyInput" type="password" :placeholder="selectedProvider.has_api_key?'留空保留该服务商的密钥；填写新 Key 可替换':'粘贴当前服务商的 API Key'" autocomplete="new-password" :spellcheck="false" maxlength="1024" :disabled="busy||!config.encryption_ready"/>
              <p class="field-help">请填写在 <a :href="selectedProvider.console_url" target="_blank" rel="noopener noreferrer">{{selectedProvider.label}} 控制台</a>创建的 API Key。密钥仅保存在服务端，不会发送给用户端。</p></div>
            </el-form-item>
            <div class="service-actions"><el-button type="primary" :loading="saving" :disabled="busy||!dirty||(!config.encryption_ready&&Boolean(keyInput))" @click="save">保存配置</el-button><el-button :loading="checking" :disabled="busy||dirty||!config.has_api_key||!config.encryption_ready" @click="checkConnection">检查连接</el-button><el-button v-if="selectedProvider.has_api_key" link type="danger" :disabled="busy||dirty" @click="clearKey">清除密钥</el-button></div>
            <p v-if="dirty" class="pending-note">有未保存的修改，保存后才能检查连接。</p>
          </el-form>
        </section>
        <aside class="panel service-status">
          <h2>已保存配置 · {{config.provider_label}}</h2><el-tag :type="config.last_check_status==='ok'?'success':config.last_check_status==='error'?'warning':'info'">{{checkLabels[config.last_check_status]||'尚未检查'}}</el-tag>
          <p>{{config.last_check_message||'填写并保存 API Key 后，可检查服务器与当前服务商的连接。'}}</p>
          <dl><dt>密钥更新时间</dt><dd>{{formatDate(config.key_updated_at)}}</dd><dt>上次检查</dt><dd>{{formatDate(config.last_check_at)}}</dd></dl>
          <p class="check-note">检查只读取模型信息，不生成图片；通过检查不代表已验证图片生成权限或账户余额。</p>
          <template v-if="config.last_generation"><h2>最近一次生图记录</h2><el-tag :type="config.last_generation.status==='ready'?'success':config.last_generation.status==='failed'?'warning':'info'">{{renderLabels[config.last_generation.status]||config.last_generation.status}}</el-tag><p>{{config.last_generation.provider_label}} · {{config.last_generation.model}} · {{formatDate(config.last_generation.created_at)}}</p><p v-if="config.last_generation.error_message">{{(renderErrors[config.last_generation.error_code]||config.last_generation.error_message).replaceAll('OpenAI',config.last_generation.provider_label)}}</p><p class="check-note">这是上次任务的历史记录。修改服务商或 Key 后不会自动更新，请再次生成图片以验证新配置。</p></template>
        </aside>
      </div>
      <el-alert title="前台已接入真实生图：顾客确认后，服务器使用此配置处理上传照片。保存 Key 不会自动生成图片；模型读取检查不代表图片生成权限或余额已验证。" type="info" :closable="false" show-icon/>
      <router-link v-if="!embedded" to="/ai/prompts" class="prompt-link">打开 AI 管理 →</router-link>
      <router-link v-if="!embedded" to="/ai/usage" class="prompt-link" style="margin-left:24px">查看生图统计与调用日志 →</router-link>
    </template>
  </section>
</template>

<style scoped>
.service-layout{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(250px,1fr);gap:22px;margin-bottom:22px}.service-form,.service-status{padding:26px}.service-heading{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:26px}.service-layout h2{font-size:17px;margin:0 0 20px}.service-heading h2{margin:0}.service-url{background:#f4f7f5;border:1px solid #e1e8e4;border-radius:7px;padding:10px 13px;width:100%;font-size:13px;overflow-wrap:anywhere}.key-field{width:100%}.field-help{font-size:11px;line-height:1.8;color:#7b8887;margin:8px 0 0}.field-help a{color:#196967;text-decoration:underline;text-underline-offset:3px}.saved-key{display:flex;gap:9px;align-items:center;flex-wrap:wrap;font-size:12px;margin-bottom:12px;color:#41775f}.saved-key code{background:#edf5ef;padding:2px 7px;border-radius:5px}.saved-key span{font-size:10px;color:#8a968e}.service-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.service-actions .el-button+.el-button{margin-left:0}.service-status p{font-size:13px;line-height:1.8;color:#71857b;margin-top:16px}.service-status dl{margin:25px 0;font-size:12px}.service-status dt{color:#99a69d;margin-top:16px}.service-status dd{margin:7px 0 0;color:#486355}.service-status .check-note{font-size:11px;border-top:1px solid #e6ece7;padding-top:18px}.pending-note{color:#987532;font-size:12px;margin:16px 0 0}.prompt-link{display:inline-block;color:#196967;font-size:13px;margin-top:20px}.service-form :deep(.el-select){width:100%}@media(max-width:1050px){.service-layout{grid-template-columns:1fr}.service-form,.service-status{padding:20px}}
</style>
