const printed=order=>['printed','delivering','dispensed'].includes(order.progress?.code);
export function historyGroup(order){
 if(printed(order))return 'printed';
 if(order.status==='cancelled'||order.progress?.code==='cancelled'||['requested','pending','succeeded'].includes(order.refund?.status))return null;
 if(order.status==='pending'&&!order.refund)return 'pending';
 if(['paid','printing','ready','completed'].includes(order.status)&&['paid','free'].includes(order.progress?.payment))return 'paid';
 return null;
}

// Older servers ignore status/search parameters and omit counts. Read their
// complete owned list before filtering, so matches on later pages aren't lost.
export async function loadOrderHistory({request,page=1,filter='all',search='',initial=null,alive=()=>true}){
 const data=initial||await request('?page='+page+'&status='+filter+'&q='+encodeURIComponent(search));
 if(!alive())return data;
 if(data.counts)return data;
 const rows=[],seen=new Set();
 let next=1;
 for(;;){
  if(!alive())return data;
  const batch=next===page?data:await request('?page='+next);
  if(!alive())return data;
  for(const order of batch.results||[])if(!seen.has(order.reference)){seen.add(order.reference);rows.push(order);}
  if(!batch.has_more)break;
  if(!batch.results?.length||next>=100)throw Error('Your order list could not be fully loaded. Please refresh or contact support.');
  next++;
 }
 const counts={all:rows.length,pending:0,paid:0,printed:0};
 for(const row of rows){const group=historyGroup(row);if(group)counts[group]++;}
 const query=search.trim().toLowerCase(),referenceQuery=query.replaceAll('-','');
 const matches=rows.filter(row=>(filter==='all'||historyGroup(row)===filter)&&(!query||String(row.model_name||'').toLowerCase().includes(query)||(referenceQuery&&String(row.reference).toLowerCase().replaceAll('-','').includes(referenceQuery))));
 return {results:matches.slice((page-1)*20,page*20),page,has_more:matches.length>page*20,counts};
}
