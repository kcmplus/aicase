<script setup>
import {computed,ref,watch,onBeforeUnmount,toRaw} from 'vue';
import {ElMessage,ElMessageBox} from 'element-plus';
import {api,can} from './api.js';
const props=defineProps({model:{type:Object,required:true},disabled:Boolean});
const emit=defineEmits(['busy','dirty']);
const data=ref(null),selected=ref(0),draft=ref(null),saved=ref(''),busy=ref(false),error=ref(''),active=ref('safe');
const editable=computed(()=>can('management_api.change_phonemodel'));
const item=computed(()=>data.value?.templates[selected.value]);
const current=computed(()=>active.value==='safe'?draft.value?.safe:draft.value?.avoid[Number(active.value)]);
const dirty=computed(()=>draft.value&&JSON.stringify(draft.value)!==saved.value);
watch(dirty,value=>emit('dirty',Boolean(value)));
let sequence=0,alive=true,drag=null;
onBeforeUnmount(()=>{alive=false;sequence++;emit('dirty',false);emit('busy',false);});
function choose(index){selected.value=index;draft.value=structuredClone(toRaw(data.value.templates[index].regions));saved.value=JSON.stringify(draft.value);active.value='safe';}
async function switchTemplate(index){
 if(dirty.value){try{await ElMessageBox.confirm('切换模板会丢弃尚未保存的区域修改。','未保存的修改',{type:'warning'});}catch{return;}}
 choose(index);
}
async function load(){
 const ticket=++sequence;busy.value=true;emit('busy',true);error.value='';
 try{const result=await api(`admin/phone-models/${props.model.id}/composition/`);if(alive&&ticket===sequence){data.value=result;choose(0);}}
 catch(e){if(alive&&ticket===sequence)error.value=e.message;}
 finally{if(alive&&ticket===sequence){busy.value=false;emit('busy',false);}}
}
watch(()=>props.model.id,()=>{data.value=null;draft.value=null;load();},{immediate:true});
function suggest(){draft.value=structuredClone(toRaw(item.value.suggestion));active.value='safe';}
function addAvoid(){if(draft.value.avoid.length<8){draft.value.avoid.push({x:0,y:0,width:25,height:25});active.value=String(draft.value.avoid.length-1);}}
function removeAvoid(){draft.value.avoid.splice(Number(active.value),1);active.value='safe';}
async function save(reset=false){
 if(!editable.value||busy.value||props.disabled)return;
 if(reset){try{await ElMessageBox.confirm('移除此模板的人工设置，改用自动建议？','恢复自动建议');}catch{return;}}
 busy.value=true;emit('busy',true);error.value='';
 const {safe,avoid,margin,source_url,note,confirmed}=draft.value;
 const key=item.value.template_id,material=item.value.case_material;
 try{
  const result=await api(`admin/phone-models/${props.model.id}/composition/`,{method:'PUT',body:{revision:data.value.revision,template_id:key,case_material:material,safe,avoid,margin,source_url,note,confirmed,reset}});
  if(!alive)return;
  data.value=result;choose(Math.max(0,result.templates.findIndex(t=>t.template_id===key&&t.case_material===material)));
  ElMessage.success('构图区域已保存，新生成的图片将使用此设置。');
 }catch(e){if(alive)error.value=e.message;}
 finally{if(alive){busy.value=false;emit('busy',false);}}
}
function start(event,kind,resize=false){
 if(!editable.value||busy.value||props.disabled)return;
 event.preventDefault();active.value=kind;
 const svg=event.currentTarget.ownerSVGElement,box=svg.getBoundingClientRect();
 event.currentTarget.setPointerCapture(event.pointerId);
 drag={id:event.pointerId,box,startX:event.clientX,startY:event.clientY,rect:{...current.value},resize};
}
function move(event){
 if(!drag||drag.id!==event.pointerId)return;
 const dx=(event.clientX-drag.startX)/drag.box.width*100,dy=(event.clientY-drag.startY)/drag.box.height*100,r=drag.rect;
 const clamp=(n,min,max)=>Math.round(Math.max(min,Math.min(max,n))*100)/100;
 if(drag.resize){current.value.width=clamp(r.width+dx,1,100-r.x);current.value.height=clamp(r.height+dy,1,100-r.y);}
 else{current.value.x=clamp(r.x+dx,0,100-r.width);current.value.y=clamp(r.y+dy,0,100-r.height);}
 draft.value.confirmed=false;
}
const boxes=computed(()=>draft.value?[{key:'safe',rect:draft.value.safe},...draft.value.avoid.map((rect,index)=>({key:String(index),rect}))]:[]);
</script>
<template>
 <section class="composition-panel" v-loading="busy">
  <h3>AI 构图区域</h3>
  <p class="hint">绿色区域用于容纳完整头部与主体，红色区域只保留背景。可拖动区域，拖动右下角调整大小。此设置用于生成构图，不改变打印模板或库存。</p>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
  <el-button v-if="error" :disabled="busy" @click="load">重新加载区域</el-button>
  <template v-if="draft&&item">
   <el-select :model-value="selected" aria-label="构图机型款式与模板" :disabled="busy||disabled" @update:model-value="switchTemplate">
    <el-option v-for="(t,i) in data.templates" :key="t.case_material+':'+t.template_id" :value="i" :label="`${t.case_material==='magnetic'?'磁吸款':'普通款'} · ${t.template_id||'通用示意（无模板）'}`"/>
   </el-select>
   <p class="hint">{{item.width}} × {{item.height}} · {{item.saved?'人工设置':item.suggestion.origin==='preview_mask'?'已按预览遮罩自动初始化':'保守默认区域，待人工核对'}}<br>模板更新后需重新核对区域；不同款式分别保存。</p>
   <div class="composition-layout">
    <div class="region-canvas" :style="{aspectRatio:item.width+'/'+item.height}">
     <img v-if="item.overlay" :src="item.overlay" alt="当前机型手机壳模板" draggable="false"/>
     <span v-else class="no-template">无机型底图<br>通用比例示意</span>
     <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="AI 构图区域编辑器">
      <g v-for="box in boxes" :key="box.key" :class="[box.key==='safe'?'safe-region':'avoid-region',{'selected-region':active===box.key}]">
       <rect v-bind="box.rect" @pointerdown="start($event,box.key)" @pointermove="move" @pointerup="drag=null" @pointercancel="drag=null"/>
       <rect v-if="active===box.key&&editable" :x="box.rect.x+box.rect.width-2" :y="box.rect.y+box.rect.height-1.5" width="4" height="3" class="resize-handle" @pointerdown.stop="start($event,box.key,true)" @pointermove="move" @pointerup="drag=null" @pointercancel="drag=null"/>
      </g>
     </svg>
    </div>
    <div class="region-controls">
     <el-select v-model="active" aria-label="正在编辑的区域"><el-option value="safe" label="主体安全区（绿色）"/><el-option v-for="(_,i) in draft.avoid" :key="i" :value="String(i)" :label="`镜头遮挡区 ${i+1}（红色）`"/></el-select>
     <div class="region-numbers"><label v-for="(label,key) in {x:'左侧位置 %',y:'顶部位置 %',width:'区域宽度 %',height:'区域高度 %'}" :key="key">{{label}}<el-input-number v-model="current[key]" :aria-label="label" :precision="2" :min="key==='width'||key==='height'?1:0" :max="100" :step="1" :disabled="!editable||busy||disabled" @change="draft.confirmed=false"/></label></div>
     <div class="region-buttons"><el-button :disabled="!editable||busy||disabled||draft.avoid.length>=8" @click="addAvoid">添加遮挡区</el-button><el-button v-if="active!=='safe'" :disabled="!editable||busy||disabled" @click="removeAvoid">移除此区域</el-button></div>
     <label class="region-margin">安全区内额外留白 %<el-input-number v-model="draft.margin" aria-label="安全区内额外留白百分比" :min="0" :max="10" :step=".5" :disabled="!editable||busy||disabled"/></label>
     <p class="hint">背景仍铺满整张图。生成后默认完整显示原图，并用模糊背景补齐比例，减少再次裁切。</p>
    </div>
   </div>
   <label class="region-field">资料来源链接<el-input v-model="draft.source_url" placeholder="https://…（官方尺寸图或供应商资料）" :disabled="!editable||busy||disabled"/></label>
   <p class="hint"><a href="https://developer.apple.com/accessories/dimensional-drawings/" target="_blank" rel="noopener noreferrer">Apple 官方尺寸图 ↗</a> · <a href="https://developer.samsung.com/mobile/accessories.html" target="_blank" rel="noopener noreferrer">Samsung 官方配件资料 ↗</a></p>
   <label class="region-field">核对备注<el-input v-model="draft.note" type="textarea" maxlength="500" :disabled="!editable||busy||disabled"/></label>
   <el-checkbox v-model="draft.confirmed" :disabled="!editable||busy||disabled">已人工核对预览区域（不代表实物打印校准）</el-checkbox>
   <div class="region-buttons"><el-button :disabled="!editable||busy||disabled" @click="suggest">填入遮罩建议</el-button><el-button v-if="item.saved" :disabled="!editable||busy||disabled" @click="save(true)">恢复自动建议</el-button><el-button type="primary" :disabled="!editable||busy||disabled" @click="save(false)">保存构图区域</el-button><span v-if="dirty" class="hint">尚未保存</span></div>
  </template>
 </section>
