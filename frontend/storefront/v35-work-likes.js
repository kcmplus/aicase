// Personal browser preferences, scoped by the existing design workspace.
// This never publishes a design or claims a public community like count.
export function mountWorkLikes(root,{read,update,active=()=>true,onError=()=>{}}){
 let closed=false;
 const buttons=[...root.querySelectorAll('[data-work-like]')];
 const normalize=rows=>Array.isArray(rows)?[...new Set(rows.filter(id=>typeof id==='string'))]:[];
 const paint=rows=>{const liked=new Set(normalize(rows));for(const button of buttons){const value=liked.has(button.dataset.workLike);button.setAttribute('aria-pressed',String(value));button.querySelector('span').textContent=value?'1':'0';button.disabled=!active();}};
 const live=()=>!closed&&active();
 async function click(event){
  const button=event.target.closest('[data-work-like]');if(!button||button.disabled||!live())return;
  event.preventDefault();const id=button.dataset.workLike;buttons.forEach(item=>item.disabled=true);
  try{const rows=await update(value=>{const all=normalize(value);return all.includes(id)?all.filter(item=>item!==id):[...all,id];});if(live())paint(rows);}
  catch{if(live()){buttons.forEach(item=>item.disabled=false);onError();}}
 }
 root.addEventListener('click',click);
 if(active())Promise.resolve().then(read).then(rows=>{if(live())paint(rows);}).catch(()=>{if(live())onError();});
 return ()=>{closed=true;root.removeEventListener('click',click);};
}
