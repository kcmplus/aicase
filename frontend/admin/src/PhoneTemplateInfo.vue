<script setup>
import {computed} from 'vue';
import {phoneTemplates} from '../../storefront/phone-templates.js';
const props=defineProps({model:{type:String,default:''}});
const templates=computed(()=>phoneTemplates.filter(t=>!props.model||t.model===props.model));
</script>
<template>
 <section v-if="templates.length" class="phone-template-info" aria-label="已接入的机型模板">
  <p class="template-help">已接入供应商底图，用户端按机型预览并导出 300 DPI 样片。打印范围由底图提取，出血、偏移和设备接口尚待确认。</p>
  <div class="template-grid">
   <article v-for="item in templates" :key="item.id" class="template-card">
    <div class="template-images"><figure><img :src="item.overlay" :alt="item.model+' 供应商底图'"/><figcaption>供应商底图</figcaption></figure><figure><span class="mask-preview" :style="{aspectRatio:item.printWidth+'/'+item.printHeight,maskImage:`url(${item.mask})`,WebkitMaskImage:`url(${item.mask})`}"></span><figcaption>打印范围</figcaption></figure></div>
    <div><h3>{{item.model}}</h3><code>{{item.id}}</code><p>{{item.printWidth}} × {{item.printHeight}} px · 300 DPI</p><small>{{item.sizeEvidence==='vendor-print-sample'?'画布尺寸已与供应商样图核对':'画布尺寸按底图分辨率推算，待确认'}}</small><p class="pending">待打样校准 · 未连接打印设备</p></div>
   </article>
  </div>
 </section>
</template>
<style scoped>
.phone-template-info{margin:16px 0 24px}.template-help{font-size:12px;color:#647875;line-height:1.8;margin-bottom:14px}.template-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px}.template-card{display:flex;align-items:center;gap:18px;padding:18px;border:1px solid #dce5e2;border-radius:12px;background:#f8faf9}.template-images{display:flex;gap:12px;flex-shrink:0}.template-images figure{margin:0;text-align:center}.template-images img,.mask-preview{display:block;width:53px;height:auto;max-width:100%}.mask-preview{background:#368e87;mask-size:100% 100%;-webkit-mask-size:100% 100%;mask-mode:alpha}.template-images figcaption{font-size:9px;color:#6c817b;margin-top:8px}.template-card h3{font-size:16px;margin:0 0 6px}.template-card code{font-size:10px;color:#637772}.template-card p{font-size:11px;line-height:1.6;margin:6px 0}.template-card small{font-size:10px;color:#6c817b}.template-card .pending{color:#9a732b}
</style>
