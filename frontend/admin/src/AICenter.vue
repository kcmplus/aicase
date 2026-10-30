<script setup>
import {computed} from 'vue';
import {useRoute} from 'vue-router';
import {can,session} from './api.js';
import {viewPermissionsFor} from './resources.js';

const route=useRoute();
const tabs=computed(()=>[
 {path:'/ai/prompts',label:'内容管理',visible:viewPermissionsFor('ai-prompts').some(can)},
 {path:'/ai/service',label:'生图配置',visible:session.user?.is_superuser},
 {path:'/ai/usage',label:'统计与日志',visible:session.user?.is_superuser},
].filter(tab=>tab.visible));
</script>

<template>
 <section class="ai-center">
  <div class="page-heading"><div><p class="eyebrow">AI CENTER</p><h1>AI 中心<span class="greeting-dot">.</span></h1><p class="muted">从案例与提示词，到生图服务、调用记录和成本统计，统一管理。</p></div></div>
  <nav class="ai-center-tabs" aria-label="AI 中心功能"><router-link v-for="tab in tabs" :key="tab.path" :to="tab.path" :class="{active:route.path===tab.path}" :aria-current="route.path===tab.path?'page':undefined">{{tab.label}}</router-link></nav>
  <router-view/>
 </section>
</template>

<style scoped>
.ai-center-tabs{display:flex;gap:6px;padding:6px;margin-bottom:28px;background:#eaf0ed;border:1px solid #dee8e1;border-radius:12px;width:fit-content;max-width:100%;flex-wrap:wrap}.ai-center-tabs a{display:flex;align-items:center;justify-content:center;min-height:42px;padding:10px 24px;border-radius:8px;color:#6d8177;font-size:14px;text-decoration:none;transition:background .15s,color .15s}.ai-center-tabs a:hover{background:#f5f8f5;color:#285c49}.ai-center-tabs a.active{background:#fff;color:#21645c;font-weight:600;box-shadow:0 2px 6px #264c3910}.ai-center-tabs a:focus-visible{outline:2px solid #196967;outline-offset:2px}.ai-center :deep(.ai-section-heading){margin-bottom:22px}.ai-center :deep(.ai-section-heading h2){font-size:21px;font-weight:600;margin:0 0 9px;color:#254d40}.ai-center :deep(.ai-section-heading .muted){font-size:12px;line-height:1.8}@media(max-width:650px){.ai-center-tabs{width:100%;gap:2px;padding:4px;box-sizing:border-box}.ai-center-tabs a{flex:1;padding:9px 8px;font-size:13px;white-space:nowrap}.ai-center :deep(.ai-section-heading h2){font-size:19px}}@media(prefers-reduced-motion:reduce){.ai-center-tabs a{transition:none}}
</style>
