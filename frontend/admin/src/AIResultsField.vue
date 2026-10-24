<script setup>
import {api} from './api.js';
import {ref} from 'vue';
const props=defineProps({modelValue:{type:Array,default:()=>[]},styles:{type:Array,default:()=>[]},disabled:Boolean});
const emit=defineEmits(['update:modelValue','busy','error']);
const uploading=ref(false);
function update(index,key,value){emit('update:modelValue',props.modelValue.map((row,i)=>i===index?{...row,[key]:value}:row));}
function add(){emit('update:modelValue',[...props.modelValue,{style:null,image_path:''}]);}
function remove(index){emit('update:modelValue',props.modelValue.filter((_,i)=>i!==index));}
async function upload(event,index){
 const file=event.target.files?.[0];if(!file)return;
 uploading.value=true;emit('busy',true);emit('error','');
 try{const body=new FormData();body.append('file',file);const result=await api('admin/uploads/',{method:'POST',body});update(index,'image_path',result.path);}
 catch(error){emit('error',error.message);}finally{uploading.value=false;emit('busy',false);event.target.value='';}
}
</script>
<template><div class="case-effects"><p class="muted">给同一张原图添加不同风格的效果图。每种风格添加一次，前台可切换对比。</p><div v-for="(result,index) in modelValue" :key="index" class="case-effect-row"><img v-if="result.image_path" :src="result.image_path" alt="风格效果预览"/><div v-else class="effect-placeholder">效果图</div><div class="case-effect-fields"><el-select :model-value="result.style" :aria-label="'效果 '+(index+1)+' 的风格'" placeholder="选择风格" :disabled="disabled||uploading" @update:model-value="update(index,'style',$event)"><el-option v-for="style in styles" :key="style.id" :value="style.id" :label="style.name+(style.active?'':'（已停用）')" :disabled="modelValue.some((row,i)=>i!==index&&row.style===style.id)"/></el-select><el-input :model-value="result.image_path" :aria-label="'效果 '+(index+1)+' 的图片路径'" placeholder="/assets/... 或上传效果图" :disabled="disabled||uploading" @update:model-value="update(index,'image_path',$event)"/><label v-if="!disabled" class="upload-button">{{uploading?'正在上传…':'上传效果图'}}<input type="file" accept="image/png,image/jpeg,image/webp" :disabled="uploading" @change="upload($event,index)"/></label></div><el-button v-if="!disabled" link type="danger" :disabled="uploading" :aria-label="'移除效果 '+(index+1)" @click="remove(index)">移除</el-button></div><el-button v-if="!disabled" :disabled="uploading||modelValue.length>=30" @click="add">＋ 添加风格效果</el-button></div></template>
<style scoped>.case-effects{width:100%}.case-effect-row{display:flex;gap:14px;align-items:center;padding:14px 0;border-bottom:1px solid #e8ebe7;margin-bottom:14px}.case-effect-row>img,.effect-placeholder{width:76px;height:104px;object-fit:cover;border-radius:8px;flex-shrink:0}.effect-placeholder{display:grid;place-items:center;background:#f3f4f1;color:#858d82}.case-effect-fields{display:grid;gap:9px;flex:1;min-width:0}.case-effects>.muted{line-height:1.7;font-size:13px}</style>
