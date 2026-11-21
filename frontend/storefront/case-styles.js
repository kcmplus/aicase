import {esc} from './art.js';
const caseMaterials=['standard','magnetic'];
export const defaultCaseMaterial=record=>caseMaterials.find(material=>record?.styles?.some(style=>style.caseMaterial===material&&style.available===true))||'';
export const caseMaterialLabel=(value,lang='en-US')=>({standard:lang==='zh-CN'?'普通款':'Standard',magnetic:lang==='zh-CN'?'磁吸款':'Magnetic'}[value]||'');
export function caseStylePicker(record,selected,{lang='en-US',scoped=false}={}){
 if(!record)return '';
 const zh=lang==='zh-CN';
 return `<fieldset class="case-style-picker"><legend>${zh?'选择款式':'Choose case style'}</legend><div class="case-style-options">${caseMaterials.map(material=>{
  const style=record.styles?.find(s=>s.caseMaterial===material),enabled=style?.available===true;
  return `<button type="button" data-case-material="${material}" aria-pressed="${selected===material}" ${enabled?'':'disabled'}><strong>${esc(caseMaterialLabel(material,lang))}</strong>${!enabled?`<small>${zh?'此网点暂无可用物料':'Unavailable at this station'}</small>`:''}</button>`;
 }).join('')}</div>${scoped?`<p class="field-note">${zh?'仅可选择当前网点有库存且可打印的款式。':'Choose a style available for printing at this station.'}</p>`:''}</fieldset>`;
}
