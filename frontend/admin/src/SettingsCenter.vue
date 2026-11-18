<script setup>
import {computed,ref} from 'vue';
import {useRoute} from 'vue-router';
import * as icons from '@element-plus/icons-vue';
import {session} from './api.js';
import {visibleSettings} from './settings-navigation.js';
const route=useRoute(),search=ref('');
const items=computed(()=>visibleSettings(session.user));
const home=computed(()=>route.path.replace(/\/$/,'')==='/settings');
const groups=computed(()=>['客户与收款','服务连接','管理与安全'].map(title=>({title,items:items.value.filter(item=>item.group===title&&`${item.title} ${item.description}`.toLowerCase().includes(search.value.trim().toLowerCase()))})).filter(group=>group.items.length));
const active=item=>route.path===item.path||route.path.startsWith(item.path+'/');
</script>
<template>
 <section class="settings-center">
  <template v-if="home">
   <div class="page-heading"><div><p class="eyebrow">SETTINGS</p><h1>设置<span class="greeting-dot">.</span></h1><p class="muted">登录、收款、服务连接和后台权限，集中在这里管理。</p></div><el-input v-model="search" clearable class="settings-search" placeholder="搜索设置，如 Google、支付、设备" aria-label="搜索设置"/></div>
   <section v-for="group in groups" :key="group.title" class="settings-group"><h2>{{group.title}}</h2><div class="settings-grid"><router-link v-for="item in group.items" :key="item.key" :to="item.path" class="settings-card"><el-icon><component :is="icons[item.icon]"/></el-icon><div><h3>{{item.title}}</h3><p>{{item.description}}</p></div><span aria-hidden="true">→</span></router-link></div></section>
   <el-empty v-if="!groups.length" description="没有匹配的设置，请换个关键词。"/>
  </template>
  <template v-else>
   <nav class="settings-nav" aria-label="设置分类"><router-link class="settings-home" to="/settings">← 全部设置</router-link><router-link v-for="item in items" :key="item.key" :to="item.path" :class="{active:active(item)}" :aria-current="active(item)?'page':undefined">{{item.title}}</router-link></nav>
   <router-view :key="route.meta.settingsSection||route.path"/>
  </template>
 </section>
</template>
<style scoped>
.settings-search{max-width:340px}.settings-group{margin:28px 0 34px}.settings-group h2{font-size:14px;color:#63766b;margin-bottom:14px}.settings-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.settings-card{display:flex;align-items:center;gap:16px;padding:24px;background:#fff;border:1px solid #e0e8e2;border-radius:16px;text-decoration:none;color:#254d40;min-width:0}.settings-card:hover{border-color:#6b9d88;box-shadow:0 5px 18px #264c390c}.settings-card>.el-icon{font-size:24px;flex-shrink:0}.settings-card>div{flex:1;min-width:0}.settings-card h3{font-size:16px;margin:0 0 9px}.settings-card p{font-size:12px;color:#728077;line-height:1.7;margin:0}.settings-nav{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 28px;padding-bottom:16px;border-bottom:1px solid #dfe8e1}.settings-nav a{padding:10px 12px;text-decoration:none;color:#60766b;border-radius:8px;font-size:13px}.settings-nav a.active{background:#e3efea;color:#205e48;font-weight:600}.settings-nav a:hover{background:#edf4ef}.settings-nav .settings-home{font-weight:600}.settings-card:focus-visible,.settings-nav a:focus-visible{outline:2px solid #196967;outline-offset:3px}@media(max-width:1150px){.settings-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.settings-grid{grid-template-columns:1fr}.settings-center .page-heading{align-items:stretch;flex-direction:column}.settings-search{max-width:none}.settings-card{padding:20px}.settings-nav{gap:2px}.settings-nav a{padding:9px;font-size:12px}}
</style>
