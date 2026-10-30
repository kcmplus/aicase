export const generationEstimate='Usually takes around 10–20 seconds. Busy times may take longer.';

// Only the server advances a render. Elapsed time changes reassurance, never progress.
export function generationWaitMessage(job,now=Date.now()){
 if(!job||job.mode!=='live'||!['queued','generating'].includes(job.status))return '';
 const since=job.status==='generating'?(job.startedAt??job.paidAt):job.paidAt;
 const elapsed=Number.isFinite(since)?Math.max(0,now-since):0;
 if(job.status==='queued')return elapsed>=30000
  ?'The queue is a little busy. Your place is saved; no need to submit again.'
  :'Your photo is in line. We’ll start as soon as a slot opens.';
 if(elapsed>=30000)return 'This one is taking a little longer. We’re still waiting for your image; no need to submit again.';
 if(elapsed>=10000)return 'Thanks for waiting. A little more patience for a look that’s all yours.';
 return 'Your photo, a little imagination… something uniquely yours is on its way.';
}
