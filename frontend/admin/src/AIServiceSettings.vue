<script setup>
import {computed,onMounted,onBeforeUnmount,ref} from 'vue';
import {onBeforeRouteLeave} from 'vue-router';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api} from './api.js';

const config=ref(null),model=ref(''),keyInput=ref(''),loading=ref(false),saving=ref(false),checking=ref(false),error=ref('');
const busy=computed(()=>loading.value||saving.value||checking.value);
const dirty=computed(()=>Boolean(config.value)&&(model.value!==config.value.model_name||Boolean(keyInput.value)));
const checkLabels={untested:'尚未检查',ok:'连接检查通过',error:'连接检查未通过'};
function accept(data){config.value=data;model.value=data.model_name;keyInput.value='';}
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
    const body={revision:config.value.revision,model_name:model.value};
    if(keyInput.value.trim())body.api_key=keyInput.value.trim();
    accept(await api('admin/ai-service/',{method:'PATCH',body}));
    ElMessage.success('生图配置已保存');
  }catch(e){error.value=e.message;}finally{saving.value=false;}
}
async function clearKey(){
  if(!config.value?.has_api_key||busy.value)return;
  try{await ElMessageBox.confirm('清除后需要重新填写 API Key 才能连接 OpenAI。','清除已保存的密钥',{confirmButtonText:'清除密钥',cancelButtonText:'取消',type:'warning'});}catch{return;}
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
    <div class="page-heading"><div><p class="eyebrow">AI CONNECTION</p><h1>AI 生图配置<span class="greeting-dot">.</span></h1><p class="muted">设置 OpenAI API Key 与图像模型。仅超级管理员可以管理。</p></div><el-button :disabled="busy" @click="refresh">刷新配置</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="form-alert"/>
    <el-skeleton v-if="loading&&!config" :rows="7" animated/>
    <template v-if="config">
      <el-alert v-if="!config.encryption_ready" title="服务端加密存储尚未就绪，请联系维护人员完成配置后再保存密钥。" type="error" :closable="false" show-icon class="form-alert"/>
      <div class="service-layout">
        <section class="panel service-form">
          <div class="service-heading"><h2>OpenAI 服务</h2><el-tag :type="config.has_api_key?'success':'info'">{{config.has_api_key?'密钥已配置':'待填写密钥'}}</el-tag></div>
          <el-form label-position="top" @submit.prevent="save">
            <el-form-item label="服务地址"><div class="service-url">{{config.base_url}}</div></el-form-item>
            <el-form-item label="图像模型"><el-select v-model="model" aria-label="图像模型" :disabled="busy"><el-option v-for="value in config.available_models" :key="value" :value="value" :label="value"/></el-select><p class="field-help">选择你的 OpenAI 项目可使用的图像模型。</p></el-form-item>
            <el-form-item label="OpenAI API Key" for="openai-api-key">
              <div class="key-field"><div v-if="config.has_api_key" class="saved-key">已加密保存 <code>{{config.masked_api_key}}</code><span>保存后不回显完整密钥</span></div>
              <el-input id="openai-api-key" v-model="keyInput" type="password" :placeholder="config.has_api_key?'留空保留原密钥；填写新 Key 可替换':'粘贴 OpenAI API Key'" autocomplete="new-password" :spellcheck="false" maxlength="1024" :disabled="busy||!config.encryption_ready"/>
              <p class="field-help">请填写在 <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer">OpenAI 平台</a>创建的 API Key。密钥仅保存在服务端，不会发送给用户端。</p></div>
            </el-form-item>
            <div class="service-actions"><el-button type="primary" :loading="saving" :disabled="busy||!dirty||(!config.encryption_ready&&Boolean(keyInput))" @click="save">保存配置</el-button><el-button :loading="checking" :disabled="busy||dirty||!config.has_api_key||!config.encryption_ready" @click="checkConnection">检查连接</el-button><el-button v-if="config.has_api_key" link type="danger" :disabled="busy||dirty" @click="clearKey">清除密钥</el-button></div>
            <p v-if="dirty" class="pending-note">有未保存的修改，保存后才能检查连接。</p>
          </el-form>
        </section>
        <aside class="panel service-status">
          <h2>连接状态</h2><el-tag :type="config.last_check_status==='ok'?'success':config.last_check_status==='error'?'warning':'info'">{{checkLabels[config.last_check_status]||'尚未检查'}}</el-tag>
          <p>{{config.last_check_message||'填写并保存 API Key 后，可检查服务器与 OpenAI 的连接。'}}</p>
          <dl><dt>密钥更新时间</dt><dd>{{formatDate(config.key_updated_at)}}</dd><dt>上次检查</dt><dd>{{formatDate(config.last_check_at)}}</dd></dl>
          <p class="check-note">检查只读取模型信息，不生成图片；通过检查不代表已验证图片生成权限或账户余额。</p>
        </aside>
      </div>
      <el-alert title="本页用于保存服务配置。前台真实生图流程尚未接入，保存 Key 不会立即生成图片或改变现有案例。" type="info" :closable="false" show-icon/>
      <router-link to="/ai-prompts" class="prompt-link">管理 AI 案例与提示词 →</router-link>
    </template>
  </section>
</template>

<style scoped>
.service-layout{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(250px,1fr);gap:22px;margin-bottom:22px}.service-form,.service-status{padding:26px}.service-heading{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:26px}.service-layout h2{font-size:17px;margin:0 0 20px}.service-heading h2{margin:0}.service-url{background:#f4f7f5;border:1px solid #e1e8e4;border-radius:7px;padding:10px 13px;width:100%;font-size:13px;overflow-wrap:anywhere}.key-field{width:100%}.field-help{font-size:11px;line-height:1.8;color:#7b8887;margin:8px 0 0}.field-help a{color:#196967;text-decoration:underline;text-underline-offset:3px}.saved-key{display:flex;gap:9px;align-items:center;flex-wrap:wrap;font-size:12px;margin-bottom:12px;color:#41775f}.saved-key code{background:#edf5ef;padding:2px 7px;border-radius:5px}.saved-key span{font-size:10px;color:#8a968e}.service-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.service-actions .el-button+.el-button{margin-left:0}.service-status p{font-size:13px;line-height:1.8;color:#71857b;margin-top:16px}.service-status dl{margin:25px 0;font-size:12px}.service-status dt{color:#99a69d;margin-top:16px}.service-status dd{margin:7px 0 0;color:#486355}.service-status .check-note{font-size:11px;border-top:1px solid #e6ece7;padding-top:18px}.pending-note{color:#987532;font-size:12px;margin:16px 0 0}.prompt-link{display:inline-block;color:#196967;font-size:13px;margin-top:20px}.service-form :deep(.el-select){width:100%}@media(max-width:1050px){.service-layout{grid-template-columns:1fr}.service-form,.service-status{padding:20px}}
</style>
