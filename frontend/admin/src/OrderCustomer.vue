<script setup>
import {can} from './api.js';
defineProps({customerId:String,email:String});
</script>
<template>
 <div class="order-customer">
  <router-link v-if="customerId&&can('management_api.view_customer')" :to="{path:'/customers',query:{customer:customerId}}">
   <span>{{email||'注册用户'}}</span><small>查看用户 →</small>
  </router-link>
  <template v-else><span>{{email||'未填写'}}</span><small>{{customerId?'已关联注册用户':'未关联用户'}}</small></template>
 </div>
</template>
<style scoped>
.order-customer{overflow-wrap:anywhere;line-height:1.6}.order-customer a{color:#216059;text-decoration:none}.order-customer a:hover span{text-decoration:underline}.order-customer small{display:block;font-size:11px;color:#718174}.order-customer a small{color:inherit}
</style>
