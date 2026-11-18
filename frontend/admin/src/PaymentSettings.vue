<script setup>
import {useRoute} from 'vue-router';
const route=useRoute();
const channels=[{path:'/settings/payments/airwallex',label:'Airwallex'},{path:'/settings/payments/stripe',label:'Stripe'}];
</script>
<template>
 <section class="payment-settings">
  <div class="page-heading"><div><p class="eyebrow">PAYMENTS</p><h1>支付配置<span class="greeting-dot">.</span></h1><p class="muted">统一管理支付渠道及测试、正式环境。启用渠道后，新订单使用该渠道，已有订单保留原支付方式。</p></div></div>
  <nav class="payment-tabs" aria-label="支付渠道"><router-link v-for="channel in channels" :key="channel.path" :to="channel.path" :class="{active:route.path===channel.path}" :aria-current="route.path===channel.path?'page':undefined">{{channel.label}}</router-link></nav>
  <router-view/>
 </section>
</template>
<style scoped>
.payment-tabs{display:flex;gap:6px;padding:6px;margin-bottom:28px;background:#eaf0ed;border:1px solid #dee8e1;border-radius:12px;width:fit-content;max-width:100%;flex-wrap:wrap}.payment-tabs a{display:flex;align-items:center;justify-content:center;min-height:42px;padding:10px 24px;border-radius:8px;color:#6d8177;font-size:14px;text-decoration:none}.payment-tabs a:hover{background:#f5f8f5;color:#285c49}.payment-tabs a.active{background:#fff;color:#21645c;font-weight:600;box-shadow:0 2px 6px #264c3910}.payment-tabs a:focus-visible{outline:2px solid #196967;outline-offset:2px}.payment-settings :deep(.payment-section-heading){display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:22px}.payment-settings :deep(.payment-section-heading h2){font-size:21px;font-weight:600;margin:0 0 9px;color:#254d40}.payment-settings :deep(.payment-section-heading .muted){font-size:12px;line-height:1.8}@media(max-width:650px){.payment-tabs{width:100%;box-sizing:border-box}.payment-tabs a{flex:1;padding:9px 8px}.payment-settings :deep(.payment-section-heading){align-items:flex-start}.payment-settings :deep(.payment-section-heading h2){font-size:19px}}
</style>
