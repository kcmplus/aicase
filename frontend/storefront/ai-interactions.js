import {generationWaitMessage} from './ai-wait.js';
import {t} from './simple-i18n.js';

// Update just the preview: changing views and dragging never recreates the image or job.
export function setAIView(root,value){
 const mode=['pair','compare','case'].includes(value)?value:'pair';
 root.querySelectorAll('[data-ai-view]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.aiView===mode)));
 root.querySelectorAll('[data-ai-pane]').forEach(pane=>{pane.hidden=pane.dataset.aiPane!==mode;});
 return mode;
}
export function setAIComparison(root,value){
 const number=Number(value),position=Number.isFinite(number)?Math.max(0,Math.min(100,number)):50;
 root.querySelector('.studio-compare-image')?.style.setProperty('--reveal',position+'%');
 const input=root.querySelector('[data-ai-compare]');
 if(input){input.value=String(position);input.setAttribute('aria-valuetext',position+'%');}
 return position;
}

// Keep space for the actual dock height, including translated copy and large text.
export function mountAIStudio(root,job){
 const flow=root.querySelector('.studio-flow'),dock=flow?.querySelector('.studio-controls');
 if(!flow)return ()=>{};
 const dialog=flow.querySelector('.studio-photo-dialog');
 const measure=()=>flow.style.setProperty('--studio-dock-height',`${dock?.getBoundingClientRect().height||0}px`);
 const observer=new ResizeObserver(measure);
 if(dock)observer.observe(dock);
 measure();
 const waitMessage=flow.querySelector('[data-ai-wait-message]');
 const updateWait=()=>{
  const message=t(generationWaitMessage(job));
  if(waitMessage.textContent!==message)waitMessage.textContent=message;
 };
 let waitTimer;
 if(waitMessage&&generationWaitMessage(job)){
  updateWait();
  waitTimer=setInterval(updateWait,1000);
 }
 const selectPhoto=value=>{
  const tab=value==='after'&&dialog.querySelector('[data-ai-photo-pane="after"]')?'after':'original';
  dialog.querySelectorAll('[data-ai-photo-tab]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.aiPhotoTab===tab)));
  dialog.querySelectorAll('[data-ai-photo-pane]').forEach(pane=>{pane.hidden=pane.dataset.aiPhotoPane!==tab;});
 };
 const click=event=>{
  const trigger=event.target.closest('[data-ai-photo]');
  if(trigger&&dialog){selectPhoto(trigger.dataset.aiPhoto);if(!dialog.open)dialog.showModal();return;}
  const tab=event.target.closest('[data-ai-photo-tab]');
  if(tab&&dialog){selectPhoto(tab.dataset.aiPhotoTab);return;}
  if(event.target.closest('[data-ai-photo-close]'))dialog?.close();
  if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}
 };
 flow.addEventListener('click',click);
 return ()=>{clearInterval(waitTimer);observer.disconnect();flow.removeEventListener('click',click);if(dialog?.open)dialog.close();};
}