</template>
<style scoped>
.composition-panel{margin-top:24px;padding:20px;border:1px solid #dce5e2;border-radius:12px}.hint{font-size:12px;color:#65716b;line-height:1.8}.composition-panel>.el-select{width:100%}.composition-layout{display:grid;grid-template-columns:minmax(140px,220px) minmax(0,1fr);gap:24px;margin:20px 0;align-items:start}.region-canvas{position:relative;width:100%;background:#f0e5fa;border:1px solid #dfcceb;border-radius:12px;overflow:hidden}.region-canvas>img,.region-canvas>svg{position:absolute;inset:0;width:100%;height:100%;object-fit:fill}.region-canvas svg{touch-action:none}.no-template{position:absolute;inset:40% 10%;text-align:center;font-size:13px;color:#786785}.safe-region rect{fill:#25b78c33;stroke:#13866a;stroke-width:.7;cursor:move}.avoid-region rect{fill:#e7474740;stroke:#d33131;stroke-width:.7;cursor:move}.selected-region rect{stroke-width:1.1}.region-canvas .resize-handle{fill:white;cursor:nwse-resize}.region-numbers{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}.region-numbers label,.region-margin,.region-field{display:grid;gap:8px;font-size:12px}.region-numbers .el-input-number{width:100%}.region-margin{margin:16px 0}.region-field{margin-top:15px}.region-buttons{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.region-buttons .el-button+.el-button{margin-left:0}@media(max-width:580px){.composition-layout{grid-template-columns:1fr}.region-canvas{width:170px;margin:auto}.composition-panel{padding:14px}}
</style>
