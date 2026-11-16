import {esc} from './art.js';

const stages={
 awaiting_payment:['等待付款','Awaiting payment','付款确认后继续选择打印设备。','Choose a station after payment is confirmed.'],
 unbound:['待选择设备','Choose a station','到设备前扫描屏幕上的二维码。','Scan the code on the station screen when you arrive.'],
 awaiting_dispatch:['待推送订单','Ready to send','请确认目标设备，再推送订单。','Confirm your station before sending the order.'],
 submitting:['正在推送订单','Sending order','正在确认设备是否收到订单，请勿重复提交。','Checking whether the station received the order. Do not send it again.'],
 awaiting_confirmation:['待确认打印','Ready for print confirmation','请在目标设备前点击「立即打印」。','At your selected station, choose Print now to confirm.'],
 waiting_device:['等待设备反馈','Waiting for station update','开印确认已记录，等待设备反馈；请勿重复操作。','Your print confirmation is recorded. Waiting for the station; do not submit again.'],
 printing:['打印中','Printing','设备正在打印你的手机壳。','The station is printing your case.'],
 printed:['已打印，等待出货','Printed · waiting to dispense','打印已完成，请等待设备出货。','Printing is complete. Please wait for dispensing.'],
 delivering:['出货中','Dispensing','设备正在出货，请在出货口等候。','Your case is being dispensed. Please wait at the collection slot.'],
 dispensed:['已出货，请取件','Dispensed · collect your case','请取走手机壳。出货记录不代表已经领取。','Please collect your case. Dispensing does not confirm collection.'],
 print_failed:['打印异常','Printing needs attention','请联系现场工作人员，勿重复打印。','Contact station staff. Do not print again.'],
 delivery_failed:['出货异常','Dispensing needs attention','请联系现场工作人员处理出货。','Contact station staff for help collecting your case.'],
 rejected:['推单未成功','Order was not sent','设计和目标设备已保留，请查看详情后确认是否重试。','Your design and station are saved. Review the details before retrying.'],
 unverified:['设备进度待核实','Station progress needs checking','暂时无法确认设备进度，请勿重复打印。可刷新状态或联系工作人员。','Station progress cannot be confirmed yet. Do not print again. Refresh or contact staff.'],
 cancelled:['订单已取消','Order cancelled','打印已停止放行；退款情况请查看退款状态。','No further print release is available. Check the refund status separately.'],
 refund_pending:['退款处理中，打印暂停','Refund in progress · printing paused','',''],
 refunded:['已退款，打印已关闭','Refunded · printing closed','',''],
 closed:['订单已结束','Order closed','',''],
 test:['测试订单，不代表真实打印','Test order · no verified physical printing','',''],
 delivery:['独立配送流程','Separate delivery process','此订单不进入现场设备打印流程，请联系客服了解配送情况。','This order uses separate delivery fulfillment. Contact support for delivery updates.'],
 unspecified:['配送方式待确认','Delivery method needs confirmation','',''],
};
export function progressText(progress,lang='en-US'){
 const entry=stages[progress?.code]||stages.unverified,zh=lang==='zh-CN';
 const tone=['print_failed','delivery_failed','rejected'].includes(progress?.code)?'danger':progress?.code==='dispensed'?'success':['unverified','refund_pending'].includes(progress?.code)?'warning':'info';
 return {label:entry[zh?0:1],description:entry[zh?2:3],tone};
}
export function progressPaymentText(progress,lang='en-US'){
 const labels={paid:['已付款','Paid'],unpaid:['待付款','Awaiting payment'],free:['0 元免付已确认','No-charge order confirmed'],test:['测试付款','Test payment'],unverified:['付款待核实','Payment needs checking']};
 return (labels[progress?.payment]||labels.unverified)[lang==='zh-CN'?0:1];
}
export function progressTime(progress,lang='en-US'){
 const time=Date.parse(progress?.updated_at);
 return Number.isFinite(time)?new Date(time).toLocaleString(lang):lang==='zh-CN'?'尚无设备反馈':'No station update yet';
}
export function progressPanel(progress,{lang='en-US',compact=false,includeDevice=true}={}){
 const zh=lang==='zh-CN',text=progressText(progress,lang),device=progress?.device;
 const steps=[['awaiting_dispatch','待推单','Send order'],['awaiting_confirmation','确认打印','Confirm print'],['printing','打印','Printing'],['delivering','出货','Dispensing'],['dispensed','取件','Collect']];
 const current={submitting:'awaiting_dispatch',waiting_device:'awaiting_confirmation',printed:'printing'}[progress?.code]||progress?.code;
 const timeline=!compact&&steps.some(([key])=>key===current)?`<ol class="print-steps" aria-label="${zh?'打印流程':'Printing stages'}">${steps.map(([key,cn,en])=>`<li ${key===current?'aria-current="step"':''}>${zh?cn:en}</li>`).join('')}</ol>`:'';
 return `<section class="order-progress tone-${text.tone}" aria-label="${zh?'打印进度':'Print progress'}"><p class="eyebrow">${zh?'打印进度':'PRINT PROGRESS'}</p><strong class="print-progress-label">${esc(text.label)}</strong>${!compact&&text.description?`<p>${esc(text.description)}</p>`:''}${timeline}${includeDevice&&device?`<p class="progress-device">${esc(device.name)}${device.location?` · ${esc(device.location)}`:''}</p>`:''}${!compact&&progress?.message?`<p>${esc(progress.message)}</p>`:''}<small>${esc(progressTime(progress,lang))}${progress?.updated_at?(zh?' · 设备反馈时间':' · Station update'):''}</small>${progress?.stale?`<p class="progress-stale">${zh?'设备反馈暂未更新，以上为最后已知进度。':'Station updates are delayed. Showing the last known progress.'}</p>`:''}</section>`;
}
