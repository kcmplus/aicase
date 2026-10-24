<script setup>
import {ref} from 'vue';
import {useRouter} from 'vue-router';
import {api,session} from './api.js';
const router=useRouter(),username=ref(''),password=ref(''),busy=ref(false),error=ref('');
async function submit(){
  busy.value=true;error.value='';
  try{const result=await api('auth/login/',{method:'POST',body:{username:username.value,password:password.value}});session.user=result.user;session.ready=true;await router.push('/');}
  catch(e){error.value=e.message;}finally{busy.value=false;}
}
</script>
<template><main class="login-page"><section class="login-intro"><a class="wordmark" href="/">POPOMO<span>™</span></a><div><p class="eyebrow">THE MANAGEMENT STUDIO</p><h1>创意背后，<br>井然有序。</h1><p>从每一个图案，到每一次打印。<br>在这里管理 POPOMO 的日常。</p></div><small>POPOMO · Pick. Scan. Print.</small></section><section class="login-side"><form class="login-form" @submit.prevent="submit"><p class="eyebrow">WELCOME BACK</p><h2>登录管理工作台</h2><p class="muted">使用管理员为你开通的账号。</p><el-alert v-if="error" :title="error" type="error" :closable="false" show-icon/><label for="username">登录账号</label><el-input id="username" v-model="username" size="large" autocomplete="username" required placeholder="请输入账号"/><label for="password">密码</label><el-input id="password" v-model="password" type="password" size="large" autocomplete="current-password" show-password required placeholder="请输入密码"/><el-button native-type="submit" type="primary" size="large" :loading="busy">登录工作台</el-button><small>仅供授权人员使用 · 访问与修改受权限控制</small></form></section></main></template>
