<script setup>
import {imageAttributes} from '../../storefront/image-view.js';
import {api} from './api.js';
import {composePrompt} from './prompt-templates.js';
import {ref} from 'vue';
import {ElMessage,ElMessageBox} from 'element-plus';
const props=defineProps({modelValue:{type:Array,default:()=>[]},styles:{type:Array,default:()=>[]},models:{type:Array,default:()=>[]},disabled:Boolean});
const emit=defineEmits(['update:modelValue','busy','error']);
const uploading=ref(false);
function update(index,key,value){emit('update:modelValue',props.modelValue.map((row,i)=>i===index?{...row,[key]:value}:row));}
function add(){emit('update:modelValue',[...props.modelValue,{style:null,image_path:'',phone_model:null,prompt:''}]);}
function remove(index){emit('update:modelValue',props.modelValue.filter((_,i)=>i!==index));}
function optionsFor(result,key,options,name){return options.some(item=>item.id===result[key])||!result[key]?options:[...options,{id:result[key],name:result[name]||'已关联记录',active:false}];}
async function upload(event,index){
 const file=event.target.files?.[0];if(!file)return;
 uploading.value=true;emit('busy',true);emit('error','');
 try{const body=new FormData();body.append('file',file);const result=await api('admin/uploads/',{method:'POST',body});update(index,'image_path',result.path);}
 catch(error){emit('error',error.message);}finally{uploading.value=false;emit('busy',false);event.target.value='';}
}
async function fill(index){
 const row=props.modelValue[index],style=props.styles.find(item=>item.id===row.style),model=props.models.find(item=>item.id===row.phone_model);
 if(!style?.prompt?.trim()&&!model?.adaptation_prompt?.trim()){ElMessage.warning('所选风格和机型还没有可填入的提示词，请先到相应页签设置。');return;}
 if(row.prompt?.trim()){try{await ElMessageBox.confirm('这会替换当前案例的提示词草稿，保存案例后才生效。','填入通用提示词',{confirmButtonText:'替换草稿',cancelButtonText:'取消'});}catch{return;}}
 update(index,'prompt',composePrompt(style,model));
 if(row.phone_model&&!model?.adaptation_prompt?.trim())ElMessage.warning('已填入风格提示词；该机型尚未设置适配规则，请补充后再测试。');
}
async function copy(text){try{await navigator.clipboard.writeText(text);ElMessage.success('已复制案例提示词');}catch{ElMessage.warning('复制失败，请在文本框中选中内容复制。');}}
</script>

<template>
 <div class="case-effects">
  <p class="muted">每个效果单独保存风格、机型和完整提示词。通用模板更新后，案例提示词会保留；需要时可以重新填入。</p>
  <section v-for="(result,index) in modelValue" :key="index" class="recipe-editor">
   <div class="recipe-heading"><h3>效果 {{index+1}} · {{styles.find(s=>s.id===result.style)?.name||result.style_name||'新效果'}}</h3><el-button v-if="!disabled" link type="danger" :disabled="uploading" :aria-label="'移除效果 '+(index+1)" @click="remove(index)">移除</el-button></div>
   <div class="recipe-top">
    <div class="recipe-image"><img v-if="result.image_path" v-bind="imageAttributes(result.image_path,{sizes:'180px'})" :alt="'效果 '+(index+1)+' 预览'"/><div v-else class="effect-placeholder">上传效果图</div><label v-if="!disabled" class="upload-button">{{uploading?'正在上传…':'上传效果图'}}<input type="file" accept="image/png,image/jpeg,image/webp" :disabled="uploading" @change="upload($event,index)"/></label></div>
    <div class="recipe-fields">
     <label>关联风格</label><el-select :model-value="result.style" :aria-label="'效果 '+(index+1)+' 的风格'" placeholder="选择风格" :disabled="disabled||uploading||!styles.length" @update:model-value="update(index,'style',$event)"><el-option v-for="style in optionsFor(result,'style',styles,'style_name')" :key="style.id" :value="style.id" :label="style.name+(style.active?'':'（已停用或无查看权限）')" :disabled="modelValue.some((row,i)=>i!==index&&row.style===style.id)"/></el-select>
     <label>适配机型</label><el-select :model-value="result.phone_model" :aria-label="'效果 '+(index+1)+' 的机型'" clearable placeholder="通用 / 尚未指定机型" :disabled="disabled||uploading||!models.length" @update:model-value="update(index,'phone_model',$event||null)"><el-option v-for="model in optionsFor(result,'phone_model',models,'phone_model_name')" :key="model.id" :value="model.id" :label="model.name+(model.active?'':'（已停用或无查看权限）')"/></el-select>
     <label>效果图路径</label><el-input :model-value="result.image_path" :aria-label="'效果 '+(index+1)+' 的图片路径'" placeholder="/assets/... 或上传效果图" :disabled="disabled||uploading" @update:model-value="update(index,'image_path',$event)"/>
     <p class="muted recipe-hint">选择机型不会自动裁切效果图，也不代表打印模板已经校准。</p>
    </div>
   </div>
   <div class="recipe-prompt-heading"><label :for="'case-prompt-'+index">本案例的完整提示词</label><el-button v-if="!disabled" link type="primary" :disabled="uploading" @click="fill(index)">从风格与机型填入</el-button></div>
   <el-input :id="'case-prompt-'+index" :model-value="result.prompt||''" :aria-label="'效果 '+(index+1)+' 的完整提示词'" type="textarea" :rows="9" maxlength="8000" show-word-limit :readonly="disabled" :disabled="uploading" placeholder="记录这张效果图使用的完整提示词，也可以从通用风格与机型规则填入后修改。" @update:model-value="update(index,'prompt',$event)"/>
   <el-button class="copy-recipe" :disabled="!result.prompt?.trim()" @click="copy(result.prompt)">复制此效果提示词</el-button>
  </section>
  <el-button v-if="!disabled" :disabled="uploading||modelValue.length>=30||!styles.length" @click="add">＋ 添加风格效果</el-button>
 </div>
</template>

<style scoped>
.case-effects{width:100%}.case-effects>.muted,.recipe-hint{font-size:12px;line-height:1.8}.recipe-editor{border:1px solid #e1e8e3;border-radius:12px;padding:22px;margin:18px 0;background:#fff}.recipe-heading,.recipe-prompt-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}.recipe-heading h3{font-size:15px;margin:0}.recipe-top{display:grid;grid-template-columns:160px 1fr;gap:24px;margin-bottom:22px}.recipe-image img,.effect-placeholder{display:block;width:160px;height:260px;object-fit:contain;border-radius:8px;background:#f1f4ef}.effect-placeholder{display:grid;place-items:center;color:#87948a}.recipe-image .upload-button{margin-top:10px}.recipe-fields{display:grid;gap:9px;align-content:start}.recipe-fields label,.recipe-prompt-heading label{font-size:12px;color:#52685b}.recipe-hint{margin:0}.copy-recipe{margin-top:14px}.case-effects :deep(textarea){font-size:12px;line-height:1.8}.recipe-fields .el-select{width:100%}@media(max-width:600px){.recipe-top{grid-template-columns:1fr}.recipe-image{display:flex;align-items:center;gap:16px}.recipe-image img,.effect-placeholder{width:115px;height:190px}.recipe-editor{padding:15px}.recipe-prompt-heading{align-items:start;flex-direction:column}}
</style>
