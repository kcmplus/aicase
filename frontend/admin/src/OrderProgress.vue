<script setup>
import {computed} from 'vue';
import {progressPanel,progressPaymentText} from '../../storefront/order-progress.js';
import '../../storefront/order-progress.css';
const props=defineProps({progress:Object});
const html=computed(()=>progressPanel(props.progress,{lang:'zh-CN'}));
</script>
<template><div><p class="muted">付款状态：{{progressPaymentText(progress,'zh-CN')}}</p><div v-html="html"></div></div></template>
