import {readPass} from '../../storefront/simple-core.js';
import {makePersonalDesign} from '../../storefront/simple-personalize.js';
import {phoneTemplate,registerSupplierTemplates} from '../../storefront/phone-templates.js';

export function orderArtwork(order){
 if(order.snapshot?._template)registerSupplierTemplates([order.snapshot._template]);
 const pass=readPass(order.snapshot?.code,order.snapshot);
 if(pass.model!==order.model_name)throw Error('订单机型与设计快照不一致，无法确认打印孔位。');
 const design=makePersonalDesign(pass);
 // Never silently pick the latest template for a historical production file.
 const template=pass.phoneTemplateId?phoneTemplate(pass.model,pass.phoneTemplateId):null;
 const filename=template&&!template.previewOnly?`order-${order.reference}-r${order.revision}-${template.id}-print-${template.dpi}dpi.png`:'';
 return {pass,design,template,filename};
}
