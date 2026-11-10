// Read-only refreshes: pause hidden pages, never overlap, and ignore stopped work.
export function startVisiblePolling({refresh,interval,enabled=()=>true,onError=()=>{},document:doc=globalThis.document,setTimeout:later=globalThis.setTimeout,clearTimeout:cancel=globalThis.clearTimeout}){
 let timer=null,busy=false,stopped=false;
 const schedule=()=>{cancel(timer);if(!stopped&&!doc.hidden)timer=later(tick,interval);};
 async function tick(){
  cancel(timer);if(stopped||doc.hidden)return;
  if(busy)return;
  if(!enabled()){schedule();return;}
  busy=true;
  try{await refresh(()=>!stopped);}catch(error){if(!stopped)onError(error);}finally{busy=false;schedule();}
 }
 const visible=()=>{cancel(timer);if(!doc.hidden)void tick();};
 doc.addEventListener('visibilitychange',visible);schedule();
 return ()=>{stopped=true;cancel(timer);doc.removeEventListener('visibilitychange',visible);};
}
