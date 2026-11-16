// Body colors are optional previews. They never select stock or a print mask.
const asset=(value,role)=>typeof value==='string'&&new RegExp('^/media/phone-colors/[a-f0-9]{32}/'+role+'\\.png$').test(value);
export function validatePhoneColor(value,template){
 const r=value?.resource,rgb=value?.rgb;
 const rgbOnly=value?.previewMode==='rgb'&&value.resource===null;
 if(!value||typeof value.code!=='string'||!/^[-a-zA-Z0-9_]{1,80}$/.test(value.code)||typeof value.name!=='string'||value.name.length>120||typeof value.isDefault!=='boolean'||
  !rgb||Object.keys(rgb).sort().join(',')!=='b,g,r'||!Object.values(rgb).every(n=>Number.isInteger(n)&&n>=0&&n<=255)||
  (!rgbOnly&&(!r||!Number.isSafeInteger(r.version)||r.version<1||typeof r.templateId!=='string'||!/^[-a-zA-Z0-9_]{1,160}$/.test(r.templateId)||
  ![r.width,r.height].every(n=>Number.isInteger(n)&&n>=32&&n<=4096)||r.width*r.height>8_000_000||
  r.templateId!==template?.id||r.width!==template.sourceWidth||r.height!==template.sourceHeight||!asset(r.overlay,'overlay')||!asset(r.mask,'mask'))))throw Error('Invalid phone color preview.');
 if(rgbOnly)return {code:value.code,name:value.name,rgb:{...rgb},isDefault:value.isDefault,previewMode:'rgb',resource:null};
 return {code:value.code,name:value.name,rgb:{...rgb},isDefault:value.isDefault,resource:{version:r.version,templateId:r.templateId,width:r.width,height:r.height,overlay:r.overlay,mask:r.mask}};
}
// A paid snapshot remains readable after an explicit device-template change.
// Consumers may paint it only when it matches the template being previewed.
export function frozenPhoneColor(value){
 return validatePhoneColor(value,{id:value?.resource?.templateId,sourceWidth:value?.resource?.width,sourceHeight:value?.resource?.height});
}
export function validPhoneColors(values,template){
 if(!Array.isArray(values))return [];
 const seen=new Set();
 return values.flatMap(value=>{try{const color=validatePhoneColor(value,template);if(seen.has(color.code))return [];seen.add(color.code);return [color];}catch{return [];}});
}
export function reconcilePhoneColor(saved,colors=[]){
 const current=saved&&colors.find(c=>c.code===saved.code&&(c.resource?.version??0)===(saved.resource?.version??0));
 const color=current||colors.find(c=>c.isDefault)||colors[0]||null;
 return {color,changed:Boolean(saved)&&JSON.stringify(saved)!==JSON.stringify(current||null)};
}
export function colorSelection(value){return value?{code:value.code,version:value.resource?.version??0,...(!value.resource?{rgb:{...value.rgb}}:{})}:undefined;}
export function colorPicker(colors,selected,lang='en-US',changed=false){
 const zh=lang==='zh-CN',esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const note=changed?`<p class="field-note" role="status">${zh?'原选颜色已失效或配置已变化，请重新确认预览。':'Your saved color changed or is unavailable. Please review the preview again.'}</p>`:'';
 if(!colors.length)return note;
 return `<fieldset class="v35-phone-colors"><legend>${zh?'机身预览颜色（近似显示色）':'Phone body preview (approximate color)'}</legend><div>${colors.map(c=>`<button type="button" data-phone-color="${esc(c.code)}" aria-pressed="${c.code===selected?.code}" aria-label="${esc(c.name||c.code)}"><span aria-hidden="true" style="background:rgb(${c.rgb.r},${c.rgb.g},${c.rgb.b})"></span>${esc(c.name||c.code)}</button>`).join('')}</div><p class="field-note">${zh?'仅改变机身预览，不改变壳体库存或打印内容。':'Preview only; case stock and printed artwork stay the same.'}</p></fieldset>${note}`;
}
